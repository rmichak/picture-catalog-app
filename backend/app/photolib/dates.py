from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.photolib import is_photo

# EXIF tag 36867 = DateTimeOriginal (preferred) ; 306 = DateTime ; 36868 = DateTimeDigitized
_EXIF_DATE_TAGS = (36867, 36868, 306)

# Match year-month-day in filenames. Order matters: longer/specific first.
_FILENAME_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?P<y>20\d{2}|19[789]\d)[-_.](?P<m>0[1-9]|1[0-2])[-_.](?P<d>0[1-9]|[12]\d|3[01])"),
    re.compile(r"(?P<y>20\d{2}|19[789]\d)(?P<m>0[1-9]|1[0-2])(?P<d>0[1-9]|[12]\d|3[01])"),
)


def extract_date(path: Path) -> tuple[datetime | None, str]:
    """Return (taken_at, source). source is one of: exif, filename, mtime, none."""
    if is_photo(path.name):
        d = _from_exif(path)
        if d is not None:
            return d, "exif"
    d = _from_filename(path.name)
    if d is not None:
        return d, "filename"
    d = _from_mtime(path)
    if d is not None:
        return d, "mtime"
    return None, "none"


def _from_exif(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    if not exif:
        return None
    for tag in _EXIF_DATE_TAGS:
        raw = exif.get(tag)
        if not raw:
            continue
        d = _parse_exif_dt(raw)
        if d is not None:
            return d
    return None


def _parse_exif_dt(raw: object) -> datetime | None:
    s = raw.decode("ascii", errors="replace") if isinstance(raw, bytes) else str(raw)
    s = s.strip().rstrip("\x00")
    # Canonical EXIF: "YYYY:MM:DD HH:MM:SS"
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _from_filename(name: str) -> datetime | None:
    for pat in _FILENAME_DATE_PATTERNS:
        m = pat.search(name)
        if not m:
            continue
        try:
            return datetime(int(m["y"]), int(m["m"]), int(m["d"]))
        except ValueError:
            continue
    return None


def _from_mtime(path: Path) -> datetime | None:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return None
    try:
        return datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        return None


def year_month_dir(d: datetime) -> tuple[str, str]:
    return f"{d.year:04d}", f"{d.month:02d}"
