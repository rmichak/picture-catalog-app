# picture-catalog-app

A personal, self-hosted catalog for a family photo collection living in Dropbox.

- **Catalog without disturbing originals** — photos stay in Dropbox; the app only reads.
- **Find duplicates** — exact matches via Dropbox's content hash, near-duplicates via perceptual hashing.
- **Recognize family** — local face recognition (no cloud AI). Teach it once by labeling faces; it auto-tags the rest.
- **Search by people, dates, events** — e.g., "all three kids at a birthday party."
- **Always-on** — runs as a Windows service, polls Dropbox for new photos every 15 minutes, reachable from any device on the home LAN.

## Architecture

```
   Any device on home LAN                Windows desktop (always-on host)
 ┌──────────────────────┐              ┌────────────────────────────────────┐
 │  Browser (UI)        │ ◄── HTTP ──► │  FastAPI backend (Python 3.11+)    │
 │  React + Vite        │   :8000      │  Running as Windows Service (NSSM) │
 └──────────────────────┘              └─────────────────┬──────────────────┘
                                                         │
                          ┌──────────────────────────────┼──────────────────────────────┐
                          │                              │                              │
                  ┌───────▼───────┐              ┌───────▼────────┐             ┌───────▼────────┐
                  │  SQLite DB    │              │  Local cache   │             │  Dropbox API   │
                  │  (catalog +   │              │  thumbnails,   │             │  (read-only    │
                  │   vec0 idx)   │              │  face crops    │             │   via OAuth)   │
                  └───────────────┘              └────────────────┘             └────────────────┘
                                                         │
                                              ┌──────────▼──────────┐
                                              │  ONNX Runtime       │
                                              │  + DirectML EP      │
                                              │  → AMD Radeon GPU   │
                                              └─────────────────────┘
```

## Cross-machine workflow

Development happens on a Mac; the app is hosted on a Windows desktop.

```
┌──────────────┐   git push    ┌─────────┐   git pull   ┌─────────────────┐
│  Mac (dev)   │ ────────────► │ GitHub  │ ──────────► │  Windows (host) │
└──────────────┘               └─────────┘              └─────────────────┘
```

## Requirements

- **Python 3.11 or 3.12** (3.13 not yet supported by InsightFace / onnxruntime-directml wheels)
- **Node.js 20+ and npm**
- **[uv](https://github.com/astral-sh/uv)** for Python env management (`brew install uv` on Mac, `winget install astral-sh.uv` on Windows)
- **A Dropbox app** registered at https://www.dropbox.com/developers/apps (see "Dropbox setup" below)
- **Windows host only**: Visual C++ Build Tools + NSSM (added in Phase 5)

## Quick start (development on Mac)

```bash
git clone https://github.com/rmichak/picture-catalog-app.git
cd picture-catalog-app

# 1. Configure Dropbox credentials
cp backend/.env.example backend/.env
# ...edit backend/.env and paste your Dropbox app key + secret...

# 2. Run both servers + open the browser
./scripts/start.sh
```

This starts:

- Backend: <http://localhost:8000> (FastAPI + Swagger UI at `/docs`)
- Frontend (dev mode with hot reload): <http://localhost:5173>

The Vite dev server proxies `/api/*` to the backend, so you can develop against `http://localhost:5173`.

For a production-ish run (single port, no Vite dev server):

```bash
cd frontend && npm run build && cd -
cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

## Dropbox setup

1. Go to <https://www.dropbox.com/developers/apps> and click **Create app**.
2. Pick **Scoped access** + **App folder** (recommended — sandboxed) or **Full Dropbox** if you want to point at an existing folder.
3. Name your app (e.g., `picture-catalog-app-randy`).
4. On the app's settings page:
   - Add this redirect URI: `http://localhost:8000/api/auth/dropbox/callback`
     (When hosting on Windows for LAN access, also add `http://<windows-ip>:8000/api/auth/dropbox/callback`.)
   - Under **Permissions**, enable: `files.metadata.read`, `files.content.read`, `account_info.read`. Submit.
5. Copy the **App key** and **App secret** into `backend/.env` as `PCA_DROPBOX_APP_KEY` and `PCA_DROPBOX_APP_SECRET`.
6. Restart the backend. In the app, go to **Settings → Connect Dropbox**.

## Project layout

```
picture-catalog-app/
├── backend/             # FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── api/         # HTTP routes (health, auth, photos)
│   │   ├── db/          # SQLAlchemy models, session
│   │   ├── dropbox_svc/ # Dropbox OAuth + client wrapper
│   │   ├── indexer/     # Folder walker, photos table populator
│   │   ├── faces/       # (Phase 3) face detection + embeddings
│   │   ├── events/      # (Phase 4) auto-event detection
│   │   ├── search/      # (Phase 4) filter engine
│   │   ├── dedupe/      # (Phase 2) duplicate detection
│   │   ├── config.py    # Pydantic settings (env-driven)
│   │   └── main.py      # FastAPI entry point
│   ├── tests/           # pytest
│   ├── data/            # gitignored: SQLite DB, thumbnails, tokens, models
│   └── pyproject.toml
├── frontend/            # React + Vite + TS + Tailwind
│   └── src/
│       ├── api/         # typed fetch client
│       ├── components/  # Layout, etc.
│       └── pages/       # Library, Settings
├── scripts/
│   ├── start.sh         # macOS/Linux dev launcher
│   └── start.bat        # Windows dev launcher
├── LICENSE              # MIT
└── README.md
```

## Roadmap

- **Phase 0** — repo bootstrap. ✅
- **Phase 1** — walking skeleton: FastAPI backend, React UI, Dropbox OAuth, basic folder indexing into SQLite. ✅
- **Phase 2** — thumbnail cache, perceptual hashing, dedupe review UI.
- **Phase 3** — InsightFace + ONNX Runtime/DirectML face pipeline; "Who is this?" learning loop.
- **Phase 4** — auto event detection, multi-filter search (people + dates + events).
- **Phase 5** — Windows Service install via NSSM, 15-min Dropbox poll, daily SQLite backup.

## Developer commands

```bash
# Backend tests
cd backend && .venv/bin/pytest -q

# Backend type & lint
cd backend && .venv/bin/ruff check .

# Frontend type-check
cd frontend && npm run lint

# Frontend production build
cd frontend && npm run build
```

## License

MIT — see [LICENSE](./LICENSE).
