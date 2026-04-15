# Architecture Research

**Domain:** Tauri desktop shell wrapping a PyInstaller-packaged Flask/Socket.IO sidecar with a GitHub-Pages CDN-JSON data plane, layered onto an existing Vue 3 + Flask + Supabase monorepo.
**Researched:** 2026-04-14
**Confidence:** HIGH (component boundaries, integration points, build order fully specified in the delivery-form spec and verifiable against the existing codebase)

## Scope Note

This is a "subsequent milestone" research pass. The existing three-tier architecture (Vue 3 ↔ Flask/Socket.IO ↔ Supabase + LCU bridge) is preserved. Research is scoped to the three net-new architectural components:

1. **Tauri Rust host** — launcher, window host, sidecar supervisor, updater.
2. **Python sidecar lifecycle** — spawn on dynamic port, ready-file handshake, graceful-shutdown ladder.
3. **CDN-JSON data plane** — `json_repo.py` replacing `supabase_repo.py` on the runtime path, with an on-disk cache and conditional-GET refresh.

Flask routes, the recommendation engine, the LCU bridge, and the ETL pipeline are **not** re-researched and are marked as frozen surfaces.

## Standard Architecture

### System Overview (End-State)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Installed Desktop App (one .msi + one portable .exe)                         │
│                                                                              │
│ ┌─────────────────────────┐            ┌────────────────────────────────┐    │
│ │ Webview (Vue 3 + Vite)  │◄── IPC ───►│ Tauri Host (Rust, src-tauri/)  │    │
│ │  - api/client.ts        │            │  - window + menu               │    │
│ │  - stores/draft.ts      │            │  - get_backend_port cmd (IPC)  │    │
│ │  - socket.io-client     │            │  - restart_backend cmd (IPC)   │    │
│ │  - UNCHANGED component  │            │  - sidecar supervisor          │    │
│ │    tree                 │            │  - Job Object (KILL_ON_CLOSE)  │    │
│ └──────────┬──────────────┘            │  - Tauri updater               │    │
│            │                           └──────────┬─────────────────────┘    │
│            │ HTTP + Socket.IO                     │ spawn/kill/observe      │
│            │ to 127.0.0.1:<dyn-port>              │                          │
│            ▼                                      ▼                          │
│ ┌──────────────────────────────────────────────────────────────────┐         │
│ │ PyInstaller onefile: backend.exe (FROZEN Flask/Socket.IO code)   │         │
│ │  ┌──────────────────────────────────────────────────────────┐    │         │
│ │  │ backend.py (route handlers UNCHANGED)                    │    │         │
│ │  │   + argparse: --port, --ready-file   (NEW, 2-arg delta)  │    │         │
│ │  │   + ready-flag write after socketio.init_app            │    │         │
│ │  ├──────────────────────────────────────────────────────────┤    │         │
│ │  │ recommendation_engine.py   (UNCHANGED — frozen surface)  │    │         │
│ │  │ league_client_*.py         (UNCHANGED except hover fix)  │    │         │
│ │  ├──────────────────────────────────────────────────────────┤    │         │
│ │  │ lolalytics_api/json_repo.py (NEW — same public API as    │    │         │
│ │  │   supabase_repo.py; reads CDN via requests + cache)      │    │         │
│ │  │ lolalytics_api/supabase_repo.py (STAYS in repo for ETL   │    │         │
│ │  │   tooling; EXCLUDED from PyInstaller bundle)             │    │         │
│ │  └──────────────────────────────────────────────────────────┘    │         │
│ └───────────────────┬──────────────────────┬──────────────────────┘         │
│                     │ HTTPS (read-only)    │ filesystem R/W                 │
└─────────────────────┼──────────────────────┼─────────────────────────────────┘
                      ▼                      ▼
        ┌──────────────────────┐   ┌────────────────────────────────────┐
        │ GitHub Pages (CDN)   │   │ %APPDATA%\{bundle_id}\cache\       │
        │  /data/<table>.json  │   │   <table>.json (body)              │
        │   each with          │   │   <table>.meta.json                │
        │   __meta.exported_at │   │     {etag,last_modified,sha256,    │
        │   __meta.sha256      │   │      fetched_at}                   │
        └──────────▲───────────┘   └────────────────────────────────────┘
                   │
                   │ commits to gh-pages branch (daily)
        ┌──────────┴───────────────────────────────┐
        │ GitHub Actions: update-dataset.yml       │
        │  existing:                               │
        │   supabase-etl.ts → writes Supabase      │
        │  NEW appended step:                      │
        │   export_to_json.py → reads Supabase,   │
        │     writes data/*.json, commits to       │
        │     gh-pages branch                      │
        └──────────▲───────────────────────────────┘
                   │ reads
                ┌──┴──────────┐
                │  Supabase   │  (ETL target only — no client contact anymore)
                └─────────────┘
```

### Component Responsibilities

| Component | Status | Responsibility | Implementation |
|-----------|--------|----------------|----------------|
| Tauri Host (Rust) | **NEW** | Allocate port, spawn sidecar, observe lifetime, bridge IPC to frontend, drive updater, enforce Job Object kill-on-close | `src-tauri/` crate (new), `tauri = "2.x"`, `tokio`, `windows-sys` for Job Object FFI |
| Webview (Vue 3) | Modified | Draft UI (unchanged) + **backend-URL discovery** via Tauri IPC | `apps/frontend/src/api/client.ts` (new getter) + one-line diffs in `api/backend.ts` and `stores/draft.ts` |
| Python Sidecar entrypoint | Modified | Flask + Socket.IO (unchanged) + **2 new CLI args** + ready-file write | `apps/backend/backend.py` — argparse delta only |
| `json_repo.py` | **NEW** | Mirror `supabase_repo.py` public surface; fetch from CDN with conditional GET and on-disk cache | `apps/backend/src/lolalytics_api/json_repo.py` — uses `requests`, stdlib `json`/`hashlib`/`pathlib` |
| CDN exporter | **NEW** | Dump Supabase tables to `data/<table>.json` and push to `gh-pages` | `supabase-dataset-updater/scripts/export_to_json.py` (new), appended to existing `.github/workflows/update-dataset.yml` |
| `supabase_repo.py` | **Frozen/unused-at-runtime** | Stays in repo for ETL/admin tooling; excluded from PyInstaller bundle via spec `excludes` | `apps/backend/src/lolalytics_api/supabase_repo.py` — no code change |
| Flask routes | **Frozen** | REST + Socket.IO endpoints | `apps/backend/backend.py` route handlers — no change |
| Recommendation engine | **Frozen** | Wilson-Score scoring | `apps/backend/recommendation_engine.py` — no change |
| LCU bridge | **Frozen (+ 1 bug fix)** | Hover/pick event relay | `apps/backend/league_client_*.py` — targeted hover-weight fix |

### New vs Existing (Boundary Diagram)

```
  NEW SURFACES                           EXISTING (FROZEN) SURFACES
 ═══════════════                         ═══════════════════════════
 src-tauri/                ─── spawns ─► apps/backend/backend.py
 ├─ main.rs                                 (argparse delta only)
 ├─ sidecar.rs  (port alloc,                      │
 │              Job Object,                       │ calls unchanged
 │              ready-file poll,                  ▼
 │              CTRL_BREAK ladder)         recommendation_engine.py
 ├─ commands.rs (get_backend_port,         league_client_*.py
 │              restart_backend)                  ▲
 └─ tauri.conf.json (bundle id,                   │ imports
                     resources,                   │ (single-line swap)
                     updater,                     │
                     devUrl)                      │
                                          lolalytics_api/
 apps/backend/src/lolalytics_api/                 │
 └─ json_repo.py  ◄── same public API ──  lolalytics_api/supabase_repo.py
    - get_champion_stats                     (stays in tree, excluded
    - get_champion_stats_by_role              from PyInstaller bundle)
    - get_matchups
    - get_synergies
    - get_items / get_runes /
      get_summoner_spells

 apps/frontend/src/api/client.ts  ◄────── apps/frontend/src/api/backend.ts
   (new: getBackendURL() via invoke)         (API_BASE_URL swap to absolute)
                                          apps/frontend/src/stores/draft.ts
                                            (one-line: io('http://localhost:5000')
                                             → io(await getBackendURL()))

 supabase-dataset-updater/                supabase-dataset-updater/
 └─ scripts/export_to_json.py     ──┐     └─ src/supabase-etl.ts (existing)
                                    │
 .github/workflows/                 │     .github/workflows/
 ├─ release.yml (NEW, tag-trig.)    └──►  update-dataset.yml (append step)
 └─ update-dataset.yml (modified)
```

### Public API Contract (Must Stay Stable)

`json_repo.py` **must** expose functions with identical signatures and return shapes to these in `supabase_repo.py` (verified against source):

| Function | Signature | Return |
|----------|-----------|--------|
| `get_champion_stats(...)` | `(patch: Optional[str] = None, ...) -> List[Dict[str, Any]]` | list of stat rows, names attached |
| `get_champion_stats_by_role(...)` | same pattern | list of per-role stat rows |
| `get_matchups(champion, role?, patch?)` | `(champion: str, role: Optional[str] = None, patch: Optional[str] = None) -> List[Dict]` | list of matchup rows with `enemy_name` |
| `get_synergies(champion, role?, patch?)` | same pattern | list of synergy rows with `ally_name` |
| `get_items(patch?)` | `(patch: Optional[str] = None) -> List[Dict]` | item rows |
| `get_runes(patch?)` | same | rune rows |
| `get_summoner_spells(patch?)` | same | summoner-spell rows |
| `_wilson_score(wins, n, z?)` | internal helper — stays identical to avoid drift between scoring in engine vs repo |

**Contract requirement:** `backend.py` changes exactly **one import block** (lines 11–19) from `from lolalytics_api.supabase_repo import …` to `from lolalytics_api.json_repo import …` — preserving the `sb_get_…` aliases so downstream route handlers compile without further edits.

## Recommended Project Structure

```
F:\Dokumente\Archiv\Riot Api\
├── counterpick-app\
│   ├── apps\
│   │   ├── backend\
│   │   │   ├── backend.py                    [MODIFIED: argparse + ready-file + repo import swap]
│   │   │   ├── backend.spec                  [NEW: PyInstaller spec, upx=False, excludes supabase]
│   │   │   ├── requirements.txt              [MODIFIED: remove supabase; keep requests, flask, flask-socketio]
│   │   │   ├── recommendation_engine.py      [UNCHANGED]
│   │   │   ├── recommendation_config.py      [UNCHANGED]
│   │   │   ├── league_client_auth.py         [UNCHANGED]
│   │   │   ├── league_client_api.py          [UNCHANGED]
│   │   │   ├── league_client_websocket.py    [MODIFIED: hover-weight bug fix only]
│   │   │   ├── live_client_api.py            [UNCHANGED]
│   │   │   └── src\lolalytics_api\
│   │   │       ├── json_repo.py              [NEW: CDN reader + cache; public API mirrors supabase_repo]
│   │   │       ├── supabase_repo.py          [UNCHANGED; excluded from PyInstaller bundle]
│   │   │       ├── supabase_client.py        [UNCHANGED; excluded from bundle]
│   │   │       ├── config.py                 [UNCHANGED]
│   │   │       ├── errors.py                 [UNCHANGED]
│   │   │       └── main.py                   [UNCHANGED]
│   │   └── frontend\
│   │       ├── src\
│   │       │   ├── api\
│   │       │   │   ├── backend.ts            [MODIFIED: API_BASE_URL derived from getBackendURL()]
│   │       │   │   └── client.ts             [NEW: getBackendURL() — invoke('get_backend_port')]
│   │       │   ├── stores\
│   │       │   │   └── draft.ts              [MODIFIED: one line — io(await getBackendURL())]
│   │       │   └── …                         [UNCHANGED]
│   │       └── vite.config.ts                [UNCHANGED for prod; dev proxy may stay as fallback]
│   ├── src-tauri\                            [NEW CRATE — root of Tauri host]
│   │   ├── Cargo.toml                        [NEW]
│   │   ├── build.rs                          [NEW, Tauri default]
│   │   ├── tauri.conf.json                   [NEW: bundle id, resources, updater endpoints, devUrl]
│   │   ├── icons\                            [NEW: .ico, .png assets]
│   │   └── src\
│   │       ├── main.rs                       [NEW: tauri::Builder setup, command registration]
│   │       ├── sidecar.rs                    [NEW: PortAlloc, ReadyFilePoll, JobObject, ShutdownLadder]
│   │       └── commands.rs                   [NEW: #[tauri::command] get_backend_port, restart_backend]
│   ├── packages\core\                        [UNCHANGED]
│   ├── pnpm-workspace.yaml                   [MODIFIED: add src-tauri to workspace-ignore if needed]
│   └── package.json                          [MODIFIED: add "tauri" script, @tauri-apps/cli devDep]
├── supabase-dataset-updater\
│   ├── scripts\
│   │   └── export_to_json.py                 [NEW: reads Supabase → data/*.json + __meta]
│   └── src\supabase-etl.ts                   [UNCHANGED]
└── .github\workflows\
    ├── update-dataset.yml                    [MODIFIED: append export_to_json.py step + gh-pages push]
    └── release.yml                           [NEW: windows-latest, v* tag trigger, sidecar + tauri build]
```

### Structure Rationale

- **`src-tauri/` as a new sibling of `apps/`** — matches Tauri convention (`pnpm tauri init` default) and keeps the Rust crate outside the pnpm workspace graph; only root `package.json` gets the `tauri` script and `@tauri-apps/cli` devDependency so `pnpm tauri {dev,build}` works from the monorepo root.
- **`json_repo.py` beside `supabase_repo.py` (not replacing it)** — the ETL tooling at `supabase-dataset-updater/` does not import from `apps/backend/`, but keeping `supabase_repo.py` in-tree preserves optional dev-mode DB access (§4.5 of the spec) and leaves a diff-minimal rollback path.
- **Cache in `%APPDATA%\{bundle_id}\cache\` (not alongside the exe)** — Tauri's `path::app_data_dir()` resolves here on Windows; the portable `.exe` and the `.msi` installer both resolve to the same per-user folder, so cache survives reinstall and never pollutes `Program Files`.
- **`backend.spec` at `apps/backend/backend.spec`** — colocated with the entrypoint so `pyinstaller apps/backend/backend.spec` works from repo root in CI.
- **`release.yml` separate from `update-dataset.yml`** — different triggers (git tag vs. cron), different runners (windows-latest vs. ubuntu-latest for ETL), different secret scopes. Merging them creates brittle conditionals.

## Architectural Patterns

### Pattern 1: Sidecar Lifecycle State Machine

**What:** Tauri treats the Python child as a managed subprocess with an explicit state machine; the UI is deferred until `Ready`, and shutdown descends a defined ladder.

**State machine:**

```
  [Launching]
       │  1. TcpListener bind 127.0.0.1:0 → read .local_addr().port() → drop listener
       │  2. Create temp ready-file path (e.g. %TEMP%\counterpick-<uuid>.ready)
       │  3. CreateJobObject + SetInformationJobObject(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
       │  4. CreateProcess backend.exe --port <P> --ready-file <R>
       │     with CREATE_NEW_PROCESS_GROUP + CREATE_NO_WINDOW flags
       │  5. AssignProcessToJobObject
       ▼
  [WaitingForReady]
       │  Poll filesystem for ready-file every 100 ms, timeout 10 s
       │  If timeout → [FailedToStart] → error dialog → exit
       │  If child exits <2 s → [CrashedEarly] → "AV likely quarantined" dialog
       ▼
  [Ready]
       │  6. Show main window; webview navigates to tauri://localhost (prod)
       │                                       or http://localhost:5173 (dev)
       │  7. Frontend issues invoke('get_backend_port') → returns P
       ▼
  [Running] ────► (child exit observed) ─► [Crashed]
       │                                       │
       │                                       │ emit 'backend-disconnected'
       │                                       │ frontend shows banner + Restart button
       │                                       │ Restart → invoke('restart_backend')
       │                                       │ → re-enter [Launching] with fresh port/file
       │
       │ User closes window
       ▼
  [ShuttingDownGracefully]
       │  8. GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, child.pid)
       │     (requires CREATE_NEW_PROCESS_GROUP at spawn)
       │  9. Wait 2 s for clean exit
       ▼
  [ShuttingDownHard]
       │  10. TerminateProcess(child_handle, 1)
       ▼
  [JobObjectCloses]
          11. Tauri process exits → Job Object handle closes →
              OS kernel terminates any remaining processes in the job
              (safety net if Tauri itself crashed before step 10)
```

**Why the ladder:** `CTRL_BREAK_EVENT` lets Flask/Socket.IO drain, but Socket.IO's threading-mode event loop can block on select(); the 2s-then-TerminateProcess ensures shutdown is bounded. Job Object is the defense-in-depth for "Tauri force-killed by Task Manager" — without it, orphaned `backend.exe` processes accumulate and hold the port next launch.

**Trade-offs:**
- Pro: Three-level defense means no orphan processes under any crash/force-kill permutation.
- Pro: Ready-file polling is simpler and more portable than piped stdout signaling (PyInstaller onefile has a bootloader that unpacks before user code runs; stdout isn't reliable during unpack).
- Con: Ready-file polling adds up to 100 ms startup latency; trivially acceptable.
- Con: Requires `windows-sys` FFI for Job Object — no pure-Rust crate covers this cleanly.

### Pattern 2: Port Allocation via Bind-Drop-Reuse

**What:** Reserve an OS-allocated free port in Rust, read it, drop the listener, then pass the number to the child which binds again.

**Code shape:**
```rust
// src-tauri/src/sidecar.rs
use std::net::{TcpListener, SocketAddr};

fn allocate_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);              // release immediately
    Ok(port)
}
```

**When to use:** Any multi-process localhost architecture where the port must not be hardcoded.

**Trade-offs:**
- Pro: Deterministic — OS guarantees the port was free at allocation time.
- Pro: No `netstat` parsing, no port-range scanning, no conflict with dev servers on 3000/5000/5173/8000.
- Con: **TOCTOU race** — another process could grab the port between drop and the sidecar's bind. Mitigation: on `bind() failed` in the sidecar, exit with a distinct code (e.g. 42); Tauri retries allocation up to 3×. In practice this race never fires on a user's desktop; only matters on CI with noisy processes.
- Con: The port number is visible to any local process (any user-space program on 127.0.0.1 can probe). Acceptable for this threat model — no secrets are served; recommendations are non-sensitive; LCU auth is held only inside the Python process.

### Pattern 3: CDN-JSON Data Plane with Conditional-GET Cache

**What:** Replace the live-query repository with a read-through cache whose authoritative source is a static JSON dump on a public CDN; use HTTP `If-None-Match` / `If-Modified-Since` to avoid re-downloading unchanged data.

**Cache topology:**
```
%APPDATA%\{bundle_id}\cache\
├── champion_stats.json         <— body (raw response, includes __meta envelope)
├── champion_stats.meta.json    <— { "etag": "...", "last_modified": "...",
│                                     "sha256": "...", "fetched_at": "ISO-8601" }
├── champion_stats_by_role.json
├── champion_stats_by_role.meta.json
├── matchups.json
├── matchups.meta.json
├── synergies.json
├── synergies.meta.json
├── items.json         + .meta.json
├── runes.json         + .meta.json
└── summoner_spells.json + .meta.json
```

**Envelope on CDN (committed by `export_to_json.py`):**
```json
{
  "__meta": {
    "exported_at": "2026-04-14T12:17:03Z",
    "sha256": "9b...e4",
    "row_count": 167,
    "source_table": "champion_stats"
  },
  "rows": [ { …row… }, … ]
}
```

**Refresh policy:**
- At sidecar startup: one conditional GET per table. If `304 Not Modified` → reuse cache file. If `200 OK` → overwrite body + update `.meta.json` with new ETag/Last-Modified, verify `__meta.sha256` against hash of `rows`.
- During runtime: no re-fetching (data is patch-frequency static; daily refresh is sufficient).
- On CDN unreachable + cache present: use cache, expose `cache_age_days` via a status endpoint for the frontend staleness banner.
- On CDN unreachable + no cache: return 503 from repo, frontend shows retry UI.
- On parse/SHA mismatch: delete cache file + meta, redownload unconditionally.

**Trade-offs:**
- Pro: Zero Supabase credentials on client; Supabase attack surface collapses to ETL-runner IAM only.
- Pro: GitHub Pages is free, globally CDN-cached, and has sub-100ms `If-None-Match` responses.
- Pro: First-run download is single-digit MB (JSON compresses well over HTTP gzip), fits the ≤100 MB installer budget and the "visible progress" UX.
- Con: Hourly or faster data freshness is impossible (GitHub Actions cron + gh-pages push latency ≈ 1–5 min; fine for patch-day stats, not for live leaderboards).
- Con: Exposing all stats publicly — acceptable because the data is already scraped from a public source (Lolalytics).

### Pattern 4: IPC-Only-for-Discovery (Not for Data)

**What:** Tauri IPC is used **exclusively** to expose runtime configuration (the dynamic port) and lifecycle controls (restart). All actual draft data flows over HTTP + Socket.IO to `127.0.0.1:<port>`.

**Rationale (explicit decision from spec §3):**
- Preserves the existing Flask/Socket.IO code path zero-diff.
- Keeps the frontend identical in "dev via Vite + native python" and "prod via Tauri + sidecar exe" modes — only the base URL changes.
- Avoids coupling domain logic to Tauri; a future non-Tauri packaging (Electron, raw NSIS, …) would change only `client.ts`.

**Commands exposed:**
```rust
#[tauri::command]
async fn get_backend_port(state: State<'_, SidecarState>) -> Result<u16, String>

#[tauri::command]
async fn restart_backend(state: State<'_, SidecarState>) -> Result<(), String>
```

**Events emitted:**
- `backend-ready` (on transition to Ready — frontend can show window/hide splash)
- `backend-disconnected` (on child exit in Running — frontend shows banner)

## Data Flow

### Flow A — App Start (Normal, Cache-Hit Path)

```
  User double-clicks .msi shortcut
        │
        ▼
  Tauri main.rs boots → SidecarState::init
        │
        ├──► allocate_port()          → 51423
        ├──► create temp ready-file   → %TEMP%\cp-ab12.ready
        ├──► CreateJobObject + KILL_ON_CLOSE flag
        ├──► spawn backend.exe --port 51423 --ready-file %TEMP%\cp-ab12.ready
        │       (CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW)
        ├──► AssignProcessToJobObject
        └──► poll ready-file every 100 ms
                │
                ▼
        backend.exe starts →
          load_cache_from_disk() reads %APPDATA%\cp\cache\*.meta.json
          for each table: requests.get(CDN, headers={If-None-Match:<etag>})
            → 304 Not Modified (fast path) → keep cached body
          socketio.init_app(app)
          open(ready-file, 'w').write('ok')
          socketio.run(host='127.0.0.1', port=51423)   (blocks)
                │
                ▼
        Tauri observes ready-file appeared → emit 'backend-ready'
        Tauri shows main window (webview loads tauri://localhost)
                │
                ▼
        Vue app.mount('#app') →
          stores/draft.ts.init() →
            port = await invoke('get_backend_port')    // returns 51423
            socket = io(`http://127.0.0.1:${port}`)
          stores/champion.ts.loadList() → fetch(`${baseURL}/api/champions/list`)
                │
                ▼
        UI usable. Time-to-interactive: ~1.5–3 s (dominated by PyInstaller onefile unpack).
```

### Flow B — Draft-in-Progress

```
  LoL client detects champ-select phase
        │
        ▼
  league_client_websocket.py (inside sidecar) receives LCU event
        │  type=ChampSelectSession, resource=/lol-champ-select/v1/session
        │  (hover-weight fix applied here before emit)
        ▼
  socketio.emit('draft_update', payload)   → travels over 127.0.0.1:51423
        │
        ▼
  Frontend stores/draft.ts socket.on('draft_update') → updateDraftState()
        │
        ▼
  Component reactive → api/backend.ts.getRecommendations({myTeam, enemyTeam, role})
        │       fetch(`${baseURL}/api/recommendations`, POST)
        ▼
  Flask handler → recommendation_engine.get_recommendations()
        │       calls json_repo.get_matchups(champ, role, patch)  [NEW]
        │         → cache hit, returns list[dict] with same shape supabase_repo returned
        │       calls json_repo.get_synergies(...)                  [NEW]
        │       calls json_repo.get_champion_stats(...)             [NEW]
        │       Wilson-Score scoring (UNCHANGED)
        ▼
  JSON response → frontend renders RecommendationsList.vue
```

**Key observation:** The yellow path (engine ↔ repo) is unchanged at the call-site level. Only the *implementation* behind `get_matchups` et al. switches from `supabase.table("matchups").select(...)` to `self._table("matchups") → list[dict]` where `_table` resolves from the in-memory-loaded JSON cache.

### Flow C — Cold CDN Fetch (First Run, No Cache)

```
  backend.exe starts, cache_dir is empty
        │
        ▼
  for each table in [champion_stats, champion_stats_by_role, matchups,
                     synergies, items, runes, summoner_spells]:
        │
        ├──► GET https://{user}.github.io/{repo}/data/<table>.json
        │    (no If-None-Match; full download)
        │    timeout=15s, retry-on-5xx with exp-backoff
        │
        ├──► on success:
        │    - verify body_json["__meta"]["sha256"] == sha256(canonical(body_json["rows"]))
        │    - write cache_dir/<table>.json       (raw body)
        │    - write cache_dir/<table>.meta.json  (etag from response header,
        │                                          last_modified, sha256,
        │                                          fetched_at=now)
        │    - socketio.emit('cdn_progress', {table, done: N, total: 7})
        │
        └──► on failure (all tables still empty):
             - write no cache
             - raise CdnUnreachableError which the Flask /health endpoint surfaces
             - frontend shows full-screen "Check connection" error
```

**Progress surfacing:** The sidecar emits `cdn_progress` Socket.IO events during startup; frontend can show a progress bar before the main UI mounts. Alternative: Tauri splash window polls `/health` endpoint with a `{phase: "downloading", done, total}` shape. Either works — splash-window is cleaner because Socket.IO isn't yet wired when the first fetch starts. **Recommendation: splash + HTTP `/status` poll**, not Socket.IO, because the status endpoint is available as soon as Flask binds (before ready-file is written).

### Flow D — Cache-Hit Startup (Steady State)

```
  backend.exe starts, cache_dir has 7 pairs
        │
        ▼
  for each table:
        │
        ├──► read cache_dir/<table>.meta.json → {etag, last_modified, sha256}
        ├──► GET .../data/<table>.json
        │    headers: If-None-Match=<etag>, If-Modified-Since=<last_modified>
        │    timeout=15s
        │
        ├──► 304 Not Modified:
        │    - read cache_dir/<table>.json into memory
        │    - verify cached sha256 against meta.sha256 (integrity guard)
        │    - if mismatch → delete both files → treat as cold fetch
        │
        └──► 200 OK (data changed overnight):
             - same path as cold fetch for this single table
             - old cache overwritten atomically (write to .json.tmp → rename)
```

**Performance:** 7 conditional GETs run in parallel (`concurrent.futures.ThreadPoolExecutor` or `requests-futures`), typical total cold-path 200–400 ms on broadband. Meets the "visible progress, no freeze" UX bar.

### Flow E — Graceful Shutdown

```
  User clicks X on window
        │
        ▼
  Tauri on_window_event(CloseRequested) → SidecarState.shutdown()
        │
        ├──► step 1: GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, child_pgid)
        │    │
        │    │   Python signal handler (registered in backend.py):
        │    │       signal.signal(signal.SIGBREAK, lambda *_: socketio.stop())
        │    │   socketio.stop() drains clients, closes listening socket
        │    │   process.exit(0)
        │    │
        │    └── wait up to 2000 ms with Child::try_wait polling at 50 ms
        │
        ├──► step 2 (if still alive): TerminateProcess(child_handle, 1)
        │    wait 500 ms
        │
        └──► step 3: drop JobObject handle
                     OS ensures no orphan descendants survive
        │
        ▼
  Tauri exits → process handle closed → OS completes Job Object cleanup
```

### Flow F — Crash Recovery (Python Dies Mid-Draft)

```
  backend.exe crashes (e.g. uncaught exception in a route handler)
        │
        ▼
  Tauri's Child::wait() future resolves with non-zero exit code
        │
        ▼
  SidecarState transitions Running → Crashed
  emit Tauri event 'backend-disconnected' + exit_code
        │
        ▼
  Frontend socket.on('disconnect') fires (Socket.IO notices TCP RST)
  Frontend also receives tauri event listener:
    listen('backend-disconnected', () => store.showRestartBanner())
        │
        ▼
  User clicks Restart → invoke('restart_backend')
        │
        ▼
  SidecarState re-enters Launching with a fresh port + new ready-file
  (old Job Object stays; new child is assigned to same job)
        │
        ▼
  Frontend: on 'backend-ready', calls getBackendURL() which re-invokes
  'get_backend_port' (cached value is invalidated) → new socket connection
```

**Crash-recovery invariant:** The frontend's `backendURL` memoization in `api/client.ts` must be invalidatable. Suggested implementation:
```ts
let backendURL: string | null = null
listen('backend-ready', () => { backendURL = null })  // invalidate on restart
```

## Scaling Considerations

Desktop app — "scale" is per-install concerns, not per-tenant.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single user, active draft | Baseline — all flows as designed. |
| Single user, 20+ drafts/session | Backend memory: lolalytics JSON fully loaded in RAM (~5–15 MB total); no GC pressure. Watch for `league_client_websocket` leaking sockets on reconnect — existing code; covered by "2 h idle, RAM <50 MB growth" criterion. |
| First-run across many new users | CDN cold-fetch concurrency is 7 files × bandwidth; GitHub Pages handles this trivially. No server-side cost. |
| Patch day (all users refresh same morning) | GitHub Pages: ETag-cached 304s for unchanged files; only the 1–2 tables that changed return 200. Spike is minutes, not sustained. |
| 10 k+ concurrent installers | GitHub Pages + GitHub Releases handle this without intervention (CDN-fronted). No infra changes required. |

**Scaling Priorities:**

1. **First bottleneck (if any):** GitHub Releases bandwidth for installer downloads. Mitigation: nothing needed at v1; move to self-hosted CDN only if download volume exceeds the Releases quota (currently very generous for public repos).
2. **Second bottleneck:** PyInstaller onefile unpack on slow HDDs (~1–3 s). Mitigation: PyInstaller `--onedir` with NSIS packaging into a folder — 2–3× faster startup, but complicates install UX. **Defer.**

## Anti-Patterns

### Anti-Pattern 1: Hardcoding Port 5000 in the Frontend

**What people do:** `const socket = io('http://localhost:5000')` in `stores/draft.ts` (line 233 — this exists today).
**Why it's wrong:** The sidecar uses a dynamic port. Hardcoded 5000 means the webview talks to whatever else happens to be on 5000, which might be a totally different app, or nothing, causing a mysterious "can't connect" state.
**Do this instead:** `socket = io(await getBackendURL())` — have `getBackendURL()` call `invoke('get_backend_port')` and cache the result. Invalidate on `backend-ready` event.

### Anti-Pattern 2: Using Tauri IPC for Data (Not Discovery)

**What people do:** Migrate Flask routes to Tauri `#[tauri::command]` handlers to "remove the HTTP layer."
**Why it's wrong:** Would require rewriting every route, re-implementing Socket.IO semantics in Tauri events, and coupling domain logic to Tauri. The spec (§3 decision) explicitly rejects this to preserve the Flask/Socket.IO architecture unchanged.
**Do this instead:** Tauri IPC strictly for `get_backend_port`, `restart_backend`, and lifecycle events. HTTP/Socket.IO for everything else.

### Anti-Pattern 3: Shipping the Supabase Client in the Bundle

**What people do:** Leave `supabase` in `requirements.txt` "just in case" and let PyInstaller auto-include it.
**Why it's wrong:** (a) Inflates bundle size by ~15–20 MB; (b) credentials leak risk if anyone later hardcodes env defaults; (c) trips AV heuristics because `supabase-py` depends on `httpx`+`postgrest`+`gotrue` — lots of network code in a compiled .exe.
**Do this instead:** Remove `supabase` from `requirements.txt` and add `excludes=['supabase', 'gotrue', 'postgrest', 'realtime', 'storage3', 'supafunc']` in `backend.spec`. Keep `supabase_repo.py` in the source tree for ETL/admin dev use — just don't let PyInstaller see it.

### Anti-Pattern 4: Polling stdout for Ready Signal

**What people do:** `backend.exe` prints `READY` to stdout, Tauri reads child stdout and waits for that line.
**Why it's wrong:** PyInstaller onefile's bootloader unpacks files to `%TEMP%\_MEIxxxxx` before user code runs; during unpack, stdout buffering is non-deterministic. Also, piped stdout doesn't work cleanly with `CREATE_NO_WINDOW`.
**Do this instead:** Ready-file sentinel. Tauri polls the filesystem (100 ms); Python writes the file after `socketio.init_app`. Filesystem semantics are bulletproof and work regardless of how the bootloader behaved.

### Anti-Pattern 5: Skipping the Job Object

**What people do:** Spawn `backend.exe` as a plain `Command::spawn()` child; rely on killing it in the close handler.
**Why it's wrong:** Task Manager force-kill of Tauri, Windows Fast Startup reboots, and power failures leave the Python child running. Next launch: port is free (since OS reclaimed TCP socket on exit) **but** `%APPDATA%\...\cache\*.json` locks from the dangling child's thread pool can survive and cause I/O errors. Also, users with multiple "stuck" backend.exes eventually notice the RAM footprint.
**Do this instead:** CreateJobObject + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assign child before it runs. One-line FFI via `windows-sys` — worth the 30 lines of unsafe for the reliability guarantee.

### Anti-Pattern 6: Committing `data/*.json` to `main` Branch

**What people do:** Put the exported JSONs on `main` because it's "simpler."
**Why it's wrong:** (a) Bloats git history with daily binary-ish data; (b) couples code-CI to data-CI (a broken ETL blocks code PRs); (c) `main` can't be the GitHub Pages source if the repo also has a Jekyll-free code tree.
**Do this instead:** Dedicated `gh-pages` orphan branch with only `data/` + a minimal `index.html`. `export_to_json.py` does a force-push of a single commit ("Data refresh YYYY-MM-DD") to `gh-pages` — no history accumulates, GitHub Pages picks it up automatically.

### Anti-Pattern 7: Synchronous Per-Table Cold Fetch

**What people do:** 7 sequential `requests.get(...)` calls during startup → ~2–4 s serial stall.
**Why it's wrong:** Visible startup lag; aggregates to worst-case 15 s if one table is slow to cache-miss.
**Do this instead:** `concurrent.futures.ThreadPoolExecutor(max_workers=7)` with per-table timeout=15s; total stall = max(per-table-time), not sum.

## Integration Points (Existing Codebase)

### Named File + Line Diffs

| File | Change | Nature |
|------|--------|--------|
| `counterpick-app/apps/backend/backend.py` lines 1–32 | Add `argparse` for `--port`/`--ready-file`; swap `from lolalytics_api.supabase_repo import …` → `from lolalytics_api.json_repo import …` keeping the `sb_` aliases | Minimal — one import block + argparse stanza |
| `counterpick-app/apps/backend/backend.py` `socketio.run(...)` call site (bottom of file) | Change `socketio.run(app, debug=False)` → `socketio.run(app, host='127.0.0.1', port=args.port)`; after `socketio.init_app(app)` add ready-file write | Two-line delta |
| `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` | **CREATE** — mirror public API of `supabase_repo.py` (9 functions enumerated in "Public API Contract" above) | New module |
| `counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` | None (stays as-is; excluded from PyInstaller bundle) | Frozen |
| `counterpick-app/apps/backend/requirements.txt` | Remove `supabase` + transitive pins; keep `flask`, `flask-socketio`, `requests`, `python-dotenv`, `lxml`, `python-socketio`, `websocket-client` | Dependency subset |
| `counterpick-app/apps/backend/backend.spec` | **CREATE** — `upx=False`, `hiddenimports=['engineio.async_drivers.threading']`, `excludes=['supabase', 'gotrue', 'postgrest', 'realtime', 'storage3', 'supafunc']` | New spec |
| `counterpick-app/apps/backend/league_client_websocket.py` | Hover-weight bug fix (scope: targeted diagnostic + logic patch; spec §7.1) | Small surgical fix |
| `counterpick-app/apps/frontend/src/api/backend.ts` line 11 | Replace `const API_BASE_URL = '/api'` with `let API_BASE_URL: string \| null = null` + an async getter that resolves via `getBackendURL()` + `'/api'`. `fetchApi` awaits the getter. | ~15 line delta |
| `counterpick-app/apps/frontend/src/api/client.ts` | **CREATE** — exports `getBackendURL()`; calls `invoke<number>('get_backend_port')`; listens for `backend-ready` to invalidate cache | New file |
| `counterpick-app/apps/frontend/src/stores/draft.ts` line 233 | `socket = io('http://localhost:5000', …)` → `socket = io(await getBackendURL(), …)` (make `connectWebSocket` async) | One-line logic change, callers updated |
| `counterpick-app/apps/frontend/vite.config.ts` lines 13–21 | `server.proxy./api.target` remains `http://localhost:5000` **only for non-Tauri dev** (`pnpm dev`). In `pnpm tauri dev` the webview bypasses this and uses `getBackendURL()` directly. Leave as-is. | No change |
| `counterpick-app/package.json` scripts | Add `"tauri": "tauri"`, `"tauri:dev": "tauri dev"`, `"tauri:build": "tauri build"`. Add `@tauri-apps/cli` to devDependencies, `@tauri-apps/api` to frontend deps. | New scripts |
| `counterpick-app/src-tauri/` | **CREATE** entire crate (structure under "Recommended Project Structure"). | New crate |
| `supabase-dataset-updater/scripts/export_to_json.py` | **CREATE** — reads Supabase via `service_role`, writes `data/<table>.json` with `__meta`, commits + force-pushes to `gh-pages`. | New script |
| `.github/workflows/update-dataset.yml` | Append a final step: run `export_to_json.py`, configure git, force-push `gh-pages`. Secret `SUPABASE_SERVICE_ROLE_KEY` already exists; add `GITHUB_TOKEN` push scope. | Append step |
| `.github/workflows/release.yml` | **CREATE** — trigger: `push.tags: [v*]`; runner: `windows-latest`; steps: setup-python, pip install, pyinstaller spec, setup-node, pnpm install, pnpm tauri build, sha256, gh release create, updater manifest publish. | New workflow |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Tauri Host ↔ Python Sidecar | OS process (spawn + signals + Job Object) | Ready-file handshake, port via CLI arg |
| Webview ↔ Tauri Host | Tauri IPC (`invoke` + `listen`) | Only `get_backend_port`, `restart_backend`, `backend-ready`, `backend-disconnected` |
| Webview ↔ Python Sidecar | HTTP + Socket.IO on `127.0.0.1:<dyn>` | Identical to current dev-mode traffic; zero route changes |
| Python Sidecar ↔ CDN | HTTPS GET with conditional headers | Read-only, no auth; cache in `%APPDATA%\{bundle_id}\cache\` |
| Python Sidecar ↔ LCU | HTTPS (self-signed) + WebSocket | Unchanged — `league_client_*.py` modules |
| GitHub Actions ETL ↔ Supabase | Service-role key (CI secret) | Unchanged |
| GitHub Actions ETL ↔ `gh-pages` | Force-push single commit via `GITHUB_TOKEN` | New step in existing workflow |

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| GitHub Pages (CDN) | Plain HTTPS GET with ETag/If-Modified-Since | Public; no auth; ~100 ms TTFB from EU; no rate limits for static assets |
| GitHub Releases | Tauri updater HTTPS GET of `latest.json` manifest | Ed25519-signed; key pair generated once via `tauri signer generate`; private key in repo secrets |
| LoL Client (LCU) | HTTPS on dynamic port, self-signed cert | Already integrated; unchanged |
| Supabase | **Removed from client runtime**; remains GitHub Actions-only | ETL-only; client credentials purged |

## Suggested Build Order

Ordering goal: land each piece in isolation, verify it, then integrate. Maximize "one thing broke at a time" debuggability. **Prerequisites → Foundation → Integration → Polish → Release.**

### Phase A: Foundation (no runtime coupling yet)

**A1. Python CLI arg + ready-file (1–2 hours work, completely reversible)**
- Edit `backend.py`: add argparse, ready-file write, `socketio.run(host, port)` args.
- Default port stays 5000 so existing `pnpm dev` workflow is untouched.
- Integration test: `pytest` a subprocess launch with `--port 0 --ready-file <tmp>`.
- **Unblocks:** Tauri spawn logic (A3), PyInstaller spec (A2).

**A2. PyInstaller `backend.spec` + local build (test outside Tauri)**
- Author `backend.spec` with `upx=False`, hidden imports, explicit excludes.
- Run `pyinstaller backend.spec` locally; verify `backend.exe --port 55555 --ready-file t.flag` works standalone.
- Run it against the existing Vue frontend (via the Vite proxy pointed at 55555) — validates the bundle end-to-end without Tauri.
- **Unblocks:** Tauri resource bundling (C1), release workflow (E1).

**A3. `json_repo.py` implementation (can proceed in parallel with A1/A2)**
- Author `json_repo.py` mirroring `supabase_repo.py`'s 9 public functions.
- Tests: mock `requests.get`; verify cache-hit / 304 / cold-fetch / corrupt-recovery paths.
- Initially point `CDN_BASE` at a **local file:// URL** of a hand-crafted fixture JSON so it can be tested before the CDN pipeline is live.
- **Unblocks:** Runtime swap (D1), and uncouples `json_repo` development from the CI/Pages work.

**A4. CDN export script (parallel-safe with A1–A3)**
- Author `supabase-dataset-updater/scripts/export_to_json.py`.
- Run locally against dev Supabase; generate `data/*.json` files with `__meta` envelope.
- Commit manually to `gh-pages` branch once to get the CDN URL working.
- Verify `curl https://{user}.github.io/{repo}/data/champion_stats.json` returns the expected shape.
- **Unblocks:** `json_repo.py` integration test against real CDN (shifts A3 fixture to real URL); update-dataset workflow modification (E2).

### Phase B: Tauri Host Skeleton

**B1. `src-tauri/` crate scaffold**
- `pnpm create tauri-app` in a scratch dir; copy the generated crate into `counterpick-app/src-tauri/`.
- `tauri.conf.json`: bundle id (`dev.till.lol-draft-analyzer`), product name, icons, `devUrl: http://localhost:5173`, `frontendDist: ../apps/frontend/dist`.
- Hello-world `pnpm tauri dev` loads the existing Vue app via the Vite dev server — no sidecar wired yet. Confirms webview integration works.
- **Unblocks:** Sidecar supervision (B2).

**B2. Port allocation + spawn + ready-file poll**
- Implement `src-tauri/src/sidecar.rs::allocate_port()` and `spawn_sidecar()`.
- In `pnpm tauri dev`: spawn the **native** Python (`python backend.py --port <P> --ready-file <R>`) not the exe yet. This tests the lifecycle plumbing without requiring PyInstaller.
- Implement `get_backend_port` Tauri command; expose via `invoke`.
- **Unblocks:** Frontend URL discovery (C2), graceful shutdown (B3).

**B3. Shutdown ladder + Job Object**
- Add `CreateJobObject` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` via `windows-sys`.
- Wire `CTRL_BREAK_EVENT` via `GenerateConsoleCtrlEvent`; fall through to `TerminateProcess` after 2 s.
- Handle Python-side: register `SIGBREAK` handler in `backend.py` calling `socketio.stop()`.
- Test matrix: normal close (X), Task Manager kill of Tauri, backend crash mid-run, Tauri restart.
- **Unblocks:** Reliable dev/prod loops; crash-recovery UI (D3).

### Phase C: Frontend Integration

**C1. Backend-URL discovery client**
- Create `apps/frontend/src/api/client.ts` with `getBackendURL()`.
- Update `api/backend.ts` to `await` it; update `stores/draft.ts` line 233.
- In **Vite dev mode** (non-Tauri), `getBackendURL()` falls back to `'http://localhost:5000'` by detecting `window.__TAURI__` absence — preserves the existing `pnpm dev` workflow.
- **Unblocks:** Full dev-loop `pnpm tauri dev` works end-to-end with native Python.

**C2. Sidecar swap: exe → backend.exe under Tauri**
- `tauri.conf.json` adds the PyInstaller-built `backend.exe` as a `resources/` entry.
- `src-tauri/src/sidecar.rs` switches spawn target from `python backend.py` to `resource_dir/backend.exe` in release builds (keep native-python in dev via `if cfg!(debug_assertions)`).
- Full end-to-end: `pnpm tauri build` → install .msi → app works with bundled sidecar.
- **Unblocks:** Release artifact work (E1).

### Phase D: Data Plane Cutover

**D1. Swap `supabase_repo` → `json_repo` imports in `backend.py`**
- One import block change (lines 11–19 of `backend.py`).
- Remove `supabase_client` import (dead after swap).
- Verify all Flask routes still respond correctly with the `json_repo` backing.
- **Unblocks:** Removing supabase from requirements (D2).

**D2. Purge Supabase from runtime bundle**
- Remove `supabase` from `requirements.txt`.
- Ensure `backend.spec` `excludes` list covers all transitive Supabase deps.
- Rebuild; verify bundle size drops ~15 MB and runtime import errors are clean.
- **Unblocks:** AV/size acceptance criterion.

**D3. Crash-recovery UI**
- Frontend listens for `backend-disconnected` Tauri event → shows banner.
- `restart_backend` command implementation.
- Invalidate memoized `backendURL` on `backend-ready`.
- **Unblocks:** Stability acceptance criteria.

### Phase E: Release Pipeline

**E1. `.github/workflows/release.yml`**
- `windows-latest` runner, `v*` tag trigger.
- Steps: checkout, setup-python, pip install, pyinstaller, setup-node, pnpm install, pnpm tauri build.
- SHA256, gh release create, attach .msi + .exe + latest.json.
- Requires secrets: `TAURI_PRIVATE_KEY`, `TAURI_KEY_PASSWORD`.
- **Unblocks:** First public release.

**E2. Append export step to `update-dataset.yml`**
- After existing `pnpm update`, run `python supabase-dataset-updater/scripts/export_to_json.py`.
- Git commit-force-push to `gh-pages`.
- **Unblocks:** Daily data refresh for installed clients.

**E3. Tauri updater manifest publishing**
- After release, `latest.json` is uploaded as a release asset (or to a stable URL).
- `tauri.conf.json` `updater.endpoints` points at that URL.
- Manual test: install v1.0.0, bump to v1.0.1, verify prompt.

### Build-Order Dependency Graph (What Blocks What)

```
     A1 (CLI args)           A4 (CDN export script)
        │                         │
        ├──┬──────────┐           │
        │  │          │           │
        ▼  ▼          ▼           ▼
      A2          A3 (json_repo   A3-late (point json_repo at real CDN)
 (PyInstaller)    via fixture)        │
        │              │               │
        │              └───────────────┤
        │                              │
        ▼                              ▼
       B1 (Tauri scaffold)        D1 (import swap)
        │                              │
        ▼                              ▼
       B2 (port + spawn native)   D2 (supabase purge)
        │
        ▼
       B3 (shutdown + JobObject)
        │
        ▼
       C1 (frontend URL disco) ◄── requires B2
        │
        ▼
       C2 (swap native→exe) ◄── requires A2 + B3
        │
        ▼
       D3 (crash-recovery UI) ◄── requires B3 + C1
        │
        ▼
       E1 (release.yml) ◄── requires A2 + C2
       E2 (update-dataset append) ◄── requires A4
       E3 (updater manifest) ◄── requires E1
```

**Critical path:** A1 → A2 → B1 → B2 → B3 → C2 → E1. Anything else can run in parallel.

**Highest-leverage parallelism:** A3 and A4 can proceed entirely independently of the Tauri track (B/C). A4 done early unblocks A3 testing against real CDN, which de-risks D1.

**Single biggest "unlocks the demo" milestone:** End of B2 (Tauri spawns native Python with dynamic port) — from that point, the app works end-to-end in dev mode, and all further work is hardening / swapping components underneath a known-good shell.

## Sources

- `F:\Dokumente\Archiv\Riot Api\docs\superpowers\specs\2026-04-14-delivery-form-design.md` — §3 Architecture, §5 IPC/Ports/Lifecycle, §6 Data Backend (authoritative spec)
- `F:\Dokumente\Archiv\Riot Api\.planning\PROJECT.md` — Locked decisions and constraints
- `F:\Dokumente\Archiv\Riot Api\.planning\codebase\ARCHITECTURE.md` — Existing three-tier layering
- `F:\Dokumente\Archiv\Riot Api\.planning\codebase\STRUCTURE.md` — Existing file layout
- `F:\Dokumente\Archiv\Riot Api\.planning\codebase\INTEGRATIONS.md` — Existing integration surface
- `F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\backend\backend.py` (lines 1–32, 53) — Actual import block and Flask init; confirms scope of one-line swap
- `F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\backend\src\lolalytics_api\supabase_repo.py` (public function list) — Verified 9-function public API that `json_repo` must mirror
- `F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\frontend\src\api\backend.ts` (line 11) — Confirms `API_BASE_URL = '/api'` (relative via Vite proxy in dev)
- `F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\frontend\src\stores\draft.ts` (line 233) — Confirms hardcoded `http://localhost:5000` in Socket.IO init
- `F:\Dokumente\Archiv\Riot Api\counterpick-app\apps\frontend\vite.config.ts` (lines 15–20) — Confirms existing dev proxy points at `:5000`
- Tauri v2 documentation (training-data + spec references): sidecar resources pattern, `@tauri-apps/api` `invoke`/`listen`, `path::app_data_dir()`, updater manifest format. **Confidence MEDIUM** on specific API names — verify via Context7 during implementation; the architectural shape does not depend on exact names.
- PyInstaller documentation (training-data): `upx=False`, `excludes`, `hiddenimports`, onefile bootloader behavior. **Confidence HIGH** for architectural claims; spec-level details in the delivery-form spec are already validated by the author.
- Win32 Job Object API (training-data): `CreateJobObject`, `SetInformationJobObject`, `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`. **Confidence HIGH** — stable Win32 API since XP.
- Windows process groups / `GenerateConsoleCtrlEvent` with `CREATE_NEW_PROCESS_GROUP`. **Confidence HIGH** — documented Win32 behavior.

---
*Architecture research for: Tauri desktop shell + PyInstaller Flask/Socket.IO sidecar + CDN-JSON data plane*
*Researched: 2026-04-14*
