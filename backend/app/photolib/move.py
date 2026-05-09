from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.photolib.dates import year_month_dir
from app.photolib.hashing import sha256_file


def organized_target(dest_root: Path, taken_at: datetime, original_name: str) -> Path:
    y, m = year_month_dir(taken_at)
    return dest_root / y / m / original_name


def quarantine_target(dest_root: Path, group_id: str, original_name: str) -> Path:
    safe = group_id.replace(":", "-").replace("/", "-")
    return dest_root / "_duplicates" / safe / original_name


def review_target(dest_root: Path, group_id: str, original_name: str) -> Path:
    safe = group_id.replace(":", "-").replace("/", "-")
    return dest_root / "_review-perceptual" / safe / original_name


def no_date_target(dest_root: Path, original_name: str) -> Path:
    return dest_root / "_no-date" / original_name


def resolve_collision(target: Path, source_sha: str) -> tuple[Path, str]:
    """Pick a final path for `source_sha` at or near `target`.

    Returns (final_path, action). action is one of:
      - "skip-identical" — target already exists with matching sha (idempotent re-run)
      - "ok" — target free, write to `target`
      - "appended" — target taken by different content; chose `final_path` with __NNN suffix
    """
    if not target.exists():
        return target, "ok"
    try:
        if sha256_file(target) == source_sha:
            return target, "skip-identical"
    except OSError:
        pass
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    for n in range(1, 1000):
        candidate = parent / f"{stem}__{n:03d}{suffix}"
        if not candidate.exists():
            return candidate, "appended"
        try:
            if sha256_file(candidate) == source_sha:
                return candidate, "skip-identical"
        except OSError:
            continue
    raise RuntimeError(f"Too many collisions resolving {target}")


def move_with_sidecar(
    src: Path,
    dst: Path,
    sidecar: dict[str, object] | None = None,
) -> None:
    """Move src → dst (creating parents). Optionally write `<dst>.json` sidecar."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst) if src.parent == dst.parent or _same_device(src, dst) else _cross_device_move(
        src, dst
    )
    if sidecar is not None:
        sidecar_path = dst.with_suffix(dst.suffix + ".reorg.json")
        sidecar_path.write_text(json.dumps(sidecar, default=str, indent=2))


def _same_device(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_dev == b.parent.stat().st_dev
    except OSError:
        return False


def _cross_device_move(src: Path, dst: Path) -> None:
    """Fallback for moves across filesystems: copy + verify + unlink."""
    import shutil

    shutil.copy2(src, dst)
    if sha256_file(src) != sha256_file(dst):
        dst.unlink(missing_ok=True)
        raise RuntimeError(f"Copy verification failed for {src} → {dst}")
    src.unlink()
