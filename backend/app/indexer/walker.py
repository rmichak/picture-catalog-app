"""Phase 1 indexer: walk a Dropbox folder, upsert Photo rows.

Phases 2+ will add thumbnail generation, EXIF parsing, perceptual hashing, and
queueing for face detection.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Photo
from app.dropbox_svc import DropboxClient


@dataclass
class IndexResult:
    scanned: int
    inserted: int
    updated: int
    skipped: int


def walk_and_index(
    session: Session,
    client: DropboxClient,
    folder: str = "",
    recursive: bool = True,
) -> IndexResult:
    scanned = inserted = updated = skipped = 0

    for f in client.list_image_files(folder=folder, recursive=recursive):
        scanned += 1
        existing = session.execute(
            select(Photo).where(Photo.dropbox_id == f.id)
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                Photo(
                    dropbox_id=f.id,
                    dropbox_path=f.path,
                    name=f.name,
                    size_bytes=f.size,
                    content_hash=f.content_hash,
                    server_modified=f.server_modified,
                    status="discovered",
                )
            )
            inserted += 1
        else:
            changed = False
            if existing.dropbox_path != f.path:
                existing.dropbox_path = f.path
                changed = True
            if existing.content_hash != f.content_hash:
                existing.content_hash = f.content_hash
                # content changed -> needs full reprocessing
                existing.status = "discovered"
                changed = True
            if existing.server_modified != f.server_modified:
                existing.server_modified = f.server_modified
                changed = True
            if changed:
                updated += 1
            else:
                skipped += 1

        # Commit in batches of 200 to keep memory bounded on huge libraries.
        if scanned % 200 == 0:
            session.commit()

    session.commit()
    return IndexResult(scanned=scanned, inserted=inserted, updated=updated, skipped=skipped)
