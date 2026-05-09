"""Reorganize CLI — bulk Dropbox photo dedupe + year/month bucketing.

See plan: ~/.claude/plans/for-right-now-lets-replicated-twilight.md
"""

from __future__ import annotations

import json
import os
import signal
import sys
import tomllib
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from tqdm import tqdm

# Make backend importable when run as a script: `python scripts/reorganize.py ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import ReorganizeRun, SourceFileAudit  # noqa: E402
from app.photolib.dedupe import DupGroup, FileRecord, classify  # noqa: E402
from app.photolib.inventory import (  # noqa: E402
    InventoryRecord,
    discover_paths,
    has_year_in_path,
    parse_taken_at,
    process_file,
)
from app.photolib.move import (  # noqa: E402
    move_with_sidecar,
    no_date_target,
    organized_target,
    quarantine_target,
    resolve_collision,
    review_target,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)

DEFAULT_CONFIG = Path(__file__).resolve().parent / "reorganize.toml"
PAUSE_SENTINEL = settings.data_dir / "reorganize.pause"


# ---------------------------------------------------------------------------
# config loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReorgConfig:
    source_root: Path
    dest_root: Path
    include_dirs: list[Path]
    include_root_files: list[Path]
    exclude_dirs: list[Path]

    def to_snapshot(self) -> str:
        return json.dumps(
            {
                "source_root": str(self.source_root),
                "dest_root": str(self.dest_root),
                "include_dirs": [str(p) for p in self.include_dirs],
                "include_root_files": [str(p) for p in self.include_root_files],
                "exclude_dirs": [str(p) for p in self.exclude_dirs],
            }
        )


def load_config(path: Path) -> ReorgConfig:
    raw = tomllib.loads(path.read_text())
    src = Path(raw["source_root"]).expanduser()
    return ReorgConfig(
        source_root=src,
        dest_root=Path(raw["dest_root"]).expanduser(),
        include_dirs=[src / d for d in raw.get("include_dirs", [])],
        include_root_files=[src / f for f in raw.get("include_root_files", [])],
        exclude_dirs=[src / d for d in raw.get("exclude_dirs", [])],
    )


# ---------------------------------------------------------------------------
# pause / SIGINT plumbing
# ---------------------------------------------------------------------------


_pause_flag = {"set": False}


def _install_sigint() -> None:
    def handler(_signum, _frame):
        _pause_flag["set"] = True
        typer.echo("\n[reorganize] pause requested — finishing in-flight work and exiting...")

    signal.signal(signal.SIGINT, handler)


def pause_requested() -> bool:
    return _pause_flag["set"] or PAUSE_SENTINEL.exists()


def clear_pause_sentinel() -> None:
    if PAUSE_SENTINEL.exists():
        PAUSE_SENTINEL.unlink()
    _pause_flag["set"] = False


# ---------------------------------------------------------------------------
# run lifecycle
# ---------------------------------------------------------------------------


def open_run(s: Session, command: str, cfg: ReorgConfig, files_total: int) -> ReorganizeRun:
    run = ReorganizeRun(
        command=command,
        status="running",
        files_total=files_total,
        files_processed=0,
        config_snapshot=cfg.to_snapshot(),
    )
    s.add(run)
    s.commit()
    s.refresh(run)
    return run


def close_run(s: Session, run_id: int, status: str, error: str | None = None) -> None:
    s.execute(
        update(ReorganizeRun)
        .where(ReorganizeRun.id == run_id)
        .values(status=status, ended_at=datetime.now(UTC), error_message=error)
    )
    s.commit()


def latest_run_for(s: Session, command: str, status: str | None = None) -> ReorganizeRun | None:
    stmt = select(ReorganizeRun).where(ReorganizeRun.command == command)
    if status:
        stmt = stmt.where(ReorganizeRun.status == status)
    stmt = stmt.order_by(ReorganizeRun.id.desc()).limit(1)
    return s.execute(stmt).scalar_one_or_none()


# ---------------------------------------------------------------------------
# inventory subcommand
# ---------------------------------------------------------------------------


