# Local Development Setup

This document explains how to run LoL Draft Analyzer locally for frontend or
backend changes.

**Setup A (pure browser dev) is the recommended path** — it works on exFAT
drives and gives you instant Vue/TypeScript hot-reload. Tauri-specific work
(Setup B/C) requires moving the repo to an NTFS drive because Tauri workspaces
need symlinks which exFAT does not support.

## Prerequisites

- **Windows 10 / 11**
- **Python 3.12** on PATH
- **Node.js 20 LTS** on PATH (includes `npm`)
- **LoL Client** installed (for champion-select detection testing)

## Setup A — Pure browser dev (works on exFAT)

Hot-reload for `.vue` and `.ts` files. No Tauri required. Fastest feedback loop.

### One-time setup (already done on your machine)

Python backend deps:

```powershell
cd "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\backend"
pip install -r requirements.txt
pip install -e .
```

Frontend deps via `npm` (NOT pnpm — pnpm workspaces need symlinks which
exFAT cannot create):

```powershell
cd "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\frontend"
npm install
```

**Local-only overrides already in place** (see `.git/info/exclude` — never
committed):

- `apps/frontend/.npmrc` with `workspaces=false` — tells npm to ignore the
  parent `pnpm-workspace.yaml`
- `apps/frontend/package.json` — has the `@counterpick/core: workspace:*`
  dep stripped (npm doesn't understand `workspace:*`, and Vite resolves
  `@counterpick/core` via `vite.config.ts` alias anyway)
- `apps/frontend/package-lock.json` — npm lockfile, never pushed

These three files are locally modified / untracked but hidden from Git via
`.git/info/exclude` + `git update-index --assume-unchanged`. You never need
to think about them.

### Daily startup

Open **two PowerShell windows**.

**Terminal 1 — Python backend:**

```powershell
cd "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\backend"
python backend.py --port 5000
```

Wait until you see:
```
 * Running on http://127.0.0.1:5000
[READY] port=5000 pid=...
```

**Terminal 2 — Vite dev server:**

```powershell
cd "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\frontend"
npm run dev
```

You'll see:
```
VITE v5.4.21  ready in xxx ms
➜  Local:   http://localhost:3000/
```

### Use

Open **http://localhost:3000** in your browser (Chrome / Edge / Firefox).

- Any edit in `apps/frontend/src/**/*.{vue,ts}` → instant HMR update
- Python backend changes → restart Terminal 1 (Ctrl+C, re-run the command)
- Browser DevTools (F12) work normally: console, network tab, Vue devtools
  extension
- Vite proxies `/api/*` calls to `http://localhost:5000` automatically

### Stop

Ctrl+C in both terminals, or close the PowerShell windows.

### What DOES work in this mode

- Vue component editing with live reload
- Pinia store debugging via Vue devtools
- API request/response inspection via browser network tab
- Full backend routes — recommendation engine, champion lookup, matchups,
  synergies, LCU detection
- Supabase connection direct (not CDN) because `python backend.py` loads
  `.env` with `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`

### What does NOT work in this mode

- Tauri IPC (`window.__TAURI__` is undefined in plain browser)
  → `getBackendURL()` returns `''` and uses the Vite proxy instead
  → `get_backend_port`, `restart_backend`, `backend-disconnected` events
    are stubbed / no-op
- Tauri auto-updater
- Windows Job Object sidecar lifecycle (Python runs as a standalone process)
- Actual `.msi` install behavior

### Example: edit a Vue component

1. Both terminals running (backend + vite)
2. Browser on http://localhost:3000
3. Edit `apps/frontend/src/App.vue` — save
4. Browser tab reloads automatically (HMR), state preserved where possible
5. Open DevTools → Console to see any errors

## Setup B / C — Tauri dev + local MSI build

Requires moving the repo to an NTFS drive. If you later decide to test
Tauri-specific code locally:

