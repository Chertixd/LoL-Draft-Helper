# Requirements: LoL Draft Analyzer — v1 Desktop Delivery

**Defined:** 2026-04-14
**Core Value:** Zero-friction delivery: a non-technical LoL player downloads one installer and has working draft recommendations — no Python, no Node, no credentials, no command line.

## v1 Requirements

Requirements for the v1 desktop delivery release. Each maps to exactly one roadmap phase.

### Sidecar Packaging (Python backend as standalone `.exe`)

- [ ] **SIDE-01**: `backend.py` accepts `--port <int>` and `--ready-file <path>` CLI arguments and binds Flask-SocketIO on `127.0.0.1:<port>`
- [ ] **SIDE-02**: Backend writes the ready-file only AFTER an in-process HTTP health probe confirms the Flask server is accepting connections
- [ ] **SIDE-03**: PyInstaller `backend.spec` produces a single-file `backend.exe` Windows binary with `upx=False`, correct hidden imports (`engineio.async_drivers.threading`, `httpx.socks`, others surfaced by CI), `certifi` data files bundled, and `supabase`/`gotrue`/`postgrest`/`realtime`/`storage3` excluded
- [ ] **SIDE-04**: Built `backend.exe` passes a CI smoke test: standalone launch, Socket.IO round-trip, HTTPS CDN fetch, and VirusTotal detections ≤ 3
- [ ] **SIDE-05**: Resource resolution uses `sys._MEIPASS` for bundled read-only files and `platformdirs.user_data_dir()` for read/write paths — no hardcoded `__file__` paths

### CDN Data Plane (client no longer talks to Supabase)

- [ ] **CDN-01**: New `json_repo.py` mirrors the public API of `supabase_repo.py` — identical function signatures and return shapes for `get_champion_stats`, `get_champion_stats_by_role`, `get_matchups`, `get_synergies`, `get_items`, `get_runes`, and `get_summoner_spells`
- [ ] **CDN-02**: `json_repo.py` fetches JSON files from the GitHub Pages CDN base URL and caches them in `%APPDATA%\{bundle_id}\cache\` as `<table>.json` + `<table>.meta.json` (ETag, Last-Modified, fetched_at, sha256)
- [ ] **CDN-03**: On backend startup, `json_repo` issues one conditional GET per table (`If-None-Match` / `If-Modified-Since`); on HTTP 304 it reuses cache; on 200 it atomically replaces cache via write-to-temp + rename
- [ ] **CDN-04**: Corrupt cache (JSON parse error) is automatically deleted and re-fetched on next access
- [ ] **CDN-05**: `supabase-dataset-updater/scripts/export_to_json.py` exports the required tables to JSON with a top-level `__meta` envelope (`exported_at`, `sha256`) and publishes them to a `gh-pages` branch
- [ ] **CDN-06**: The ETL GitHub Actions workflow runs `export_to_json.py` after each ETL write, so the CDN is refreshed daily
- [ ] **CDN-07**: GitHub Pages is configured to serve the `gh-pages` branch at a stable public URL, baked into `tauri.conf.json` as a config constant
- [ ] **CDN-08**: `supabase-py` is removed from `requirements.txt` on the runtime path; `supabase_repo.py` remains in-repo for ETL/dev use only

### Tauri Shell (Rust desktop host)

- [ ] **TAURI-01**: `src-tauri/` Rust crate with `main.rs`, `tauri.conf.json`, and finalized `identifier` (e.g. `dev.till.lol-draft-analyzer`) committed before any release build
- [ ] **TAURI-02**: Tauri host allocates a free localhost port by binding `127.0.0.1:0` with a `TcpListener`, reading `.local_addr()`, then dropping the listener, before spawning the sidecar
- [ ] **TAURI-03**: Tauri spawns `backend.exe --port <allocated> --ready-file <tmp>` inside a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` so the OS kills the child if Tauri exits unexpectedly
- [ ] **TAURI-04**: Tauri polls for the ready-file (100 ms interval, 10 s timeout); the Webview window is only shown once the file appears
- [ ] **TAURI-05**: Tauri exposes a `get_backend_port` IPC command returning the allocated port and a `restart_backend` IPC command that re-spawns the sidecar
- [ ] **TAURI-06**: On normal app close, Tauri sends a graceful shutdown (`CTRL_BREAK_EVENT`), waits 2 seconds, then hard-kills via `TerminateProcess`
- [ ] **TAURI-07**: If the sidecar fails to become ready within 10 seconds, Tauri shows an error dialog (with a link to the README AV-troubleshooting section) and exits cleanly
- [ ] **TAURI-08**: If the sidecar exits during runtime, Tauri emits a `backend-disconnected` event consumed by the frontend
- [ ] **TAURI-09**: Only a single Tauri instance is allowed per machine (via `tauri-plugin-single-instance`); launching a second copy focuses the existing window
- [ ] **TAURI-10**: A Rust smoke test covers spawn → ready → clean shutdown on `windows-latest` with 50× repeats and zero flakes
- [ ] **TAURI-11**: Task-Manager-kill of the Tauri host results in `backend.exe` process count returning to zero within 1 second

