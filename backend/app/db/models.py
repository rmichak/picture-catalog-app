from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    dropbox_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    dropbox_path: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    content_hash: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    phash: Mapped[str | None] = mapped_column(String, index=True, nullable=True)

    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    server_modified: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # processing status: 'discovered' -> 'metadata' -> 'thumbnailed' -> 'faces_done'
    status: Mapped[str] = mapped_column(String, default="discovered", index=True)

    # soft-hide (e.g., user marked it as a duplicate to ignore)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    faces: Mapped[list[Face]] = relationship(back_populates="photo", cascade="all, delete-orphan")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    is_family: Mapped[bool] = mapped_column(Boolean, default=False)
    centroid_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    faces: Mapped[list[Face]] = relationship(back_populates="person")


class Face(Base):
    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", ondelete="SET NULL"), index=True, nullable=True
    )

    bbox_x: Mapped[int] = mapped_column(Integer)
    bbox_y: Mapped[int] = mapped_column(Integer)
    bbox_w: Mapped[int] = mapped_column(Integer)
    bbox_h: Mapped[int] = mapped_column(Integer)

    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    crop_path: Mapped[str | None] = mapped_column(String, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    photo: Mapped[Photo] = relationship(back_populates="faces")
    person: Mapped[Person | None] = relationship(back_populates="faces")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EventPhoto(Base):
    __tablename__ = "event_photos"
    __table_args__ = (UniqueConstraint("event_id", "photo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)


class PhotoTag(Base):
    __tablename__ = "photo_tags"
    __table_args__ = (UniqueConstraint("photo_id", "tag_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AlbumPhoto(Base):
    __tablename__ = "album_photos"
    __table_args__ = (UniqueConstraint("album_id", "photo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), index=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)


class DropboxCursor(Base):
    """Stores resume cursors for the Dropbox folder walker so indexing is incremental."""

    __tablename__ = "dropbox_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    folder_path: Mapped[str] = mapped_column(String, unique=True, index=True)
    cursor: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


Index("ix_photos_taken_status", Photo.taken_at, Photo.status)


class ReorganizeRun(Base):
    """One row per invocation of a reorganize subcommand. Drives progress/pause/resume."""

    __tablename__ = "reorganize_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="running", index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    files_total: Mapped[int] = mapped_column(Integer, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, default=0)
    last_path_processed: Mapped[str | None] = mapped_column(Text, nullable=True)

    config_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceFileAudit(Base):
    """Ledger of every source file the reorganize tool has touched. Source of truth for undo."""

    __tablename__ = "source_file_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reorganize_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )

    original_path: Mapped[str] = mapped_column(Text, index=True)
    target_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    action: Mapped[str] = mapped_column(String, index=True)
    group_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)
    dup_layer: Mapped[str | None] = mapped_column(String, nullable=True)
    date_source: Mapped[str | None] = mapped_column(String, nullable=True)

    sha256: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    phash: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mtime_ts: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)

    executed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


Index("ix_audit_sha256_action", SourceFileAudit.sha256, SourceFileAudit.action)
Index("ix_audit_run_action", SourceFileAudit.run_id, SourceFileAudit.action)
