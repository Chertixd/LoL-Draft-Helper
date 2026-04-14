# Delivery-Form Design — LoL Draft Analyzer v1

**Date:** 2026-04-14
**Author:** Till (with Claude as brainstorming partner)
**Status:** Approved for implementation planning
**Topic scope:** How the LoL Draft Analyzer is delivered to and executed by end users.
**Out of scope:** UX polish of the Vue frontend, recommendation-engine tuning, publishing readiness (legal/license). Those are separate specs.

---

## 1. Context & Motivation

The LoL Draft Analyzer currently runs as:
- A Flask + Flask-SocketIO backend on `localhost:5000` (manually started via `python backend.py`).
- A Vue 3 frontend served by Vite on `localhost:5173` (manually started via `pnpm dev`).
- Data persisted in a Supabase PostgreSQL project; ETL updates it daily via GitHub Actions.

The stated goal is to make this tool publicly available on GitHub to non-technical LoL players (people who would download an installer, not run `pip install`). The current two-step manual startup, the Python/Node toolchain requirement, and the hardcoded Supabase credentials are all blockers for that audience.

A prior conversation ruled out four adjacent concerns as out-of-scope for this spec:
- GitHub publishing readiness (license, legal, README) — separate spec.
- Overlay UX improvements (graphics performance, hover detection) — separate spec, though hover detection is carried into this spec as a targeted fix because its root cause likely sits in code we touch anyway (see §7.1).
- Backend-stack replacement (Flask → FastAPI) — not pursued; Flask is adequate.
- macOS/Linux builds — backlog.

## 2. Decision Summary