### Frontend Integration (Vue talks to sidecar over dynamic port)

- [ ] **FRONT-01**: New `apps/frontend/src/api/client.ts` exports `getBackendURL()`, which calls `invoke<number>('get_backend_port')` on first use and returns `http://127.0.0.1:<port>`; falls back to `http://localhost:5000` when `window.__TAURI__` is absent (pure-browser dev mode)
- [ ] **FRONT-02**: `apps/frontend/src/api/backend.ts` (line 11) and `apps/frontend/src/stores/draft.ts` (line 233) are updated to use `getBackendURL()` instead of the hardcoded `localhost:5000`
- [ ] **FRONT-03**: Frontend listens for the `backend-disconnected` Tauri event and shows a banner with a "Restart" button that invokes `restart_backend`; Socket.IO's default exponential backoff is preserved
- [ ] **FRONT-04**: Frontend shows a full-screen "Waiting for League of Legends…" view when the LCU is not running (polling every 3 s)

### First-Run UX and Error States

- [ ] **UX-01**: On first run with no local cache, the app downloads CDN data with a visible per-table progress indicator
- [ ] **UX-02**: On first run with no network and no cache, the app shows a clear error banner with a Retry button (exponential backoff); no crash
- [ ] **UX-03**: When the CDN is unreachable but a local cache exists, the app silently uses the cache and shows a "using cached data from <date>" indicator; background retry every 10 minutes
- [ ] **UX-04**: The cached-data staleness indicator turns amber when data is older than 48 hours and red when older than 7 days

### Hover-Detection Fix (in-scope targeted improvement)

- [ ] **HOVER-01**: Add temporary diagnostic logging of all LCU events (`type` + `resource`) during champion select, identify which event-type carries hover vs confirmed-pick state, patch `league_client_websocket.py` so hovered picks reach `recommendation_engine` with the reduced-weight flag set, and remove diagnostic logging before release

### Logging and Diagnostics (enables user-submitted bug reports)

