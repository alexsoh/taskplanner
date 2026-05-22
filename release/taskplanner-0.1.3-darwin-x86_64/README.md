# TaskPlanner

Profile-based weekly action scheduler. Fires PiyoAI-compatible notifications (MQTT, Telegram, HTTP, Script, NVR) on **day + time** schedules in each profile's timezone.

## Requirements

- macOS or Linux: `curl` or `wget` (for vendored Python download on first run)
- Node.js 20+ on PATH when building the frontend (or use release zips with pre-built `static/`)
- No PiyoAI runtime dependency — notification configs match PiyoAI; executors live in `tp/notify/`

## Quick start

| Action | Command |
|--------|---------|
| First-time setup (Unix) | `./setup.sh` |
| Dev server (Unix) | `./serve.sh` or `./serve.sh 8200` |
| Upgrade (Unix) | `./upgrade.sh --source-path /path/to/new-taskplanner` or `./upgrade.sh --token evlx_...` |
| Update (alias) | `./update.sh` (same as `upgrade.sh`) |
| Publish release | `./scripts/publish-release.sh --patch -m "..."` |
| Windows setup | `setup.bat` or `.\setup.ps1` |
| Windows dev server | `.\serve.ps1` |

Default URL: http://127.0.0.1:8200

### Unix details

```bash
cd taskplanner
./setup.sh          # venv + pip + frontend → static/
./serve.sh          # same bootstrap if needed, then uvicorn with --reload
./serve.sh --skip-build   # skip npm when static/ is already built
```

Environment (optional):

- `TASKPLANNER_PORT` — default `8200`
- `TASKPLANNER_PYTHON` — use a specific Python 3.10+ for venv creation
- `TASKPLANNER_PBS_TAG`, `TASKPLANNER_PYTHON_MM` — standalone CPython download pins

### Upgrade

`upgrade.sh` is the canonical name; `update.sh` forwards to it.

- Local tree: `./upgrade.sh --source-path ../taskplanner-new`
- Evalex download: `./upgrade.sh --token evlx_...` (requires `taskplanner` app registered on the evalex server)

Upgrades preserve `data/` (SQLite). Backups land under `backups/`.

### Publish

```bash
./scripts/publish-release.sh --patch -m "Brief release notes"
./scripts/publish-release.sh --dry-run   # preview bump only
```

Bumps `tp/__init__.py` `__version__`, builds `static/`, updates `version.txt` and `summary.txt`, then commit, tag, push, and `gh release` (unless `--no-gh`).

## Development

```bash
# After ./setup.sh
./serve.sh --skip-build    # backend only if static/ is current

# Or separate terminals:
# Terminal 1: ./serve.sh --skip-build
# Terminal 2: cd frontend && npm run dev
```

## Data

SQLite database: `data/taskplanner.db`

Scripts run with the same privileges as the TaskPlanner process (same as PiyoAI script notifications).

## API

- `GET /api/health` — `{"ok": true, "version": "0.1.0"}`
