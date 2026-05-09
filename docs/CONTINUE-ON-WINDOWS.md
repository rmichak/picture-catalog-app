# Continuing on Windows — Reorganize phase handoff

This doc is a one-shot bridge from the Mac dev session (May 9, 2026) to the
Windows host where the reorganize CLI will actually run. Once the reorg is
done you can delete this file.

## What's in the repo right now

A new CLI, `backend/scripts/reorganize.py`, that physically reorganizes
Dropbox photos into `~/Dropbox/Pictures-Organized/YYYY/MM/`, quarantines
duplicates, and leaves an audit trail in the SQLite catalog DB.

Subcommands:

```
inventory  classify  plan  execute  verify
status     pause     resume          cancel <id>   undo <id>
```

New code:

- `backend/scripts/reorganize.py` — Typer CLI
- `backend/scripts/reorganize.toml` — source allowlist (in/out folders)
- `backend/app/photolib/{__init__,hashing,dates,dedupe,move,inventory}.py` — shared logic
- `backend/app/db/models.py` — added `ReorganizeRun` and `SourceFileAudit` tables
- `backend/pyproject.toml` — added `typer`, `tqdm`, `pillow-heif`
- `backend/tests/test_{hashing,dates,dedupe,move}.py` — 27 unit tests, all green

The approved design plan lives at
`~/.claude/plans/for-right-now-lets-replicated-twilight.md`
(only on the Mac — re-read it on Windows from your `~/.claude/` if synced,
or refer to the README + this doc, which capture the operative parts).

## Why we couldn't run it on the Mac

Smoke test on the Mac revealed that `~/Dropbox` is online-only / smart-sync.
Of ~75K in-scope photos, only ~2,650 had local content — the rest were
0-byte placeholder stubs. Mac also had only 10 GB free vs 31 GB needed to
materialize everything. So the reorg has to run somewhere with full
Dropbox sync + disk space.

Per project memory, the Windows host is where the production app lives
anyway. Running the reorg there is the natural fit.

## Bootstrap on Windows

Open PowerShell in the repo root after `git pull`:

```powershell
# 1. Toolchain (skip if already installed)
winget install -e astral-sh.uv     # Python env manager
winget install -e Python.Python.3.12   # if you don't have 3.11 or 3.12 yet

# 2. Backend env
cd backend
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"

# 3. Smoke-check imports
python -c "import typer, tqdm, pillow_heif, imagehash; from app.photolib.inventory import process_file; print('ok')"

# 4. Run the unit tests — should all pass
python -m pytest -q
```

Expected: 32 tests pass (5 from existing `test_health.py`, 27 from the new
photolib suite).

## Pre-flight checks before running for real

Run these and confirm before kicking off `inventory`:

### 1. Dropbox is locally synced

In the Dropbox app: Preferences → Sync. The in-scope folders need to be
"Local" (not "Online-only"). Easiest path is to right-click each in-scope
folder in File Explorer → "Smart Sync" → "Local". Or set the whole
`Dropbox` folder to local.

The in-scope folders are listed in `backend/scripts/reorganize.toml`:
`Camera Uploads`, `Camera Uploads (1)`, `pictures`, `gallery pictures`,
`Mobile Uploads`, `From Gina's Kitchen`.

Verify with PowerShell — every photo path should report a real size:

```powershell
Get-ChildItem -Path "$HOME\Dropbox\Camera Uploads" -File | Select-Object -First 5 Name, Length
```

If `Length` is mostly 0, sync hasn't completed.

### 2. Free disk space ≥ 31 GB

```powershell
Get-PSDrive C | Select-Object Used, Free
```