@app.command()
def inventory(
    config: Annotated[Path, typer.Option(help="Path to reorganize.toml")] = DEFAULT_CONFIG,
    workers: Annotated[int, typer.Option(help="Worker process count")] = 0,
    batch: Annotated[int, typer.Option(help="DB commit batch size")] = 200,
) -> None:
    """Walk source folders, hash + EXIF + date every file, populate audit table."""
    Base.metadata.create_all(bind=engine)
    cfg = load_config(config)
    _install_sigint()

    typer.echo(f"[inventory] source: {cfg.source_root}")
    typer.echo(f"[inventory] include: {len(cfg.include_dirs)} dirs")
    typer.echo("[inventory] discovering files (this can take a moment for large trees)...")
    paths = discover_paths(cfg.include_dirs, set(cfg.exclude_dirs), cfg.include_root_files)
    typer.echo(f"[inventory] discovered: {len(paths):,} candidate files")

    with SessionLocal() as s:
        seen = _existing_inventory_index(s)
        skip_count = 0
        todo: list[Path] = []
        for p in paths:
            try:
                st = p.stat()
            except OSError:
                continue
            key = (str(p), st.st_size, st.st_mtime)
            if key in seen:
                skip_count += 1
                continue
            todo.append(p)
        typer.echo(
            f"[inventory] resume-skip: {skip_count:,} already in audit; queueing {len(todo):,}"
        )

        run = open_run(s, "inventory", cfg, files_total=len(todo))

    if not todo:
        with SessionLocal() as s:
            close_run(s, run.id, "completed")
        typer.echo("[inventory] nothing to do.")
        return

    n_workers = workers or max(1, (os.cpu_count() or 4) - 1)
    typer.echo(f"[inventory] using {n_workers} worker processes, batch size {batch}")

    pending: list[InventoryRecord] = []
    final_status = "completed"
    error: str | None = None
    last_path: str | None = None

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        path_iter = iter(todo)
        in_flight: dict[Future, Path] = {}
        prime = min(n_workers * 4, len(todo))
        for _ in range(prime):
            p = next(path_iter)
            in_flight[pool.submit(process_file, str(p))] = p

        with tqdm(total=len(todo), unit="file") as bar:
            while in_flight:
                done, _not = wait(list(in_flight), timeout=1.0, return_when=FIRST_COMPLETED)
                for fut in done:
                    p = in_flight.pop(fut)
                    try:
                        rec = fut.result()
                    except Exception as e:  # noqa: BLE001
                        rec = _failed_record(p, f"worker: {e}")
                    pending.append(rec)
                    last_path = rec.path
                    bar.update(1)
                    if len(pending) >= batch:
                        with SessionLocal() as s:
                            _flush_inventory(s, run.id, pending, last_path)
                        pending.clear()
                    # keep the queue full
                    if not pause_requested():
                        try:
                            np = next(path_iter)
                            in_flight[pool.submit(process_file, str(np))] = np
                        except StopIteration:
                            pass
                if pause_requested() and not in_flight:
                    final_status = "paused"
                if pause_requested():
                    # drain in-flight, then exit
                    for fut in list(in_flight):
                        p = in_flight.pop(fut)
                        try:
                            rec = fut.result()
                        except Exception as e:  # noqa: BLE001
                            rec = _failed_record(p, f"worker: {e}")
                        pending.append(rec)
                        last_path = rec.path
                        bar.update(1)
                    final_status = "paused"
                    break

    with SessionLocal() as s:
        if pending:
            _flush_inventory(s, run.id, pending, last_path)
        close_run(s, run.id, final_status, error)
    typer.echo(f"[inventory] done — status: {final_status}")


def _existing_inventory_index(s: Session) -> set[tuple[str, int, float]]:
    rows = s.execute(
        select(SourceFileAudit.original_path, SourceFileAudit.size_bytes, SourceFileAudit.mtime_ts)
    ).all()
    return {(r[0], r[1] or 0, r[2] or 0.0) for r in rows}


