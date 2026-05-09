from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from app.photolib.hashing import hamming, phash_file, sha256_file


def test_sha256_matches_stdlib(tmp_path: Path) -> None:
    p = tmp_path / "data.bin"
    p.write_bytes(b"the quick brown fox" * 1000)
    assert sha256_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_phash_returns_hex_for_jpeg(tmp_path: Path) -> None:
    p = tmp_path / "img.jpg"
    Image.new("RGB", (64, 64), color=(120, 30, 200)).save(p, "JPEG")
    h = phash_file(p)
    assert h is not None
    assert len(h) == 16
    int(h, 16)


def test_phash_none_for_video_extension(tmp_path: Path) -> None:
    p = tmp_path / "clip.mov"
    p.write_bytes(b"not actually a video")
    assert phash_file(p) is None


def test_phash_none_for_corrupt_image(tmp_path: Path) -> None:
    p = tmp_path / "corrupt.jpg"
    p.write_bytes(b"\xff\xd8\xff" + b"junk" * 10)
    assert phash_file(p) is None


def test_hamming_distance() -> None:
    assert hamming("ff" * 8, "ff" * 8) == 0
    assert hamming("0" * 16, "f" * 16) == 64
    assert hamming("00ff" + "0" * 12, "00fe" + "0" * 12) == 1


def test_hamming_rejects_unequal_length() -> None:
    with pytest.raises(ValueError):
        hamming("ff", "ffff")
