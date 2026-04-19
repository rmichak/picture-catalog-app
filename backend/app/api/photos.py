from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.db import SessionLocal
from app.db.models import Photo
from app.dropbox_svc import get_client
from app.indexer import walk_and_index

router = APIRouter(tags=["photos"])


class PhotoOut(BaseModel):
    id: int
    dropbox_path: str
    name: str
    size_bytes: int
    content_hash: str | None
    status: str

    model_config = {"from_attributes": True}


class ListResponse(BaseModel):
    total: int
    items: list[PhotoOut]


class IndexStartResponse(BaseModel):
    started: bool
    folder: str
    message: str


class FoldersResponse(BaseModel):
    folder: str
    children: list[str]


@router.get("/photos", response_model=ListResponse)
def list_photos(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    with SessionLocal() as s:
        total = s.execute(select(func.count(Photo.id))).scalar_one()
        rows = (
            s.execute(
                select(Photo)
                .where(Photo.hidden.is_(False))
                .order_by(Photo.id.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return ListResponse(total=total, items=[PhotoOut.model_validate(p) for p in rows])


@router.get("/folders", response_model=FoldersResponse)
def list_folders(folder: str = ""):
    client = get_client()
    if client is None:
        raise HTTPException(status_code=400, detail="Not connected to Dropbox.")
    try:
        children = client.list_folders(folder=folder)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dropbox error: {e}") from e
    return FoldersResponse(folder=folder, children=children)


def _do_index(folder: str) -> None:
    client = get_client()
    if client is None:
        return
    with SessionLocal() as s:
        walk_and_index(s, client, folder=folder, recursive=True)


@router.post("/index/start", response_model=IndexStartResponse)
def start_index(background: BackgroundTasks, folder: str = ""):
    client = get_client()
    if client is None:
        raise HTTPException(status_code=400, detail="Not connected to Dropbox.")
    background.add_task(_do_index, folder)
    return IndexStartResponse(
        started=True,
        folder=folder or "/",
        message="Indexing started in the background. Refresh /photos to watch progress.",
    )