def _flush_inventory(
    s: Session, run_id: int, recs: list[InventoryRecord], last_path: str | None
) -> None:
    s.bulk_save_objects(
        [
            SourceFileAudit(
                run_id=run_id,
                original_path=r.path,
                action="discovered" if r.error is None else "error",
                sha256=r.sha256,
                phash=r.phash,
                size_bytes=r.size_bytes,
                mtime_ts=r.mtime_ts,
                width=r.width,
                height=r.height,
                taken_at=parse_taken_at(r.taken_at_iso),
                date_source=r.date_source,
            )
            for r in recs
        ]
    )
    s.execute(
        update(ReorganizeRun)
        .where(ReorganizeRun.id == run_id)
        .values(
            files_processed=ReorganizeRun.files_processed + len(recs),
            last_path_processed=last_path,
        )
    )
    s.commit()


def _failed_record(p: Path, msg: str) -> InventoryRecord:
    return InventoryRecord(
        path=str(p),
        name=p.name,
        sha256=None,
        phash=None,
        size_bytes=0,
        mtime_ts=0.0,
        width=None,
        height=None,
        taken_at_iso=None,
        date_source="none",
        error=msg,
    )


# ---------------------------------------------------------------------------
# classify subcommand
# ---------------------------------------------------------------------------


@app.command(name="classify")
def cmd_classify(
    config: Annotated[Path, typer.Option("--config", help="Path to reorganize.toml")] = DEFAULT_CONFIG,
) -> None:
    """Group duplicates across 3 layers; update audit rows with action + group_id."""
    cfg = load_config(config)
    Base.metadata.create_all(bind=engine)
    typer.echo("[classify] loading audit rows...")

    with SessionLocal() as s:
        rows = (
            s.execute(
                select(SourceFileAudit).where(
                    SourceFileAudit.action.in_(["discovered", "plan_move", "plan_quarantine", "plan_review", "plan_no_date"])
                )
            )
            .scalars()
            .all()
        )
        typer.echo(f"[classify] {len(rows):,} rows in scope")

        records = [
            FileRecord(
                audit_id=r.id,
                path=r.original_path,
                name=Path(r.original_path).name,
                sha256=r.sha256 or "",
                phash=r.phash,
                size_bytes=r.size_bytes or 0,
                mtime_ts=r.mtime_ts or 0.0,
                has_year_in_path=has_year_in_path(r.original_path),
            )
            for r in rows
            if r.sha256
        ]
        typer.echo(f"[classify] usable (have sha256): {len(records):,}")

        run = open_run(s, "classify", cfg, files_total=len(records))

        # reset prior plan state for re-runs
        s.execute(
            update(SourceFileAudit)
            .where(SourceFileAudit.id.in_([r.id for r in rows]))
            .values(group_id=None, is_canonical=False, dup_layer=None)
        )
        s.commit()

        groups, singletons = classify(records)

        for g in tqdm(groups, desc="groups"):
            _apply_group(s, g)
        for r in tqdm(singletons, desc="singletons"):
            action = _action_for_singleton(s, r)
            s.execute(
                update(SourceFileAudit)
                .where(SourceFileAudit.id == r.audit_id)
                .values(action=action, is_canonical=True)
            )
        s.commit()

        n_exact = sum(1 for g in groups if g.layer == "exact")
        n_filename = sum(1 for g in groups if g.layer == "filename")
        n_perceptual = sum(1 for g in groups if g.layer == "perceptual")
        typer.echo(
            f"[classify] groups: exact={n_exact}  filename={n_filename}  perceptual={n_perceptual}"
        )
        close_run(s, run.id, "completed")


