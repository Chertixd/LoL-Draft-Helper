# Roadmap: LoL Draft Analyzer — v1 Desktop Delivery

## Overview

Ship the existing Flask + Vue draft analyzer as a one-click Windows desktop app. Four phases: build the PyInstaller sidecar with locked-down hidden imports and AV-mitigated spec (Phase 1); stand up the GitHub-Pages CDN data plane so clients never touch Supabase (Phase 2, parallel with 1 and 3); wrap both in a Tauri Rust shell with dynamic-port sidecar lifecycle, frontend URL discovery, error states, hover-fix, and logging (Phase 3, the "unlocks demo" milestone); then drive the tagged-release pipeline, auto-updater ceremony, end-to-end acceptance on clean Windows, and user-facing docs to v1.0.0 (Phase 4).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

**Parallelization:** Phase 1 (Sidecar Foundation) and Phase 2 (CDN Data Plane) have no dependency on each other and can execute in parallel. Phase 3 (Tauri Shell + Integration) consumes the output of both before it can reach its demo gate.

- [ ] **Phase 1: Sidecar Foundation** - PyInstaller-packaged `backend.exe` with CLI args, ready-file health probe, AV-safe spec, and `_MEIPASS`/`user_data_dir` resource handling
- [ ] **Phase 2: CDN Data Plane** - `json_repo.py` drop-in for `supabase_repo.py` plus Supabase→JSON export workflow publishing to `gh-pages`, so clients never hit Supabase
- [ ] **Phase 3: Tauri Shell + Integration** - Rust host allocates port, spawns sidecar inside a Windows Job Object, Vue discovers backend via IPC, disconnected/waiting/stale-cache states wired, hover bug fixed, logging centralized — end-to-end draft flow works locally
- [ ] **Phase 4: Release Pipeline & Distribution** - Tag-triggered CI produces signed `.msi` + portable `.exe`, updater key ceremony complete, `latest.json` on `gh-pages`, mid-draft update deferral, clean-Windows acceptance passes, README and CHANGELOG shipped

## Phase Details

### Phase 1: Sidecar Foundation
**Goal**: A built `backend.exe` can stand alone — it accepts a dynamic port, announces readiness only after proving the server accepts connections, fetches HTTPS CDN data successfully, and passes a VirusTotal sanity threshold.
**Depends on**: Nothing (parallel track A — first phase on sidecar path)
**Requirements**: SIDE-01, SIDE-02, SIDE-03, SIDE-04, SIDE-05
**Success Criteria** (what must be TRUE):
  1. `python backend.py --port 0 --ready-file <tmp>` binds Flask-SocketIO on a caller-chosen loopback port and the ready-file only appears after an in-process `GET /api/health` returns 200.
  2. `pyinstaller apps/backend/backend.spec` produces a single-file `backend.exe` built with `upx=False`, `engineio.async_drivers.threading` and `httpx.socks` hidden-imports present, `certifi` data files bundled, and `supabase`/`gotrue`/`postgrest`/`realtime`/`storage3` excluded.
  3. CI smoke test launches the built `.exe`, round-trips a Socket.IO event, performs an HTTPS CDN fetch end-to-end, and VirusTotal reports ≤ 3 detections.
  4. Read-only resources resolve through a `bundled_resource()` helper backed by `sys._MEIPASS`; read/write paths resolve through `user_data_dir()`/`platformdirs` — no `__file__` or `cwd()` path resolution remains in the runtime code path.
**Plans**: 3 plans
Plans:
- [x] 01-01-PLAN.md — resources.py helper module + backend.spec PyInstaller recipe (SIDE-03, SIDE-05)
- [x] 01-02-PLAN.md — backend.py main() rewrite with argparse + /api/health + probe thread + ready-file (SIDE-01, SIDE-02)
- [x] 01-03-PLAN.md — test_backend_cli.py + smoke_test_exe.py + build-smoke CI workflow (SIDE-04)