If short on space, free up before continuing — the reorg moves files
(doesn't double-store) but Dropbox will need elbow room for the rename
events to settle.

### 3. The Dropbox path matches the config

`backend\scripts\reorganize.toml` has:

```toml
source_root = "~/Dropbox"
```

`Path("~/Dropbox").expanduser()` resolves to `C:\Users\<you>\Dropbox` on
Windows. If your Dropbox lives elsewhere (e.g., `Dropbox (Personal)` for
some accounts, or a different drive), edit `source_root` accordingly.

## How to actually run the reorg

```powershell
# 1. Smoke test on a small folder first — strongly recommended.
#    Make a copy of `gallery pictures` to /tmp-style location, point a
#    custom config at it, run all five subcommands, undo, confirm clean.
#    See "Smoke test recipe" below.

# 2. Then for real:
python scripts\reorganize.py inventory       # ~hours: hash + EXIF + date for ~75K files
python scripts\reorganize.py classify         # minutes: group dups across 3 layers
python scripts\reorganize.py plan             # writes data\move-plan.csv — eyeball this!
python scripts\reorganize.py execute --dry-run # prints planned moves, no file changes
python scripts\reorganize.py execute          # apply the moves and quarantines
python scripts\reorganize.py verify           # re-hash destination, confirm 1:1
```

Between any two commands you can:

```powershell
python scripts\reorganize.py status   # progress, ETA, last path processed
```

To pause an active run from another terminal:

```powershell
python scripts\reorganize.py pause    # writes the sentinel file
# Active run finishes its current file, flushes DB, exits cleanly.
# Or hit Ctrl-C in the running terminal — same effect.
```

To resume:

```powershell
python scripts\reorganize.py resume   # picks up the most recent paused run
```

To roll back a completed `execute` run:

```powershell
python scripts\reorganize.py undo <run_id>   # walks the audit table backwards
```

## Smoke test recipe

Before running on the full collection, prove the pipeline end-to-end on a
small isolated copy:

```powershell
# Copy a small in-scope folder to a scratch area to avoid touching Dropbox
$smoke = "C:\reorg-smoketest"
Remove-Item -Recurse -Force $smoke -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$smoke\source", "$smoke\dest", "$smoke\data" | Out-Null
Copy-Item -Recurse "$HOME\Dropbox\From Gina's Kitchen" "$smoke\source\From Gina's Kitchen"

# Write a scratch config
@'
source_root = "C:/reorg-smoketest/source"
dest_root = "C:/reorg-smoketest/dest"
include_dirs = ["From Gina's Kitchen"]
include_root_files = []
exclude_dirs = []
'@ | Set-Content "$smoke\config.toml"

# Run the pipeline against the scratch dir using a separate DB
$env:PCA_DATA_DIR = "$smoke\data"
python scripts\reorganize.py inventory --config "$smoke\config.toml"
python scripts\reorganize.py classify --config "$smoke\config.toml"
python scripts\reorganize.py plan --config "$smoke\config.toml"
python scripts\reorganize.py execute --config "$smoke\config.toml"
python scripts\reorganize.py verify --config "$smoke\config.toml"

# Confirm files landed under YYYY/MM
Get-ChildItem -Recurse "$smoke\dest"

# Roll back to verify undo works
$lastRun = python scripts\reorganize.py status | Select-String "run #(\d+)" | ForEach-Object { $_.Matches.Groups[1].Value }
python scripts\reorganize.py undo $lastRun

# Cleanup
Remove-Item -Recurse -Force $smoke
Remove-Item Env:\PCA_DATA_DIR
```

If that completes cleanly, the real run is safe to start.

## Known gotchas on Windows

- **Long paths**: Some Dropbox subdirs may exceed Windows' default 260-char
  path limit. If you hit `[WinError 3] The system cannot find the path`,
  enable long paths via Group Policy or registry
  (`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`)
  and restart.
- **`ProcessPoolExecutor` uses spawn on Windows** (not fork). This means
  workers re-import the module, which the code already supports — but
  do NOT run the CLI from an interactive REPL.
- **Antivirus / Defender**: scanning every file the reorg touches can slow
  things ~5x. Consider adding `~\Dropbox\Pictures-Organized` and the repo's
  `backend\.venv` to the exclusion list during the run.
- **Pause sentinel** file lives at `<data_dir>\reorganize.pause` — that's
  `backend\data\reorganize.pause` by default, or `$env:PCA_DATA_DIR\reorganize.pause`.

## When the reorg is done

1. Spot-check `~/Dropbox/Pictures-Organized/_review-perceptual/` — these
   are the perceptual near-dups. Each group has a `group.json` sidecar
   with the candidates' phash distance, paths, dimensions. Approve or
   reject manually.
2. Spot-check `~/Dropbox/Pictures-Organized/_no-date/` — files where no
   reliable date could be derived. May need filename hints or a manual
   bucket assignment.
3. Once happy, you can delete `_duplicates/` and `_review-perceptual/`
   subtrees (they're not part of the canonical organized set).
4. Original empty `Camera Uploads`, `Camera Uploads (1)`, etc. folders
   can be removed manually whenever you're confident.
5. Then this doc has served its purpose — delete it.
