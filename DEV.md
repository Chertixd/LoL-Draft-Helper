# Local Development Setup

This document explains how to run LoL Draft Analyzer locally for frontend or
backend changes without a full Tauri build cycle.

## One-time setup

### Prerequisites

- **Windows 10 / 11**
- **Python 3.12** on PATH
- **Node.js 20 LTS** on PATH
- **pnpm 9.2 or newer** (`npm install -g pnpm`)
- **NTFS volume** for the project (do NOT use exFAT — pnpm workspaces need
  symlinks which exFAT cannot create; a 5 min move to `C:\` solves this
  permanently)

### First-time install

Clone the repo to an NTFS volume (e.g. `C:\Users\till-\repos\LoL-Draft-Helper`):

```powershell
git clone https://github.com/Chertixd/LoL-Draft-Helper.git C:\Users\till-\repos\LoL-Draft-Helper
cd C:\Users\till-\repos\LoL-Draft-Helper
```

Copy `.env` files (they are gitignored so they don't travel with the clone):

```powershell
copy "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\backend\.env" ".\counterpick-app\apps\backend\.env"
copy "F:\Dokumente\Archiv\Riot Api\supabase-dataset-updater\.env" ".\supabase-dataset-updater\.env"
```

Install Python backend deps:

```powershell
cd counterpick-app\apps\backend
pip install -r requirements.txt
pip install -e .
cd ..\..
```

Install frontend deps:

```powershell
pnpm install
```

## Setup A — Pure browser dev (recommended for frontend work)

Hot-reload for `.vue` and `.ts` files. No Tauri. Fastest feedback loop.

### Daily startup

Open **two PowerShell windows** at the repo root.

**Terminal 1 — Backend:**

```powershell
cd counterpick-app\apps\backend
python backend.py --port 5000
```

Wait until you see:
```
 * Running on http://127.0.0.1:5000
[READY] port=5000 pid=...
```

**Terminal 2 — Vite dev server:**

```powershell
cd counterpick-app\apps\frontend
pnpm dev
```

This prints:
```
  VITE v5.x.x  ready in xxx ms
  ➜  Local:   http://localhost:3000/
```

### Use

Open http://localhost:3000 in your browser.

- Vite proxies `/api/*` calls to `http://localhost:5000` automatically
- Any edit in `apps/frontend/src/**/*.{vue,ts}` → instant HMR update
- Python backend changes → restart Terminal 1 manually (no hot-reload for Python)
- Browser DevTools (F12) work normally — full console, network, Vue devtools

### What DOES work in this mode

- Vue component editing with live reload
- Pinia store debugging
- API request/response inspection via browser network tab
- Backend route testing with real Supabase data (not CDN) because the
  `python backend.py` invocation loads `.env` directly
- Recommendation engine, champion lookup, all HTTP routes

### What does NOT work in this mode

- Tauri IPC (`window.__TAURI__` is undefined in a plain browser)
  → `getBackendURL()` returns `''` and uses the Vite proxy instead
  → `get_backend_port`, `restart_backend`, `backend-disconnected` events
    are all stubbed
- Tauri updater (doesn't exist in browser)
- Windows Job Object sidecar lifecycle (backend runs standalone)
- Actual `.msi` install behavior
- LCU auth / champion select detection *only works while LoL is running on
  your machine* — the backend reads the LCU lockfile regardless of whether
  we're in Tauri or browser mode

### Stop

Ctrl+C in both terminals, or just close the PowerShell windows.

## Setup B — Tauri dev (for sidecar lifecycle / IPC work)

Use this when you need `window.__TAURI__`, the Rust host, or the updater.

```powershell
cd counterpick-app
pnpm tauri dev
```

This starts Vite internally + spawns a native Python backend + opens the Tauri
webview. HMR for the Vue code still works. Python backend changes require
Ctrl+C and restart.

Requires Rust installed (`rustup-init`) and the MSVC C++ build tools
(installed with Visual Studio or standalone Build Tools).

## Setup C — Local MSI/NSIS build

Only for testing the actual install flow. Takes 10-15 min.

```powershell
cd counterpick-app
pnpm tauri build
```

Output:
- `src-tauri\target\release\bundle\msi\*.msi`
- `src-tauri\target\release\bundle\nsis\*-setup.exe`

The CI pipeline does this on every `v*` tag push — you rarely need local
builds.

## Troubleshooting

### `pnpm install` crashes with `EISDIR` or symlink errors

You are on an exFAT volume. Move the repo to NTFS (usually `C:`). See the
first section of this file.

### Vite shows `localhost:3000 refused` but backend is running

Check `vite.config.ts` — the dev server port is 3000, and the proxy target
is `http://localhost:5000`. Your `python backend.py --port 5000` must match.

### Backend "Address already in use"

Another Python process is still holding port 5000. Either kill it:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

Or use a different port: `python backend.py --port 5001` and adjust
`vite.config.ts` proxy target.

### Champion select not detected while LoL is running

The backend uses `Get-CimInstance Win32_Process` to find the
`LeagueClientUx.exe` process and parse `--app-port` / `--remoting-auth-token`
from its command line. Check it's really there:

```powershell
Get-CimInstance Win32_Process -Filter "name = 'LeagueClientUx.exe'" | Select-Object -ExpandProperty CommandLine
```

If it's empty but LoL is running, PowerShell execution policy may be
blocking the query. Check with `Get-ExecutionPolicy`.

## Project structure

```
counterpick-app/
├── apps/
│   ├── frontend/       Vue 3 + Vite + TypeScript — Setup A targets this
│   └── backend/        Flask + Flask-SocketIO — python backend.py
├── packages/
│   └── core/           Shared TypeScript types (consumed via @counterpick/core alias)
└── src-tauri/          Rust + Tauri v2 — Setup B/C only

supabase-dataset-updater/
└── scripts/            Python ETL + CDN JSON exporter (runs in CI)

.github/workflows/
├── build-smoke.yml     Every push to master — PyInstaller sanity check
├── release.yml         v* tag push — builds MSI + NSIS + publishes latest.json
└── update-dataset.yml  Daily 12:00 UTC — Supabase ETL + CDN refresh
```