```powershell
git clone https://github.com/Chertixd/LoL-Draft-Helper.git C:\Users\till-\repos\LoL-Draft-Helper
cd C:\Users\till-\repos\LoL-Draft-Helper
copy "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\backend\.env" ".\counterpick-app\apps\backend\.env"
copy "F:\Dokumente\Archiv\Riot Api\supabase-dataset-updater\.env" ".\supabase-dataset-updater\.env"
cd counterpick-app
pnpm install          # works on NTFS
pnpm tauri dev        # Setup B: full Tauri + HMR
# or
pnpm tauri build      # Setup C: produces MSI + NSIS in src-tauri/target/release/bundle/
```

Also needs Rust (`rustup-init`) + MSVC C++ build tools.

Until you do that move, Tauri-specific bugs (updater, sidecar lifecycle, IPC)
can only be tested by tagging a release and letting CI build — slower but
works.

## Troubleshooting

### Vite shows `localhost:3000 refused`

Check Terminal 2 — is `npm run dev` actually running? Look for `VITE v5.x.x ready` line.

### Backend "Address already in use"

Kill stray Python processes:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

Or use a different port: `python backend.py --port 5001` — then edit
`apps/frontend/vite.config.ts` `proxy` target to match.

### `npm install` errors with `EISDIR` or `workspace:*`

Something disturbed the local setup. Rebuild it:

```powershell
cd "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\frontend"
Remove-Item -Recurse -Force node_modules, package-lock.json -ErrorAction SilentlyContinue
# Make sure .npmrc exists with: workspaces=false
npm install
```

If that fails because `package.json` has been re-synced to pin
`@counterpick/core: workspace:*`:

```powershell
# Strip the line temporarily
node -e "const fs=require('fs'); const p=JSON.parse(fs.readFileSync('package.json')); delete p.dependencies['@counterpick/core']; fs.writeFileSync('package.json', JSON.stringify(p,null,4));"
npm install
```

Then re-hide it from git:

```powershell
git update-index --assume-unchanged package.json
```

### Champion select not detected while LoL is running

The backend finds LoL by running `Get-CimInstance Win32_Process` to read
the `LeagueClientUx.exe` command line. Verify directly:

```powershell
Get-CimInstance Win32_Process -Filter "name = 'LeagueClientUx.exe'" | Select-Object -ExpandProperty CommandLine
```

If that returns empty while LoL is running, PowerShell execution policy may
be blocking WMI queries. Check with `Get-ExecutionPolicy`; should be
`RemoteSigned` or more permissive.

### Browser shows old code after edit

Hard-refresh: Ctrl+Shift+R. If still stale, check that Vite actually picked
up the change (Terminal 2 prints the updated file). If HMR truly broke,
restart `npm run dev`.

### Backend crashes immediately after start

Read the traceback in Terminal 1. Most common: missing `.env` (Supabase vars
not set), or a Python dep wasn't installed. Re-run:

```powershell
cd "F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\backend"
pip install -r requirements.txt
pip install -e .
```

## Project structure

```
counterpick-app/
├── apps/
│   ├── frontend/       Vue 3 + Vite + TypeScript — Setup A targets this
│   └── backend/        Flask + Flask-SocketIO — python backend.py
├── packages/
│   └── core/           Shared TypeScript types (consumed via @counterpick/core alias)
└── src-tauri/          Rust + Tauri v2 — Setup B/C only (needs NTFS)

supabase-dataset-updater/
└── scripts/            Python ETL + CDN JSON exporter (runs in CI)

.github/workflows/
├── build-smoke.yml     Every push to master — PyInstaller sanity check
├── release.yml         v* tag push — builds MSI + NSIS + publishes latest.json
└── update-dataset.yml  Daily 12:00 UTC — Supabase ETL + CDN refresh
```

## Workflow when you ship changes

1. Make edits under `apps/frontend/` or `apps/backend/` (Setup A catches most)
2. `git add <files>` + `git commit` — exclude list keeps the local-only
   package.json / .npmrc / package-lock.json out automatically
3. `git push origin master` — CI runs build-smoke
4. When you have multiple changes ready for users: `git tag v1.0.X` +
   `git push origin v1.0.X` — CI builds MSI/NSIS, publishes latest.json,
   installed clients get the auto-update prompt

For Tauri-only fixes (sidecar lifecycle, IPC commands, Rust code): move
the repo to NTFS (Setup B/C) or test via tagged pre-release builds.
