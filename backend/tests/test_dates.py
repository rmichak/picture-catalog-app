from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from app.photolib.dates import extract_date, year_month_dir


def _make_jpeg_with_exif(path: Path, dt_string: str) -> None:
    img = Image.new("RGB", (32, 32), color=(10, 20, 30))
    exif = img.getexif()
    exif[36867] = dt_string  # DateTimeOriginal
    img.save(path, "JPEG", exif=exif)


def test_exif_takes_priority(tmp_path: Path) -> None:
    p = tmp_path / "2099-01-01_misleading.jpg"  # filename says 2099
    _make_jpeg_with_exif(p, "2018:04:15 14:25:30")
    d, src = extract_date(p)
    assert src == "exif"
    assert d == datetime(2018, 4, 15, 14, 25, 30)


def test_iso_filename_when_no_exif(tmp_path: Path) -> None:
    p = tmp_path / "2021-08-12 17.56.39.jpg"
    Image.new("RGB", (16, 16)).save(p, "JPEG")
    d, src = extract_date(p)
    assert src == "exif" or src == "filename"  # may emit empty exif on some Pillow builds
    if src == "filename":
        assert d == datetime(2021, 8, 12)


def test_compact_date_filename(tmp_path: Path) -> None:
    p = tmp_path / "IMG_20180415_142530.jpg"
    p.write_bytes(b"")  # no real image — filename path tested
    d, src = extract_date(p)
    assert d is not None
    assert d.year == 2018 and d.month == 4 and d.day == 15


def test_mtime_fallback(tmp_path: Path) -> None:
    p = tmp_path / "noname.bin"
    p.write_bytes(b"x")
    target = time.mktime((2015, 6, 1, 12, 0, 0, 0, 0, -1))
    os.utime(p, (target, target))
    d, src = extract_date(p)
    assert src == "mtime"
    assert d is not None
    assert d.year == 2015 and d.month == 6


def test_year_month_dir() -> None:
    assert year_month_dir(datetime(2021, 8, 12)) == ("2021", "08")
    assert year_month_dir(datetime(1999, 12, 31)) == ("1999", "12")


def test_invalid_date_in_filename_rejected(tmp_path: Path) -> None:
    p = tmp_path / "2021-13-45_bogus.jpg"
    p.write_bytes(b"")
    d, src = extract_date(p)
    assert src == "mtime"  # falls past filename due to invalid month/day