### Phase 2: CDN Data Plane
**Goal**: The Supabase read path is replaced end-to-end with a public GitHub-Pages CDN plus a conditional-GET local cache, and the ETL publishes fresh JSON daily without any client-side Supabase credential.
**Depends on**: Nothing (parallel track B — independent of Phase 1 and Phase 3 per ARCHITECTURE.md "CDN data plane has zero dependency on the Tauri track")
**Requirements**: CDN-01, CDN-02, CDN-03, CDN-04, CDN-05, CDN-06, CDN-07, CDN-08
**Success Criteria** (what must be TRUE):
  1. `json_repo.py` exports the same 9-function public surface as `supabase_repo.py` — identical signatures and row shapes for `get_champion_stats`, `get_champion_stats_by_role`, `get_matchups`, `get_synergies`, `get_items`, `get_runes`, `get_summoner_spells` — verified by a contract test per function against the real CDN.
  2. A cold-start fetches each table over HTTPS and caches it under `%APPDATA%\{bundle_id}\cache\<table>.json` + `<table>.meta.json`; a warm start issues conditional GETs, accepts 304 by reusing cache, and handles 200 via write-to-temp + `os.replace`.
  3. Truncating or JSON-corrupting any cached file and restarting the backend self-heals by deleting the bad file and re-fetching; no user action required.
  4. After each daily ETL run, `export_to_json.py` force-pushes fresh JSON (with `__meta.exported_at` and `__meta.sha256`) to the `gh-pages` orphan branch and `curl https://<pages-url>/data/champion_stats.json` returns the expected envelope within 10 minutes.
  5. `supabase-py` is absent from the runtime `requirements.txt` and from the PyInstaller bundle; `supabase_repo.py` remains in-repo for ETL/dev-only use.
**Plans**: 4 plans
Plans:
- [x] 02-01-PLAN.md — json_repo.py + test_json_repo_cache.py (client-side CDN read path + mocked-HTTP unit tests) [Wave 1, parallel with 02-02]
- [x] 02-02-PLAN.md — export_to_json.py + test_export_to_json.py (server-side Supabase to JSON exporter with canonical sha256 envelope) [Wave 1, parallel with 02-01]
- [ ] 02-03-PLAN.md — update-dataset.yml GitHub Actions extension + docs/DATA-PIPELINE.md operator runbook + human-action checkpoint to confirm CDN is live [Wave 2, depends on 02-02]
- [ ] 02-04-PLAN.md — atomic CDN cutover (single commit: backend.py import swap + requirements.txt supabase removal + backend.spec excludes restore + CI guard re-enable + test_json_repo_contract.py) [Wave 3, depends on 02-01 AND 02-03]

### Phase 3: Tauri Shell + Integration
**Goal**: A developer running `pnpm tauri dev` (or a fresh `pnpm tauri build` install) can open the app, see it wait politely for League, then drive a full draft end-to-end — with the backend sidecar supervised, frontend using IPC-discovered URLs, disconnect/restart wired, hover-fix active, and logs centralized. This is the "unlocks demo" milestone.
**Depends on**: Phase 1 (needs `backend.exe` to spawn) AND Phase 2 (needs `json_repo.py` for the cutover)
**Requirements**: TAURI-01, TAURI-02, TAURI-03, TAURI-04, TAURI-05, TAURI-06, TAURI-07, TAURI-08, TAURI-09, TAURI-10, TAURI-11, FRONT-01, FRONT-02, FRONT-03, FRONT-04, UX-01, UX-02, UX-03, UX-04, HOVER-01, LOG-01, LOG-02, LOG-03, LOG-04, LOG-05
**Success Criteria** (what must be TRUE):
  1. From a cold Tauri start, the Rust host allocates a free loopback port, spawns `backend.exe` inside a Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`), polls the ready-file with a 10 s timeout, and only then shows the Webview; a 50× repeat of this flow on `windows-latest` passes with zero flakes.
  2. Force-killing the Tauri host via Task Manager reduces the system's `backend.exe` process count to zero within 1 second, and launching a second app instance focuses the existing window instead of spawning a second sidecar.
  3. The Vue frontend calls `invoke('get_backend_port')` to discover `http://127.0.0.1:<dyn-port>`, all hardcoded `localhost:5000` references in `apps/frontend/src/api/backend.ts` and `apps/frontend/src/stores/draft.ts` are gone, and the pure-browser dev fallback to `http://localhost:5000` still works.
  4. User-facing error/waiting states behave correctly: a full-screen "Waiting for League of Legends…" view appears when the LCU lockfile is absent; a disconnected banner with a working Restart button appears on backend exit; first-run with no cache shows per-table download progress; offline-with-no-cache shows a Retry banner without crashing; offline-with-cache silently uses the cache and shows a staleness indicator that turns amber > 48 h and red > 7 days.
  5. In an LCU champion-select trace, hovered picks reach `recommendation_engine` with the reduced-weight flag set (previously ignored); diagnostic LCU-event logging used to root-cause the fix is removed before the phase closes.
  6. Both Python and Rust logs land in `%APPDATA%\{bundle_id}\logs\backend-<YYYY-MM-DD>.log` (with daily rotation) and `%APPDATA%\{bundle_id}\logs\tauri-<YYYY-MM-DD>.log`; LCU auth tokens are redacted at write-time; frontend `console.*` is visible in Tauri devtools in dev and stripped in production.