- [ ] **LOG-01**: The Python backend writes structured log files to `%APPDATA%\{bundle_id}\logs\backend-<YYYY-MM-DD>.log` with daily rotation
- [ ] **LOG-02**: The Tauri host (Rust `log` crate) writes logs to the same `%APPDATA%\{bundle_id}\logs\` directory
- [ ] **LOG-03**: Frontend `console.*` output is visible via Tauri devtools in dev mode and disabled in production builds
- [ ] **LOG-04**: Log filenames include the finalized `{bundle_id}` string; the README documents the exact literal path
- [ ] **LOG-05**: LCU auth tokens / passwords are redacted at write-time before they reach log files

### Auto-Update (Tauri updater via GitHub Releases)

- [ ] **UPD-01**: Tauri updater is configured with `createUpdaterArtifacts: true` and a signing key pair generated via `tauri signer generate`; keys are stored in repo secrets (`TAURI_PRIVATE_KEY`, `TAURI_KEY_PASSWORD`)
- [ ] **UPD-02**: A signed `latest.json` manifest is published to the `gh-pages` branch (NOT as a release asset) so rollback is a `git revert`
- [ ] **UPD-03**: The Tauri updater detects newer releases and presents a prompt with release notes; the user can choose Install or Later (default Tauri updater prompt is acceptable for v1)
- [ ] **UPD-04**: A `GET /api/draft/active` backend endpoint returns draft-session state; the updater defers `installAndRelaunch()` when a draft is active
- [ ] **UPD-05**: The updater private key is stored in three places (password manager + GitHub Actions secret + offline encrypted USB or printed QR) with recovery procedure documented in `docs/RELEASE.md`

### Build Pipeline and CI/CD

- [ ] **BUILD-01**: `.github/workflows/release.yml` triggers on `v*` git tags on `windows-latest` and runs: checkout → Python setup → `pip install -r requirements.txt pyinstaller` → `pyinstaller apps/backend/backend.spec` → Node setup → `pnpm install` → `pnpm tauri build`
- [ ] **BUILD-02**: The workflow produces a `.msi` installer and a portable `.exe` (NSIS `-setup.exe`) as GitHub Release assets; installer size ≤ 100 MB
- [ ] **BUILD-03**: The workflow computes SHA256 hashes of both artifacts and includes them in the GitHub Release notes
- [ ] **BUILD-04**: The workflow publishes the signed `latest.json` to the `gh-pages` branch for the updater
- [ ] **BUILD-05**: Every push to `main` runs a build smoke check (build only, no release)
- [ ] **BUILD-06**: Dev workflow `pnpm tauri dev` spawns the backend natively with `python backend.py --port <auto> --ready-file <tmp>` and loads Vite HMR from `http://localhost:5173`, so developer ergonomics are preserved

### Installation and Runtime (end-to-end acceptance)

- [ ] **INST-01**: The `.msi` installer completes on clean Windows 10 and Windows 11 without requiring admin rights (per-user install)
- [ ] **INST-02**: A Start Menu entry "LoL Draft Analyzer" is created; the uninstaller removes the app and its cache
- [ ] **INST-03**: The app opens from the Start Menu shortcut without any credential entry or command-line interaction
- [ ] **INST-04**: The LoL client is detected within 3 seconds of being started; draft state is displayed in real time
- [ ] **INST-05**: Recommendation scores are produced for all 5 roles at every pick event for the supported game modes (Normal Draft, Ranked Solo/Duo, Ranked Flex, Clash); blind-pick recommendation mode inside those drafts is preserved
- [ ] **INST-06**: Closing the LoL client does not crash the app — the waiting view reappears; reopening auto-reconnects
- [ ] **INST-07**: 2 h idle runtime with LoL open and no active draft grows RAM by less than 50 MB
- [ ] **INST-08**: 20 consecutive drafts without restart show no functional degradation
- [ ] **INST-09**: Auto-update flow verified end-to-end: install v1.0.0, tag v1.0.1, updater prompts, install, app relaunches on new version

### Documentation (AV/SmartScreen mitigation depends on this)

