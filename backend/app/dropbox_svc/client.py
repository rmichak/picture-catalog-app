"""Thin wrapper around the Dropbox SDK that uses the stored refresh token.

Why a wrapper:
- Centralizes the refresh-token boilerplate so every caller doesn't redo it.
- Lets us add retry/backoff, metrics, and rate-limit handling in one place later.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from dropbox import Dropbox
from dropbox.files import FileMetadata, FolderMetadata

from app.config import settings
from app.dropbox_svc.auth import load_tokens

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".tiff", ".bmp"}


@dataclass
class DropboxFile:
    id: str
    path: str
    name: str
    size: int
    content_hash: str | None
    server_modified: datetime | None


class DropboxClient:
    def __init__(self, dbx: Dropbox):
        self._dbx = dbx

    @property
    def raw(self) -> Dropbox:
        return self._dbx

    def list_image_files(self, folder: str = "", recursive: bool = True) -> Iterator[DropboxFile]:
        """Walk a folder and yield image files (filtered by extension)."""
        result = self._dbx.files_list_folder(path=folder, recursive=recursive)
        while True:
            for entry in result.entries:
                if not isinstance(entry, FileMetadata):
                    continue
                lower = entry.name.lower()
                if not any(lower.endswith(ext) for ext in _IMAGE_EXTS):
                    continue
                yield DropboxFile(
                    id=entry.id,
                    path=entry.path_display or entry.path_lower,
                    name=entry.name,
                    size=entry.size,
                    content_hash=getattr(entry, "content_hash", None),
                    server_modified=entry.server_modified,
                )
            if not result.has_more:
                break
            result = self._dbx.files_list_folder_continue(result.cursor)

    def list_folders(self, folder: str = "") -> list[str]:
        """One-level folder listing for the UI's folder picker."""
        result = self._dbx.files_list_folder(path=folder, recursive=False)
        out: list[str] = []
        while True:
            for entry in result.entries:
                if isinstance(entry, FolderMetadata):
                    out.append(entry.path_display or entry.path_lower)
            if not result.has_more:
                break
            result = self._dbx.files_list_folder_continue(result.cursor)
        return out

    def account_info(self) -> dict[str, str]:
        acct = self._dbx.users_get_current_account()
        return {
            "name": acct.name.display_name,
            "email": acct.email,
            "account_id": acct.account_id,
        }


def get_client() -> DropboxClient | None:
    """Construct a DropboxClient using the persisted refresh token, or None if unauthenticated."""
    tokens = load_tokens()
    if tokens is None:
        return None
    if not settings.dropbox_app_key or not settings.dropbox_app_secret:
        raise RuntimeError("Dropbox app key/secret not configured.")
    dbx = Dropbox(
        oauth2_refresh_token=tokens.refresh_token,
        app_key=settings.dropbox_app_key,
        app_secret=settings.dropbox_app_secret,
    )
    return DropboxClient(dbx)