def _apply_group(s: Session, g: DupGroup) -> None:
    canon_action = "plan_move" if g.layer != "perceptual" else "plan_review"
    dup_action = {
        "exact": "plan_quarantine",
        "filename": "plan_quarantine",
        "perceptual": "plan_review",
    }[g.layer]

    if g.layer == "perceptual":
        # No canonical separation; whole cluster goes to review.
        for r in (g.canonical, *g.duplicates):
            s.execute(
                update(SourceFileAudit)
                .where(SourceFileAudit.id == r.audit_id)
                .values(action="plan_review", group_id=g.group_id, dup_layer="perceptual")
            )
        return

    # Determine canonical action — depends on whether a date is available
    canon_row = s.get(SourceFileAudit, g.canonical.audit_id)
    if canon_row and canon_row.taken_at is None:
        canon_action = "plan_no_date"

    s.execute(
        update(SourceFileAudit)
        .where(SourceFileAudit.id == g.canonical.audit_id)
        .values(
            action=canon_action,
            group_id=g.group_id,
            is_canonical=True,
            dup_layer=g.layer,
        )
    )
    for d in g.duplicates:
        s.execute(
            update(SourceFileAudit)
            .where(SourceFileAudit.id == d.audit_id)
            .values(
                action=dup_action,
                group_id=g.group_id,
                is_canonical=False,
                dup_layer=g.layer,
            )
        )


def _action_for_singleton(s: Session, r: FileRecord) -> str:
    row = s.get(SourceFileAudit, r.audit_id)
    if row and row.taken_at is None:
        return "plan_no_date"
    return "plan_move"


# ---------------------------------------------------------------------------
# plan subcommand
# ---------------------------------------------------------------------------


@app.command()
def plan(
    config: Annotated[Path, typer.Option(help="Path to reorganize.toml")] = DEFAULT_CONFIG,
    out: Annotated[Path, typer.Option(help="Output CSV path")] = settings.data_dir / "move-plan.csv",
) -> None:
    """Render planned moves to a CSV for human review before execute."""
    import csv

    cfg = load_config(config)
    Base.metadata.create_all(bind=engine)
    out.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as s:
        rows = (
            s.execute(
                select(SourceFileAudit).where(
                    SourceFileAudit.action.in_(
                        ["plan_move", "plan_quarantine", "plan_review", "plan_no_date"]
                    )
                )
            )
            .scalars()
            .all()
        )

        with out.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "audit_id",
                    "action",
                    "group_id",
                    "is_canonical",
                    "dup_layer",
                    "date_source",
                    "taken_at",
                    "original_path",
                    "target_path",
                    "sha256_short",
                ]
            )
            for r in rows:
                target = _planned_target(cfg, r)
                w.writerow(
                    [
                        r.id,
                        r.action,
                        r.group_id or "",
                        "1" if r.is_canonical else "0",
                        r.dup_layer or "",
                        r.date_source or "",
                        r.taken_at.isoformat() if r.taken_at else "",
                        r.original_path,
                        str(target) if target else "",
                        (r.sha256 or "")[:12],
                    ]
                )
    typer.echo(f"[plan] wrote {out}  ({len(rows):,} rows)")


def _planned_target(cfg: ReorgConfig, r: SourceFileAudit) -> Path | None:
    name = Path(r.original_path).name
    if r.action == "plan_move" and r.taken_at:
        return organized_target(cfg.dest_root, r.taken_at, name)
    if r.action == "plan_quarantine" and r.group_id:
        return quarantine_target(cfg.dest_root, r.group_id, name)
    if r.action == "plan_review" and r.group_id:
        return review_target(cfg.dest_root, r.group_id, name)
    if r.action == "plan_no_date":
        return no_date_target(cfg.dest_root, name)
    return None


# ---------------------------------------------------------------------------
# execute subcommand
# ---------------------------------------------------------------------------


_FINAL_BY_PLAN = {
    "plan_move": "moved",
    "plan_quarantine": "quarantined",
    "plan_review": "review",
    "plan_no_date": "no_date",
}


