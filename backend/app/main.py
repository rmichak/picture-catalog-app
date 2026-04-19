from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import settings
from app.db.base import Base, engine

_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Phase 1: just create tables. Alembic migrations land in Phase 2 once schema starts evolving.
    settings.ensure_dirs()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="picture-catalog-app",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# Serve the built React app, if present. In dev, the user runs Vite separately on :5173.
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Serve index.html for any unmatched path so the SPA router can handle it.
        index = _FRONTEND_DIST / "index.html"
        if not index.exists():
            return {"error": "frontend not built"}
        return FileResponse(index)
else:

    @app.get("/")
    def root():
        return {
            "name": "picture-catalog-app",
            "frontend": "not built — run `npm run dev` in frontend/ for development",
            "docs": "/docs",
        }