**Plans**: TBD
**UI hint**: yes

### Phase 4: Release Pipeline & Distribution
**Goal**: Tagging `v1.0.0` produces a public GitHub Release with an `.msi` installer and portable `.exe` that a non-technical user on a clean Windows machine can download, install without admin rights, launch from the Start Menu, and receive a future `v1.0.1` auto-update for — without losing mid-draft state.
**Depends on**: Phase 3 (needs a working end-to-end app to package and release)
**Requirements**: UPD-01, UPD-02, UPD-03, UPD-04, UPD-05, BUILD-01, BUILD-02, BUILD-03, BUILD-04, BUILD-05, BUILD-06, INST-01, INST-02, INST-03, INST-04, INST-05, INST-06, INST-07, INST-08, INST-09, DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):
  1. Pushing a `v*` tag to `main` on `windows-latest` runs `pyinstaller backend.spec` → `pnpm install` → `pnpm tauri build` → SHA256 hash computation → GitHub Release creation with both `.msi` and portable `-setup.exe` attached (each ≤ 100 MB) → `latest.json` published to the `gh-pages` branch as a separate file (not a release asset, so rollback is a `git revert`); every push to `main` also runs a build-only smoke check, and `pnpm tauri dev` preserves native-Python hot-reload for developers.
  2. The updater key pair exists in three independent locations (password manager, `TAURI_PRIVATE_KEY` GitHub Actions secret, offline encrypted backup), the recovery procedure is documented in `docs/RELEASE.md`, a rehearsed rotation has completed in staging, and the key is never prefixed with `VITE_` (GHSA-2rcp-jvr4-r259).
  3. On a clean Windows 10 and Windows 11 machine, the `.msi` installs per-user without admin rights, creates a "LoL Draft Analyzer" Start Menu entry, opens without any credential prompt or command-line step, detects a running LoL client within 3 s, produces recommendations for all 5 roles on every pick across Normal Draft / Ranked Solo/Duo / Ranked Flex / Clash (with blind-pick mode preserved), survives a LoL client close-and-reopen by showing the waiting view and auto-reconnecting, and the uninstaller removes the app and its cache.
  4. Stability gates pass: 2 h idle runtime with LoL open and no active draft grows RAM by less than 50 MB, and 20 consecutive drafts without restart show no functional degradation.
  5. The auto-update flow is verified end-to-end: install v1.0.0 → tag v1.0.1 → updater prompts with release notes → user accepts → app relaunches on v1.0.1; if `GET /api/draft/active` returns `{active: true}`, `installAndRelaunch()` is deferred until the draft ends.
  6. README documents the installer download link, SHA256 verification, SmartScreen "More info → Run anyway" walkthrough with screenshots, AV false-positive guidance (with the Microsoft submission link), the literal `%APPDATA%\{bundle_id}\logs\` path (with the final real bundle_id, not a placeholder), and an MSI-vs-portable FAQ; `CHANGELOG.md` has a v1.0.0 entry.
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases 1 and 2 may execute in parallel. Phase 3 requires both 1 and 2. Phase 4 requires 3.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Sidecar Foundation | 0/3 | Not started | - |
| 2. CDN Data Plane | 0/4 | Not started | - |
| 3. Tauri Shell + Integration | 0/TBD | Not started | - |
| 4. Release Pipeline & Distribution | 0/TBD | Not started | - |
