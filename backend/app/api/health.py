from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.db import SessionLocal
from app.dropbox_svc import tokens_exist

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    db_reachable = False
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
            db_reachable = True
    except Exception:
        db_reachable = False
    return {
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "dropbox_connected": tokens_exist(),
        "db_reachable": db_reachable,
    }