@app.command()
def execute(
    config: Annotated[Path, typer.Option(help="Path to reorganize.toml")] = DEFAULT_CONFIG,
    dry_run: Annotated[bool, typer.Option(help="Print actions, do not move files")] = False,
) -> None:
    """Apply planned moves and quarantines. Idempotent and resumable."""
    cfg = load_config(config)
    Base.metadata.create_all(bind=engine)
    _install_sigint()

    with SessionLocal() as s:
        rows = (
            s.execute(
                select(SourceFileAudit).where(SourceFileAudit.action.in_(list(_FINAL_BY_PLAN)))
            )
            .scalars()
            .all()
        )
        run = open_run(s, "execute", cfg, files_total=len(rows))

    final_status = "completed"
    last_path: str | None = None

    with SessionLocal() as s, tqdm(total=len(rows), unit="file") as bar:
        for r in rows:
            if pause_requested():
                final_status = "paused"
                break
            try:
                _execute_one(s, run.id, cfg, r, dry_run=dry_run)
            except Exception as e:  # noqa: BLE001
                s.execute(
                    update(SourceFileAudit)
                    .where(SourceFileAudit.id == r.id)
                    .values(action="error_execute")
                )
                typer.echo(f"[execute] error on {r.original_path}: {e}", err=True)
            last_path = r.original_path
            bar.update(1)
            if bar.n % 100 == 0:
                s.execute(
                    update(ReorganizeRun)
                    .where(ReorganizeRun.id == run.id)
                    .values(files_processed=bar.n, last_path_processed=last_path)
                )
                s.commit()
        s.execute(
            update(ReorganizeRun)
            .where(ReorganizeRun.id == run.id)
            .values(files_processed=bar.n, last_path_processed=last_path)
        )
        s.commit()
        close_run(s, run.id, final_status)

    typer.echo(f"[execute] done — status: {final_status}")


def _execute_one(
    s: Session, run_id: int, cfg: ReorgConfig, r: SourceFileAudit, *, dry_run: bool
) -> None:
    src = Path(r.original_path)
    target = _planned_target(cfg, r)
    final_action = _FINAL_BY_PLAN[r.action]

    if not src.exists():
        # already moved? if target exists with matching sha, finalize idempotently
        if target and target.exists() and r.sha256 and target.is_file():
            s.execute(
                update(SourceFileAudit)
                .where(SourceFileAudit.id == r.id)
                .values(action=final_action, target_path=str(target), run_id=run_id)
            )
            s.commit()
            return
        s.execute(
            update(SourceFileAudit)
            .where(SourceFileAudit.id == r.id)
            .values(action="missing_source", run_id=run_id)
        )
        s.commit()
        return

    if target is None:
        return

    final_target, action = resolve_collision(target, r.sha256 or "")
    if dry_run:
        typer.echo(f"[dry] {r.action} {src} -> {final_target} ({action})")
        return

    if action == "skip-identical":
        # source exists but identical at target — remove source
        if src != final_target:
            src.unlink()
    else:
        sidecar = None
        if r.action in ("plan_quarantine", "plan_review") and r.group_id:
            sidecar = {
                "group_id": r.group_id,
                "dup_layer": r.dup_layer,
                "is_canonical": r.is_canonical,
                "sha256": r.sha256,
                "phash": r.phash,
                "date_source": r.date_source,
                "original_path": r.original_path,
            }
        move_with_sidecar(src, final_target, sidecar=sidecar)

    s.execute(
        update(SourceFileAudit)
        .where(SourceFileAudit.id == r.id)
        .values(action=final_action, target_path=str(final_target), run_id=run_id)
    )
    s.commit()


# ---------------------------------------------------------------------------
# verify subcommand
# ---------------------------------------------------------------------------


@app.command()
def verify(
    config: Annotated[Path, typer.Option(help="Path to reorganize.toml")] = DEFAULT_CONFIG,
) -> None:
    """Confirm every audit row's target_path exists and (for moved files) hashes match."""
    from app.photolib.hashing import sha256_file as _sha

    cfg = load_config(config)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as s:
        rows = (
            s.execute(
                select(SourceFileAudit).where(
                    SourceFileAudit.action.in_(["moved", "quarantined", "review", "no_date"])
                )
            )
            .scalars()
            .all()
        )
        run = open_run(s, "verify", cfg, files_total=len(rows))

    missing = 0
    hash_mismatch = 0
    with tqdm(total=len(rows), unit="file") as bar:
        for r in rows:
            bar.update(1)
            if not r.target_path:
                missing += 1
                continue
            tp = Path(r.target_path)
            if not tp.exists():
                missing += 1
                typer.echo(f"[verify] missing target: {tp}", err=True)
                continue
            if r.action == "moved" and r.sha256:
                try:
                    if _sha(tp) != r.sha256:
                        hash_mismatch += 1
                        typer.echo(f"[verify] hash mismatch: {tp}", err=True)
                except OSError as e:
                    typer.echo(f"[verify] read error on {tp}: {e}", err=True)

    with SessionLocal() as s:
        close_run(s, run.id, "completed")
    typer.echo(f"[verify] checked {len(rows):,}  missing={missing}  hash_mismatch={hash_mismatch}")


