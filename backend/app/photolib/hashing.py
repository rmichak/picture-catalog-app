from __future__ import annotations

import hashlib
from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError

from app.photolib import is_photo

_SHA_CHUNK = 1024 * 1024  # 1 MiB


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_SHA_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def phash_file(path: Path) -> str | None:
    """Perceptual hash for photos. Returns None for videos or unreadable images."""
    if not is_photo(path.name):
        return None
    try:
        with Image.open(path) as img:
            img.draft("RGB", (256, 256))
            return str(imagehash.phash(img))
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def hamming(a: str, b: str) -> int:
    """Hamming distance between two hex-encoded perceptual hashes of equal length."""
    if len(a) != len(b):
        raise ValueError(f"phash length mismatch: {len(a)} vs {len(b)}")
    ai = int(a, 16)
    bi = int(b, 16)
    return (ai ^ bi).bit_count()
