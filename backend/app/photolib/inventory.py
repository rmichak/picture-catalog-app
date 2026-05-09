"""Worker functions for the inventory subcommand. Importable by both the CLI
and `multiprocessing.Pool` workers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.photolib import is_media, is_photo
from app.photolib.dates import extract_date
from app.photolib.hashing import phash_file, sha256_file


@dataclass
class InventoryRecord:
    path: str
    name: str
    sha256: str | None
    phash: str | None
    size_bytes: int
    mtime_ts: float
    width: int | None
    height: int | None
    taken_at_iso: str | None
    date_source: str
    error: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def process_file(path_str: str) -> InventoryRecord:
    """Compute hash + phash + EXIF + dimensions for one file. Safe for `Pool.map`."""
    path = Path(path_str)
    name = path.name
    try:
        st = path.stat()
        size = st.st_size
        mtime = st.st_mtime
    except OSError as e:
        return _err(path_str, name, f"stat: {e}")

    try:
        sha = sha256_file(path)
    except OSError as e:
        return _err(path_str, name, f"sha: {e}", size=size, mtime=mtime)

    phash = phash_file(path) if is_photo(name) else None
    width, height = _dimensions(path)
    taken_at, source = extract_date(path)

    return InventoryRecord(
        path=path_str,
        name=name,
        sha256=sha,
        phash=phash,
        size_bytes=size,
        mtime_ts=mtime,
        width=width,
        height=height,
        taken_at_iso=taken_at.isoformat() if taken_at else None,
        date_source=source,
        error=None,
    )


def _err(
    path_str: str,
    name: str,
    msg: str,
    *,
    size: int = 0,
    mtime: float = 0.0,
) -> InventoryRecord:
    return InventoryRecord(
        path=path_str,
        name=name,
        sha256=None,
        phash=None,
        size_bytes=size,
        mtime_ts=mtime,
        width=None,
        height=None,
        taken_at_iso=None,
        date_source="none",
        error=msg,
    )


def _dimensions(path: Path) -> tuple[int | None, int | None]:
    if not is_photo(path.name):
        return None, None
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None


def discover_paths(
    include_dirs: list[Path],
    exclude_dirs: set[Path],
    include_root_files: list[Path] | None = None,
) -> list[Path]:
    """Walk include_dirs recursively, skipping any path under an exclude_dir.

    `include_root_files` is a literal list of files (e.g., loose photos at the Dropbox root)
    that don't need walking but should be added to the inventory.
    """
    results: list[Path] = []
    excludes_resolved = {p.resolve() for p in exclude_dirs}

    for root in include_dirs:
        root = root.expanduser()
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if not is_media(p.name):
                continue
            if _is_under_any(p, excludes_resolved):
                continue
            results.append(p)

    if include_root_files:
        for p in include_root_files:
            p = p.expanduser()
            if p.is_file() and is_media(p.name) and not _is_under_any(p, excludes_resolved):
                results.append(p)

    # Deterministic order — matters for resume from `last_path_processed`.
    results.sort(key=lambda p: str(p))
    return results


def _is_under_any(p: Path, excludes: set[Path]) -> bool:
    try:
        rp = p.resolve()
    except OSError:
        return False
    for ex in excludes:
        try:
            rp.relative_to(ex)
            return True
        except ValueError:
            continue
    return False


def has_year_in_path(path: str) -> bool:
    """Heuristic for canonical-picking: path contains a YYYY segment plausibly a year."""
    import re

    return bool(re.search(r"(?:^|/|[ _-])(19[789]\d|20[0-3]\d)(?:$|/|[ _.-])", path))


def parse_taken_at(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None
