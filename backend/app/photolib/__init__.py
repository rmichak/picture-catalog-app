"""Local-filesystem photo utilities used by the reorganize CLI.

This package is intentionally decoupled from `app.dropbox_svc` — it operates
on filesystem paths and does no network I/O.
"""

from __future__ import annotations

from pillow_heif import register_heif_opener

# Pillow can't read .heic without this. Safe to call multiple times.
register_heif_opener()

PHOTO_EXTS = frozenset(
    {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tiff", ".tif", ".webp", ".bmp"}
)
VIDEO_EXTS = frozenset({".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".3gp"})
MEDIA_EXTS = PHOTO_EXTS | VIDEO_EXTS


def is_photo(path_or_name: str) -> bool:
    return _ext(path_or_name) in PHOTO_EXTS


def is_video(path_or_name: str) -> bool:
    return _ext(path_or_name) in VIDEO_EXTS


def is_media(path_or_name: str) -> bool:
    return _ext(path_or_name) in MEDIA_EXTS


def _ext(s: str) -> str:
    i = s.rfind(".")
    return s[i:].lower() if i >= 0 else ""