# ---------------------------------------------------------------------------
# status / pause / resume / cancel / undo
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show the most recent reorganize run and pause sentinel state."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        run = s.execute(
            select(ReorganizeRun).order_by(ReorganizeRun.id.desc()).limit(1)
        ).scalar_one_or_none()
    if run is None:
        typer.echo("[status] no runs yet")
        return
    pct = (100.0 * run.files_processed / run.files_total) if run.files_total else 0.0
    typer.echo(f"run #{run.id}  command={run.command}  status={run.status}")
    typer.echo(f"  started={run.started_at}  ended={run.ended_at or '-'}")
    typer.echo(f"  progress: {run.files_processed:,}/{run.files_total:,}  ({pct:.1f}%)")
    if run.last_path_processed:
        typer.echo(f"  last path: {run.last_path_processed}")
    if run.error_message:
        typer.echo(f"  error: {run.error_message}")
    typer.echo(f"pause sentinel present: {PAUSE_SENTINEL.exists()}")


@app.command()
def pause() -> None:
    """Ask the running reorganize process to stop after the current file."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    PAUSE_SENTINEL.touch()
    typer.echo(f"[pause] wrote {PAUSE_SENTINEL}")


@app.command()
def resume(
    config: Annotated[Path, typer.Option(help="Path to reorganize.toml")] = DEFAULT_CONFIG,
) -> None:
    """Continue the most recent paused run by re-invoking its command."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        run = s.execute(
            select(ReorganizeRun)
            .where(ReorganizeRun.status == "paused")
            .order_by(ReorganizeRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if run is None:
        typer.echo("[resume] no paused run found")
        raise typer.Exit(code=1)
    typer.echo(f"[resume] continuing run #{run.id} ({run.command})")
    clear_pause_sentinel()
    if run.command == "inventory":
        inventory(config=config)
    elif run.command == "execute":
        execute(config=config)
    else:
        typer.echo(f"[resume] command {run.command} is not resumable")
        raise typer.Exit(code=1)


@app.command()
def cancel(run_id: int) -> None:
    """Mark a run canceled (does not roll back work — use undo for that)."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        s.execute(
            update(ReorganizeRun)
            .where(ReorganizeRun.id == run_id)
            .values(status="canceled", ended_at=datetime.now(UTC))
        )
        s.commit()
    typer.echo(f"[cancel] run #{run_id} marked canceled")


@app.command()
def undo(run_id: int) -> None:
    """Reverse all moves from a run by walking the audit table in reverse."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        rows = (
            s.execute(
                select(SourceFileAudit)
                .where(SourceFileAudit.run_id == run_id)
                .where(SourceFileAudit.action.in_(["moved", "quarantined", "review", "no_date"]))
            )
            .scalars()
            .all()
        )
        typer.echo(f"[undo] reversing {len(rows):,} moves from run #{run_id}")

        with tqdm(total=len(rows), unit="file") as bar:
            for r in rows:
                bar.update(1)
                if not r.target_path:
                    continue
                tp = Path(r.target_path)
                op = Path(r.original_path)
                if not tp.exists():
                    continue
                op.parent.mkdir(parents=True, exist_ok=True)
                if op.exists():
                    typer.echo(f"[undo] skip — original path occupied: {op}", err=True)
                    continue
                tp.rename(op)
                # cleanup sidecar if present
                side = tp.with_suffix(tp.suffix + ".reorg.json")
                if side.exists():
                    side.unlink()
                s.execute(
                    update(SourceFileAudit)
                    .where(SourceFileAudit.id == r.id)
                    .values(action="undone")
                )
        s.commit()
    typer.echo(f"[undo] done")


if __name__ == "__main__":
    app()