- [ ] **DOC-01**: README documents the installer download link, SHA256 verification, SmartScreen "More info → Run anyway" walkthrough with screenshots, AV false-positive guidance (link to Microsoft submission form), and the literal `%APPDATA%\{bundle_id}\logs\` log-folder path
- [ ] **DOC-02**: README includes an MSI-vs-portable FAQ explaining the two download options
- [ ] **DOC-03**: A CHANGELOG entry exists for v1.0.0
- [ ] **DOC-04**: `docs/RELEASE.md` documents the updater key ceremony (generation, three-copy storage, recovery procedure, rehearsed rotation)

## v2 Requirements

Deferred to a follow-on release. Acknowledged but not in v1 scope.

### Auto-Update Polish

- **UPD-V2-01**: Custom updater UI with "Install on next launch" option (custom UI replacing default Tauri prompt)
- **UPD-V2-02**: Persist champion-select state to `%APPDATA%\{bundle_id}\draft_session.json` per pick for mid-session resilience beyond the in-memory case

### Diagnostics Polish

- **DIAG-V2-01**: "Open log folder" button in the app
- **DIAG-V2-02**: "Copy diagnostics" button (version + OS + log tail → clipboard, with LCU auth redaction already enforced by LOG-05)

### Supabase Hardening (ETL-side)

- **DB-V2-01**: Supabase connection pooling, query audit, index coverage review — urgency reduced because clients no longer hit Supabase, but the ETL benefits

### Cross-Platform

- **PLAT-V2-01**: macOS build (LoL has ~5% share on macOS)

## Out of Scope

Explicitly excluded from v1. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| macOS build | LoL on macOS has ~5% share; Windows-only focus for v1 |
| Linux build | Riot does not support LoL on Linux |
| EV code signing certificate | ~$200–400/year not justified for a non-commercial v1 |
| Nuitka migration (alternative to PyInstaller) | Only if AV friction dominates user feedback |
| FastAPI migration (Flask → FastAPI) | Flask is adequate; not a bottleneck |
| Telemetry or crash-reporting SaaS | Privacy-preserving v1; if ever added, must be opt-in |
| User settings / preferences UI | None shipped in v1 |
| Auto-launch on Windows startup | Out of scope; anti-feature |
| System-tray presence | Out of scope; anti-feature |
| Direct Supabase connectivity from installed client | Replaced by CDN JSON read path |
| Non-Summoner's-Rift modes (ARAM, Arena, Nexus Blitz, TFT) | Different data domain; no matchup data applies |
| LoL "Blind Pick" queue | Structurally unsupported — no champion-select phase with visible picks/hovers/bans |
| Co-op vs AI, Practice Tool, Custom games | No ranked meta data relevant |
| Tauri-IPC as the Vue↔Python data channel | Rejected by spec §3 in favor of preserving HTTP + Socket.IO |
| Silent or forced mid-draft updates | Anti-feature; mid-draft force-update destroys champion-select state |
| Multi-channel (stable/beta) update feeds | v1 has one channel |
| GitHub publishing readiness (license/legal/README polish beyond install and troubleshooting) | Separate spec |
| Overlay UX polish beyond the hover-detection fix | Separate spec |

## Traceability

Which phases cover which requirements.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SIDE-01 | Phase 1 — Sidecar Foundation | Pending |
| SIDE-02 | Phase 1 — Sidecar Foundation | Pending |
| SIDE-03 | Phase 1 — Sidecar Foundation | Pending |
| SIDE-04 | Phase 1 — Sidecar Foundation | Pending |
| SIDE-05 | Phase 1 — Sidecar Foundation | Pending |
| CDN-01 | Phase 2 — CDN Data Plane | Pending |
| CDN-02 | Phase 2 — CDN Data Plane | Pending |
| CDN-03 | Phase 2 — CDN Data Plane | Pending |
| CDN-04 | Phase 2 — CDN Data Plane | Pending |
| CDN-05 | Phase 2 — CDN Data Plane | Pending |
| CDN-06 | Phase 2 — CDN Data Plane | Pending |
| CDN-07 | Phase 2 — CDN Data Plane | Pending |
| CDN-08 | Phase 2 — CDN Data Plane | Pending |
| TAURI-01 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-02 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-03 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-04 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-05 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-06 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-07 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-08 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-09 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-10 | Phase 3 — Tauri Shell + Integration | Pending |
| TAURI-11 | Phase 3 — Tauri Shell + Integration | Pending |
| FRONT-01 | Phase 3 — Tauri Shell + Integration | Pending |
| FRONT-02 | Phase 3 — Tauri Shell + Integration | Pending |
| FRONT-03 | Phase 3 — Tauri Shell + Integration | Pending |
| FRONT-04 | Phase 3 — Tauri Shell + Integration | Pending |
| UX-01 | Phase 3 — Tauri Shell + Integration | Pending |
| UX-02 | Phase 3 — Tauri Shell + Integration | Pending |
| UX-03 | Phase 3 — Tauri Shell + Integration | Pending |
| UX-04 | Phase 3 — Tauri Shell + Integration | Pending |
| HOVER-01 | Phase 3 — Tauri Shell + Integration | Pending |
| LOG-01 | Phase 3 — Tauri Shell + Integration | Pending |
| LOG-02 | Phase 3 — Tauri Shell + Integration | Pending |
| LOG-03 | Phase 3 — Tauri Shell + Integration | Pending |
| LOG-04 | Phase 3 — Tauri Shell + Integration | Pending |
| LOG-05 | Phase 3 — Tauri Shell + Integration | Pending |
| UPD-01 | Phase 4 — Release Pipeline & Distribution | Pending |
| UPD-02 | Phase 4 — Release Pipeline & Distribution | Pending |
| UPD-03 | Phase 4 — Release Pipeline & Distribution | Pending |
| UPD-04 | Phase 4 — Release Pipeline & Distribution | Pending |
| UPD-05 | Phase 4 — Release Pipeline & Distribution | Pending |
| BUILD-01 | Phase 4 — Release Pipeline & Distribution | Pending |
| BUILD-02 | Phase 4 — Release Pipeline & Distribution | Pending |
| BUILD-03 | Phase 4 — Release Pipeline & Distribution | Pending |
| BUILD-04 | Phase 4 — Release Pipeline & Distribution | Pending |
| BUILD-05 | Phase 4 — Release Pipeline & Distribution | Pending |
| BUILD-06 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-01 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-02 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-03 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-04 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-05 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-06 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-07 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-08 | Phase 4 — Release Pipeline & Distribution | Pending |
| INST-09 | Phase 4 — Release Pipeline & Distribution | Pending |
| DOC-01 | Phase 4 — Release Pipeline & Distribution | Pending |
| DOC-02 | Phase 4 — Release Pipeline & Distribution | Pending |
| DOC-03 | Phase 4 — Release Pipeline & Distribution | Pending |
| DOC-04 | Phase 4 — Release Pipeline & Distribution | Pending |

**Coverage:**
- v1 requirements: 62 total (5 SIDE + 8 CDN + 11 TAURI + 4 FRONT + 4 UX + 1 HOVER + 5 LOG + 5 UPD + 6 BUILD + 9 INST + 4 DOC)
- Mapped to phases: 62 (100%) ✓
- Unmapped: 0

> **Note on count discrepancy:** The original requirements doc footer stated "49 total" but the enumerated list contains 62 distinct requirement IDs. All 62 are mapped. The "49" in upstream planning notes is stale and should be treated as outdated.

**Per-phase distribution:**
- Phase 1 (Sidecar Foundation): 5 requirements (SIDE-01..05)
- Phase 2 (CDN Data Plane): 8 requirements (CDN-01..08)
- Phase 3 (Tauri Shell + Integration): 25 requirements (TAURI-01..11, FRONT-01..04, UX-01..04, HOVER-01, LOG-01..05)
- Phase 4 (Release Pipeline & Distribution): 24 requirements (UPD-01..05, BUILD-01..06, INST-01..09, DOC-01..04)

---
*Requirements defined: 2026-04-14*
*Last updated: 2026-04-14 after roadmap creation — traceability populated, 100% coverage*
