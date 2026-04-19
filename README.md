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

## Status

**Phase 0 complete** — repo bootstrapped, MIT licensed, ready for scaffolding.

See the per-phase setup docs (added in later phases) for backend, frontend, and Windows service install instructions.

## License

MIT — see [LICENSE](./LICENSE).