1. **Delivery form:** Tauri desktop application (Windows-only for v1), with the existing Python backend bundled as a PyInstaller sidecar binary.
2. **IPC between Vue and Python:** HTTP + WebSocket on a dynamically-allocated localhost port (not Tauri IPC bridge). This preserves the existing Flask/Socket.IO architecture unchanged.
3. **Data delivery:** Clients no longer connect to Supabase. A new GitHub-Actions export step dumps the relevant tables to JSON after each ETL run and publishes them to GitHub Pages. Clients fetch JSONs from that CDN on startup and cache locally. Supabase remains the source of truth for the ETL pipeline but is invisible to end users.
4. **Platforms for v1:** Windows only. No code signing. AV false-positive mitigation via PyInstaller-without-UPX + Microsoft false-positive submissions + README guidance.
5. **Auto-update:** Tauri updater with GitHub Releases as the update channel.

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Tauri Desktop App (Installer: .msi / portable .exe)    │
│                                                         │
│  ┌──────────────────┐      ┌──────────────────────┐    │
│  │ Webview          │◄────►│ Tauri Host (Rust)    │    │
│  │ (Vue 3 Frontend) │ IPC  │ - Window management  │    │
│  │ unchanged        │      │ - Sidecar lifecycle  │    │
│  └────────┬─────────┘      │ - Auto-updater       │    │
│           │                 │ - Dynamic port alloc │    │
│           │                 └──────────┬───────────┘    │
│           │ HTTP + Socket.IO           │ spawn/kill     │
│           ▼                            ▼                │
│  ┌────────────────────────────────────────────────┐     │
│  │ Python Sidecar (PyInstaller onefile backend.exe)│    │
│  │  - Flask + Flask-SocketIO (unchanged)          │     │
│  │  - recommendation_engine.py (unchanged)        │     │
│  │  - league_client_*.py (unchanged)              │     │
│  │  - json_repo.py (NEW, replaces supabase_repo) │     │
│  │  - Binds to 127.0.0.1:<dynamic-port>           │     │
│  └──────────────────────┬─────────────────────────┘     │
│                         │ HTTPS (read-only)             │
└─────────────────────────┼───────────────────────────────┘
                          ▼
                ┌─────────────────────┐
                │ GitHub Pages (CDN)  │
                │  data/*.json        │
                └──────────▲──────────┘
                           │ push (daily via GitHub Actions)
                ┌──────────┴──────────┐
                │ JSON-Export Script  │
                │ (reads Supabase via │
                │  service_role key)  │
                └──────────▲──────────┘
                           │ reads (daily, server-side)
                ┌──────────┴──────────┐
                │      Supabase       │
                │ (source of truth,   │
                │  ETL target)        │
                └──────────▲──────────┘
                           │ writes (daily)
                ┌──────────┴──────────┐
                │  Lolalytics ETL     │
                │  (unchanged)        │
                └─────────────────────┘
```

**Core decision:** Vue ↔ Python communicates via HTTP + WebSocket as today, not via Tauri-IPC. Tauri is only the launcher, window host, and updater. This keeps the Flask/Socket.IO code path untouched — minimum invasive change.

**What changes:**
- New `src-tauri/` crate with a minimal Rust host (sidecar spawn, port allocation, window config, updater).
- Python backend gets a CLI argument `--port` (no longer hardcoded 5000) and `--ready-file` (for startup synchronization).
- New `json_repo.py` replaces `supabase_repo.py` and `supabase_client.py` on the runtime path (those become unused in the bundled client; they remain in the repo for the ETL tooling if needed).
- New GitHub-Actions workflow step: after ETL runs, export Supabase tables to JSON and publish to `gh-pages` branch.

**What stays the same:**
- `counterpick-app/apps/frontend/` — Vue + Vite codebase, minor change only to backend URL discovery.
- `counterpick-app/apps/backend/` — Flask routes, recommendation engine, LCU client.
- `counterpick-app/packages/core/` — shared TS types.
- `supabase-dataset-updater/` — ETL pipeline and its GitHub Actions schedule.

**What is removed from the client runtime:**
- Direct Supabase connectivity from the client.
- Hardcoded port 5000 in the frontend.
- Manual two-step startup (`pnpm dev` + `python backend.py`).

## 4. Build Pipeline & Packaging

Three-stage build, orchestrated by `pnpm tauri build` in CI.

### 4.1 Stage 1 — Python Sidecar

- Tool: **PyInstaller** `--onefile` with custom `backend.spec`.
- Input: `counterpick-app/apps/backend/backend.py` + `requirements.txt`.
- Output: `backend.exe` (Windows), ~50–70 MB.
- Key spec settings:
  - `upx=False` (UPX-compressed PyInstaller binaries triple the AV false-positive rate).
  - Hidden imports: `httpx.socks`, `engineio.async_drivers.threading`, and any others surfaced during a first CI run.
  - `--collect-all supabase` is NOT needed because the runtime no longer uses Supabase; we explicitly exclude `supabase` from the bundle to reduce size and to eliminate credential surface area.
- The binary must be reproducible enough that the SHA256 hash stays stable for the same input. PyInstaller's build-time metadata may produce small variance; this is acceptable.

### 4.2 Stage 2 — Vue Frontend Bundle

- Tool: **Vite** (unchanged).
- Input: `counterpick-app/apps/frontend/src/`.
- Output: static bundle in `apps/frontend/dist/` which Tauri loads into the Webview.
- Only code change required: backend-URL discovery uses Tauri IPC at runtime instead of a hardcoded `localhost:5000`:
  ```ts
  // counterpick-app/apps/frontend/src/api/client.ts
  import { invoke } from '@tauri-apps/api/core'
  let backendURL: string | null = null
  export async function getBackendURL(): Promise<string> {
    if (!backendURL) {
      const port = await invoke<number>('get_backend_port')
      backendURL = `http://127.0.0.1:${port}`
    }
    return backendURL
  }
  ```
  Every `axios.create({ baseURL: 'http://localhost:5000' })` site in the frontend switches to `baseURL: await getBackendURL()`.

### 4.3 Stage 3 — Tauri Bundle

- Tool: **`tauri build`**.
- Inputs: Vue `dist/` as webview content + `backend.exe` as a sidecar resource.
- Output for Windows:
  - `.msi` installer.
  - Portable `.exe` (no installer).
  - Both roughly ~80 MB.
- The Tauri updater configuration references a JSON manifest (`latest.json`) hosted at a GitHub Releases URL; signing keys for updater signatures are stored in repo secrets.

### 4.4 CI/CD

- New workflow: `.github/workflows/release.yml`.
- Trigger: git tag matching `v*` (e.g. `v1.0.0`).
- Runner: `windows-latest` (single platform for v1).
- Steps in order:
  1. `actions/checkout`
  2. Setup Python, run `pip install -r apps/backend/requirements.txt` and `pip install pyinstaller`.
  3. Build sidecar: `pyinstaller apps/backend/backend.spec`.
  4. Setup Node, run `pnpm install`.
  5. Build Tauri: `pnpm tauri build`.
  6. Compute SHA256 of `.msi` and portable `.exe`.
  7. Create GitHub Release with both artifacts and the hash list in the release notes.
  8. Update `latest.json` on a branch or release asset for the Tauri updater.
- Secrets required:
  - `TAURI_PRIVATE_KEY` and `TAURI_KEY_PASSWORD` — for updater signatures (generated once via `tauri signer generate`).
  - Frontend does not need Supabase credentials at build time; the CDN URL is public and can live in `tauri.conf.json` directly.

### 4.5 Dev Workflow

- Command: `pnpm tauri dev`.
- Behavior:
  1. Vite dev server starts (hot-reload preserved).
  2. Tauri host spawns Python natively (not bundled): `python backend.py --port <auto> --ready-file <tmp>`.
  3. Tauri window loads `http://localhost:5173` (pointed by `tauri.conf.json` `devUrl`).
- Python dev mode reads Supabase credentials from `apps/backend/.env` as today, so developers working on the ETL or admin tooling still have DB access. The dev-mode backend can still optionally use Supabase directly for debugging; the CDN path is used in production.
- The `.env` file stays gitignored.

## 5. IPC, Ports & Lifecycle

### 5.1 Dynamic Port Allocation

Python does **not** bind to hardcoded port 5000 in the bundled app.

1. Tauri host allocates a free port by binding `127.0.0.1:0` with a `TcpListener`, reading `.local_addr()`, then dropping the listener.
2. Tauri spawns the Python sidecar with `backend.exe --port <allocated> --ready-file <tmp>/ready.flag`.
3. Python binds Flask on `127.0.0.1:<allocated>`, and once Socket.IO is initialized it writes an empty file at the ready-file path.
4. Tauri polls for the ready-file (100 ms interval, 10 s timeout), and only then shows the Webview window.
5. Frontend obtains the port via a Tauri command `get_backend_port`.

No port conflict is possible: even if other dev servers are running on common ports, the OS assigns a free port.

### 5.2 Sidecar Lifecycle

| Event | Behavior |
|-------|----------|
| App start (normal) | Tauri spawns sidecar, waits for ready flag, shows window. |
| App close (normal) | Tauri sends a graceful-shutdown request (on Windows: `GenerateConsoleCtrlEvent` with `CTRL_BREAK_EVENT` against the sidecar process group), waits 2 s for the child to exit, then hard-kills via `TerminateProcess`. |
| App crash / force-quit | The sidecar is spawned inside a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so the OS terminates the child if Tauri exits unexpectedly. |
| Python crash during runtime | Tauri observes child exit → emits Tauri event `backend-disconnected`. Frontend displays error banner with "Restart" button, which calls `invoke('restart_backend')`. |
| Sidecar fails to start | After 10 s timeout: error dialog, Tauri exits. |

### 5.3 WebSocket Reconnect

- Frontend continues using Socket.IO client (unchanged).
- On disconnect, Socket.IO's default exponential backoff kicks in.
- After 3 failed reconnects, the `backend-disconnected` banner appears.

### 5.4 Python-side Changes (minimal)

In `backend.py`:
```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=5000)
parser.add_argument('--ready-file', type=str, default=None)
args = parser.parse_args()

# ... after socketio.init_app(app):
if args.ready_file:
    with open(args.ready_file, 'w') as f:
        f.write('ok')

socketio.run(app, host='127.0.0.1', port=args.port)
```

Nothing else in `backend.py` changes.

### 5.5 Antivirus False-Positive Mitigation

PyInstaller `.exe` bundles are routinely flagged by Windows Defender and some third-party AVs because the bootloader stub resembles patterns seen in malware. Mitigations used in v1:

1. **UPX compression disabled** (`upx=False` in the PyInstaller spec).
2. **Microsoft false-positive submission** after each new release build. Submitted at `submit.microsoft.com`; whitelisting is by file hash and applies to that exact binary.
3. **SHA256 hashes published** in each GitHub Release's release notes so users can verify the binary they downloaded matches the one we built.
4. **README troubleshooting section** explains SmartScreen bypass and AV whitelist procedure.

Expected residual friction: a minority of users with aggressive AV (Kaspersky, some Norton configurations) will see quarantine events. They are directed to the README. If reports become frequent, the backlog item is migration to Nuitka or purchase of an EV code-signing certificate; neither is in v1 scope.

## 6. Data Backend — Supabase → CDN Hybrid (Pattern C)

### 6.1 Decision

Supabase remains the source of truth. A new server-side export step runs after each ETL pass and produces JSON files on a CDN. Clients read only from the CDN.

### 6.2 The Export Step

- New script: `supabase-dataset-updater/scripts/export_to_json.py`.
- Runs inside the existing daily GitHub Actions workflow, immediately after the ETL writes.
- Uses the `service_role` key (available as a GitHub Actions secret, never leaves CI).
- Queries each read-relevant Supabase table and writes to `data/<table>.json`.
- Tables to export (to be verified by querying the live database at implementation time; the current known set is):
  - `champion_stats`
  - `champion_stats_by_role`
  - `matchups`
  - `synergies`
  - `items`
  - `runes`
  - `summoner_spells`
- Output files are committed to a dedicated `gh-pages` branch in this same repository. GitHub Pages, configured to serve from that branch, makes them available at a stable URL of the form `https://{GITHUB_USER}.github.io/{REPO_NAME}/data/<table>.json`. The concrete `{GITHUB_USER}` and `{REPO_NAME}` values are filled in at implementation time and baked into `tauri.conf.json` as a config constant.
- Each JSON file includes a top-level `__meta` object with `exported_at` (ISO timestamp) and a SHA256 of the body, so clients can detect staleness and verify integrity.

### 6.3 Client Side — `json_repo.py`

New Python module that replaces `supabase_repo.py` on the runtime path:

```python
# counterpick-app/apps/backend/src/lolalytics_api/json_repo.py
import requests
from pathlib import Path
from datetime import datetime

CDN_BASE = "https://{GITHUB_USER}.github.io/{REPO_NAME}/data"  # concrete values filled at build time

def fetch_json(name: str, cache_dir: Path) -> dict:
    """Fetch a JSON file from the CDN with local caching and conditional GET."""
    cache_file = cache_dir / f"{name}.json"
    meta_file = cache_dir / f"{name}.meta.json"
    headers = {}
    if meta_file.exists():
        # honor If-Modified-Since / ETag
        ...
    response = requests.get(f"{CDN_BASE}/{name}.json", headers=headers, timeout=15)
    if response.status_code == 304 and cache_file.exists():
        return json.loads(cache_file.read_text())
    response.raise_for_status()
    cache_file.write_text(response.text)
    # write meta with Last-Modified / ETag / fetched_at
    ...
    return response.json()

def get_champion_stats(cache_dir: Path) -> list[dict]:
    return fetch_json("champion_stats", cache_dir)["rows"]

# ... parallel wrappers replacing sb_get_champion_stats, sb_get_matchups, etc.
```

The existing public API surface of `supabase_repo` (`get_champion_stats`, `get_matchups`, `get_synergies`, …) is preserved in `json_repo` with the same function signatures and return shapes. `backend.py` imports from `json_repo` instead of `supabase_repo` via a single-line swap. This keeps the Flask route handlers and the recommendation engine untouched.

### 6.4 Local Cache

- Location: Tauri app-data-dir `cache/` subfolder, resolved at runtime by Tauri's `path::app_data_dir()`. On Windows this resolves to `%APPDATA%\{TAURI_BUNDLE_ID}\cache\`, where `{TAURI_BUNDLE_ID}` is the identifier chosen in `tauri.conf.json` (e.g. `dev.till.lol-draft-analyzer`, to be finalized at implementation time).
- Per table: `<name>.json` (data) and `<name>.meta.json` (metadata: `last_fetched`, `etag`, `last_modified`, `sha256`).
- Cache is loaded into memory at backend startup (equivalent to the current `cache_data.json` behavior, but sourced from CDN instead of Supabase).
- Refresh policy: one conditional GET per table at backend startup; if the 304 (Not Modified) comes back, reuse cache.
- If the CDN is unreachable and cache is present: use cache and surface a small "using cached data from <date>" indicator.
- If the CDN is unreachable and no cache exists (first run, no network): show an error banner with a retry button.

### 6.5 What Is Removed from the Client

- `supabase-py` dependency from `requirements.txt` (not imported by `json_repo`, so it disappears from the PyInstaller bundle).
- Supabase credentials from the app's configuration entirely. The CDN URL is public, so `tauri.conf.json` simply records the base URL.
- Row-Level-Security policies become unnecessary for client access (the client cannot reach Supabase). They remain optional for defense-in-depth on the database itself.

## 7. Error Handling & Edge Cases

| Failure | Detection | User Experience | Recovery |
|---------|-----------|-----------------|----------|
| CDN unreachable on first run | `requests.get` timeout or non-2xx | Error banner "Cannot load champion data. Check internet connection." | Retry button, exponential backoff. |
| CDN unreachable on later run | Same | Silent — use local cache, display "using cached data from <date>" indicator | Background retry every 10 minutes. |
| LoL client not running | `league_client_auth.py` finds no lockfile | Full-screen waiting view: "Waiting for League of Legends…" | Poll every 3 s for lockfile. |
| LoL client crashes during draft | LCU WebSocket disconnect | Banner "League Client disconnected"; draft state preserved until a fresh draft begins | Auto-reconnect. |
| Python sidecar crashes | Tauri host sees child exit | Error dialog "Backend stopped unexpectedly" with Restart button | `invoke('restart_backend')`. |
| Sidecar blocked by AV | Child process exits within 2 s after spawn | Error dialog "Backend could not start. Your antivirus may have quarantined the file." with a link to the README AV-troubleshooting section | Manual whitelist by user. |
| Auto-update fails | Tauri updater returns error | Silent; the next app start tries again | N/A; not critical. |
| ETL / export job fails in CI | GitHub Actions check | Invisible to end users (old JSONs remain on CDN) | Maintainer fixes the failing workflow. |
| Corrupt JSON in cache | JSON parse error on read | Cache file deleted, fresh download triggered | Automatic. |
| Cache older than 7 days | Timestamp check after download | Banner "Data might be outdated" with last-update date | Informational only. |

### 7.1 Hover-Detection Fix (In-Scope Targeted Improvement)

Hover detection is currently implemented but does not behave as intended (gehoverte Champions werden nicht korrekt mit reduziertem Gewicht eingerechnet). This spec carries the fix as an in-scope item because:
- The fix lives in `league_client_websocket.py`, which we must touch anyway (to verify lifecycle behavior under the new spawn/reconnect model).
- Keeping the fix in this spec avoids one more separate plan for a small change.

Approach:
1. Add temporary diagnostic logging of all LCU events (`type` + `resource`) during champion select.
2. Identify which event-type carries hover state versus confirmed-pick state.
3. Verify that the current code path for hovers reaches `recommendation_engine` with the reduced-weight flag set; patch the logic where it does not.
4. Remove diagnostic logging before release.

### 7.2 Logging

- Python backend: structured log file at `%APPDATA%\{TAURI_BUNDLE_ID}\logs\backend-<YYYY-MM-DD>.log`, rotated daily. The bundle-id directory is the same one used for the cache in §6.4.
- Tauri host: uses the `log` crate, output co-located in the same logs/ directory.
- Frontend: `console.*` is visible in Tauri devtools during dev; disabled in production builds.
- **No telemetry**, no uploads in v1. User-reported issues rely on the user manually attaching the log file. README documents the log location.

## 8. Success Criteria

Acceptance gates for the v1 release tag:

**Supported game modes (in scope)**
- Summoner's Rift draft-based queues where LCU exposes the champion-select session: Normal Draft, Ranked Solo/Duo, Ranked Flex, and Clash.
- All five role positions (Top, Jungle, Mid, ADC, Support) are supported.
- The existing "blind-pick recommendation mode" of the recommendation engine — i.e. producing recommendations when no enemy picks are yet visible within a draft — remains supported unchanged.

**Unsupported game modes (out of scope by design)**
- The LoL "Blind Pick" queue (structurally unsupported: it has no champion-select phase with visible picks/hovers/bans that the tool could observe).
- ARAM, Arena, Nexus Blitz, TFT, and any other non-Summoner's-Rift mode (different data domain; lolalytics scoring data does not apply).
- Co-op vs. AI queues (no matchup/meta data relevant).
- Practice Tool and Custom games (no ranked meta context).

**Build & distribution**
- [ ] `.msi` installer is present as a GitHub Release asset.
- [ ] Portable `.exe` is present as a GitHub Release asset.
- [ ] Release notes include SHA256 hashes of both artifacts.
- [ ] Installer size ≤ 100 MB.
- [ ] CI workflow on `windows-latest` builds both on a tagged release.

**Installation**
- [ ] Installer completes on clean Windows 10 and Windows 11 without requiring admin rights.
- [ ] Start Menu entry "LoL Draft Analyzer" is created.
- [ ] Uninstaller removes the app and its cache, optionally preserving user settings (none in v1).

**First-run / cold start**
- [ ] App opens without interaction from the Start Menu shortcut.
- [ ] No credential entry required at first run.
- [ ] CDN data is downloaded on first run with visible progress.
- [ ] If no network is available at first run: a clear error, no crash.

**Runtime**
- [ ] LoL client is detected within 3 s of being started.
- [ ] Champion-select draft state is displayed in real time.
- [ ] Recommendation scores are produced for all 5 roles at every pick event.
- [ ] **Hover detection works:** hovered enemy/ally picks are factored in with a reduced weight (not ignored).
- [ ] Closing the LoL client does not crash the app; the waiting view reappears.
- [ ] Reopening the LoL client auto-reconnects.

**Stability**
- [ ] 2 h idle runtime with LoL open and no active draft grows RAM by less than 50 MB.
- [ ] 20 consecutive drafts without restart show no functional degradation.

**Auto-update**
- [ ] Tauri updater detects a newer release.
- [ ] User receives an "Update available" prompt with Install button.
- [ ] Update installs successfully and the app relaunches.

**Documentation**
- [ ] README documents: download link, SmartScreen workaround, AV false-positive guidance, log-folder location for bug reports.
- [ ] CHANGELOG entry for v1.0.0.

## 9. Testing Strategy

**Automated (CI)**
- Python backend: existing `pytest` suite runs unchanged.
- New integration test `test_backend_cli.py`: spawns `backend.py --port 0 --ready-file <tmp>`, verifies that the ready file is written and the server listens on the assigned port.
- New unit tests for `json_repo.py`: mocked HTTP, cache-hit path, conditional-GET path, corrupt-cache recovery.
- Vue frontend: no new tests (minimum diff to the component tree).
- Tauri host: a Rust smoke test — sidecar-binary spawn + clean shutdown.
- Build smoke: every push to `main` builds the installer (no release); only tag pushes publish a release.

**Manual (per release)**
- Clean install on a fresh Windows VM with no prior dev tooling.
- Full draft flow across all 5 roles.
- Close/reopen the LoL client mid-draft → reconnect verified.
- Update flow: install v1.0.0, tag v1.0.1, verify updater trigger.

## 10. Deferred Concerns / Out-of-Scope

**Deferred to follow-on specs:**
- **DB-performance review on Supabase.** Connection pooling, index coverage on query paths (matchups, synergies, champion_stats), query efficiency (no `SELECT *`), and Supabase-side rate limits must be reviewed before scaling the ETL or before exposing any live query path. Pattern C greatly reduces urgency because clients no longer hit Supabase, but the ETL itself benefits from these audits.
- **Nuitka migration** as an alternative to PyInstaller — only justified if AV false-positive reports become frequent.
- **macOS and Linux builds** — out of scope for v1; LoL on macOS has ~5% share, Linux has no official LoL support.
- **Code signing (EV certificate)** — out of scope for v1; ~$200–400/year cost not justified for a non-commercial release. Reconsider if AV friction dominates user feedback.
- **User settings / preferences** (language, theme, role override) — no settings shipped in v1. When added, storage goes in Tauri app-data-dir via `@tauri-apps/plugin-store`.
- **Telemetry, crash reporting** — not in v1 for privacy reasons. If later added, it must be opt-in.
- **FastAPI migration** — only revisit if Flask becomes an actual bottleneck.
- **Non-Summoner's-Rift and non-draft game modes** (ARAM, Arena, Nexus Blitz, TFT, LoL Blind Pick queue, Co-op vs AI, Practice Tool, Custom games) — out of scope. See §8 "Supported/Unsupported game modes" for the full rationale. Supporting these would require separate data sources and is not planned.
- **Overlay UX polish** — separate spec (Theme B in original brainstorming decomposition).
- **GitHub-publishing readiness** (license selection, legal review of Lolalytics scraping, README polish) — separate spec (Theme A).

## 11. Migration Checklist (for the implementation plan)

These are the concrete deltas the implementation plan will enumerate:

1. Add `src-tauri/` crate with `main.rs`, `tauri.conf.json`, and the `get_backend_port` and `restart_backend` commands.
2. Add `--port` and `--ready-file` CLI args to `backend.py`.
3. Create `json_repo.py` mirroring the public API of `supabase_repo.py`, reading from CDN and local cache.
4. Swap `backend.py`'s repo imports from `supabase_repo` to `json_repo`.
5. Update the frontend API client to discover the backend URL via Tauri IPC.
6. Remove `supabase` from `requirements.txt` (runtime path).
7. Add `supabase-dataset-updater/scripts/export_to_json.py` and wire it into the existing ETL GitHub Actions workflow; publish to a `gh-pages` branch.
8. Configure GitHub Pages to serve from that branch.
9. Create `backend.spec` for PyInstaller (no UPX, correct hidden imports).
10. Create `.github/workflows/release.yml` (triggered by `v*` tags, matrix = `windows-latest`).
11. Generate Tauri updater signing keys; add as repo secrets.
12. Update README with: installer download, SmartScreen workaround, AV guidance, log location.
13. Diagnose and fix hover-detection bug in `league_client_websocket.py`.
14. Add the integration and unit tests listed in §9.
15. Write CHANGELOG v1.0.0 entry.

---

**End of spec.** Implementation plan to be created by the `writing-plans` skill next.
