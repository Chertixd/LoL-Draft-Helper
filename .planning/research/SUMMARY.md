# Research Summary — LoL Draft Analyzer, v1 Desktop Delivery

**Milestone:** Windows desktop packaging of an existing Flask + Vue web app for non-technical LoL players
**Domain:** Tauri v2 shell + PyInstaller sidecar + GitHub Pages CDN JSON data plane + Tauri auto-updater
**Researched:** 2026-04-14
**Overall confidence:** HIGH

> **Scope note.** Only NEW-to-this-milestone tech is researched. The existing Flask / Vue / Supabase / LCU codebase is locked — not re-summarized here.

## Executive Summary

Tauri v2 Rust shell spawns a PyInstaller onefile `backend.exe` sidecar on a dynamically-allocated localhost port. Vue ↔ Python keeps HTTP + Socket.IO exactly as today; Tauri IPC is used only for `get_backend_port` / `restart_backend`. A new `json_repo.py` mirrors the public API of `supabase_repo.py` but reads from a public GitHub Pages CDN populated by the nightly ETL, cached in `%APPDATA%\{bundle_id}\cache\` via conditional GET. Auto-updates use the Tauri v2 updater with an Ed25519-signed `latest.json` hosted on `gh-pages`. No code signing in v1 — AV friction mitigated procedurally via `upx=False`, SHA256 in release notes, README SmartScreen walkthrough, Microsoft false-positive submissions. Dominant risks: AV quarantine, orphaned sidecar processes on Tauri crash, lost updater private key, and mid-draft force-updates.

## Recommended Stack (NEW tech only)

| Component | Pick | Version | Confidence |
|-----------|------|---------|------------|
| Desktop shell | Tauri | 2.10.x | HIGH |
| Python bundler | PyInstaller (`--onefile`, `upx=False`) | 6.19.0 | HIGH |
| Rust toolchain | Stable (MSRV 1.88) | ≥ 1.88 | MEDIUM |
| Node / pnpm (CI) | Node 20 LTS / pnpm 9.2.0 | locked | HIGH |
| Installer target | WiX v3 `.msi` + NSIS `-setup.exe` | auto-provisioned | HIGH |
| Tauri plugins | `shell`, `updater`, `log`, `single-instance` | 2.x | HIGH |
| Windows Job Object | `win32job` crate | 2.0.0 | MEDIUM |
| CDN client | stdlib `requests` + hand-written ETag cache | — | HIGH |

**Tauri config locks (must be set explicitly):**
- `bundle.targets = ["msi", "nsis"]`
- `webviewInstallMode = { type: "downloadBootstrapper" }`
- NSIS `installMode = "perUser"`
- `createUpdaterArtifacts = true` (without this, `.sig` files don't exist and updater silently breaks — #1 2026 footgun)
- Final `identifier` (e.g. `dev.till.lol-draft-analyzer`) must be fixed before Phase 3 ships — changing later orphans user caches/logs.

**Removed from runtime bundle:** `supabase-py` + all Supabase credentials. `supabase_repo.py` stays in source for ETL/dev-mode only.

**Do not use:** Tauri v1 (EOL, incompatible config); `requests-cache` (+3 MB + SQLite inflates AV-fingerprint surface — a ~30 LoC manual cache suffices); UPX compression (triples AV false-positive rate); Tauri-IPC as primary Vue↔Python data channel (rejected by spec §3).

## Feature Triage

### Table Stakes (P1 — spec §8 acceptance gates)
- `.msi` + portable `.exe` as GitHub Release assets
- SHA256 hashes published in release notes
- Per-user install, no admin rights, Start Menu entry, working uninstaller
- README with SmartScreen walkthrough (screenshots) + AV guidance + literal log-folder path
- First-run: visible per-table CDN download progress; offline error + Retry; no crash
- Cached-data staleness indicator (amber > 48 h, red > 7 d)
- Backend-disconnected banner + Restart button
- "Waiting for League of Legends…" view
- Tauri auto-updater wired to signed `latest.json` (default prompt UX is acceptable for v1)
- Structured logs in `%APPDATA%\{bundle_id}\logs\`, daily rotation
- Hover-detection fix in `league_client_websocket.py` (spec §7.1)

### Differentiators (P2 — post-launch on real feedback)
- "Install on next launch" update option (custom updater UI; avoids mid-draft interruption) — **consider elevating to P1** because it addresses the single worst UX failure mode
- "Open log folder" button; "Copy diagnostics" button (with LCU-auth redaction)
- Version number in title bar / About screen
- First-run welcome screen; optional desktop shortcut

### Anti-Features (all map to PROJECT.md Out of Scope / spec §10)
- Silent or forced mid-draft updates; telemetry; crash-reporting SaaS
- EV code signing in v1; auto-launch on Windows startup; system-tray presence
- User settings/preferences UI in v1; macOS / Linux builds
- Direct Supabase connectivity from the installed client
- Non-Summoner's-Rift / non-draft modes (ARAM, Arena, TFT, Blind Pick queue, Co-op vs AI, Practice, Custom)
- Tauri-IPC as the Vue↔Python data channel (rejected by spec §3)

## Architectural Build Order / Critical Path

Three net-new layers over a frozen three-tier app:
1. **Tauri Rust host** (launcher + window + updater + sidecar manager)
2. **Python sidecar lifecycle delta** (argparse, ready-file, CLI port)
3. **CDN-JSON data plane** (`json_repo.py` + `export_to_json.py` + `gh-pages`)

**Public API contracts preserved exactly** — `json_repo.py` mirrors 9 public functions from `supabase_repo.py` (`get_champion_stats`, `get_champion_stats_by_role`, `get_matchups`, `get_synergies`, `get_items`, `get_runes`, `get_summoner_spells`, plus `_wilson_score` helper) with identical signatures and return shapes.

**Critical path:** Foundation (Python CLI args + `backend.spec`) → Tauri shell + lifecycle → Data-plane cutover → Release pipeline.

**Parallel track:** CDN data plane (`json_repo.py` + `export_to_json.py` + `gh-pages`) has zero dependency on the Tauri track and can be developed from day one.

**Integration points in existing codebase (verified against source):**
- `apps/backend/backend.py` — lines 11–19 (import block swap), bottom (CLI args + ready-file + `socketio.run` host/port)
- `apps/backend/src/lolalytics_api/supabase_repo.py` — 9 public functions (contract source)
- `apps/frontend/src/stores/draft.ts` line 233 (hardcoded `localhost:5000`)
- `apps/frontend/src/api/backend.ts` line 11 (`API_BASE_URL`)
- `apps/frontend/vite.config.ts` (dev proxy, stays for non-Tauri dev fallback)

### Suggested Six-Phase Structure

1. **Foundation — Python sidecar + PyInstaller bundle.** `backend.py` argparse + ready-file + in-process health probe; `backend.spec` (`upx=False`, hidden imports, excludes); `certifi` bundling; `_MEIPASS` / `user_data_dir()` resource helper. **Gate:** CI smoke test — built `.exe` passes Socket.IO round-trip + HTTPS CDN fetch; VirusTotal ≤ 3 detections.
2. **CDN data plane (parallel with 1 and 3).** `json_repo.py` mirroring all 9 public functions (cache-hit / 304 / cold-fetch / atomic rename / corrupt-cache recovery); `export_to_json.py` with `__meta` envelope + integrity validation; `gh-pages` orphan branch live; ETL workflow appended. **Gate:** `curl` on CDN returns expected JSON shape.
3. **Tauri shell + sidecar lifecycle.** `src-tauri/` crate; `tauri.conf.json`; port allocation + spawn + Job Object + `CTRL_BREAK_EVENT` → 2 s → `TerminateProcess` shutdown ladder; `get_backend_port` / `restart_backend` commands; single-instance plugin. **Gate:** 50× cold-start on `windows-latest` with zero flakes; Task Manager-kill-Tauri → `backend.exe` count → 0 within 1 s. **This is the "unlocks demo" milestone.**
4. **Data-plane cutover + frontend URL discovery.** One import-block swap (`supabase_repo` → `json_repo`); remove `supabase` from `requirements.txt`; new `api/client.ts` with `getBackendURL()`; edit `stores/draft.ts:233` + `api/backend.ts:11`; wire `backend-disconnected` banner. **Gate:** `pnpm tauri build` → install `.msi` → end-to-end draft flow on real CDN.
5. **Targeted fix + polish (parallel-capable with 4).** Diagnostic-log pass in `league_client_websocket.py` → root-cause → patch hover weight; add `GET /api/draft/active` endpoint (feeds Phase 6 deferral); staleness-banner thresholds; LoL-waiting view distinct from error banner; version in title bar.
6. **Release pipeline + updater ceremony + distribution docs.** `tauri signer generate` + three-copy key storage + rehearsed rotation; `.github/workflows/release.yml` on `windows-latest`, tag-triggered; SHA256 compute + `gh release create`; `latest.json` published to `gh-pages` (NOT as release asset, so rollback is a `git revert`); updater deferral gated on `/api/draft/active`; README with SmartScreen screenshots, AV guidance, literal log-folder path containing the real bundle_id, MSI-vs-portable FAQ. **Gate:** public v1.0.0.

## Top 5 Pitfalls by Blast Radius

1. **Orphaned `backend.exe` on Tauri crash → zombies + cache/log lock contention.** PyInstaller onefile spawns a bootloader parent + Python child; `child.kill()` targets only the bootloader. Mitigation: `CreateJobObject` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` via `win32job`; `AssignProcessToJobObject` before child runs; shutdown ladder `CTRL_BREAK_EVENT` → 2 s → `TerminateProcess`. → **Phase 3.**
2. **UPX-compressed sidecar → mass AV quarantine on first install.** Default `upx=True` matches malware signatures; non-technical users cannot recover. Mitigation: `upx=False` (CI-grep enforceable), rebuild PyInstaller bootloader from source per release, VirusTotal ≤ 3 gate in CI, SHA256 + Microsoft false-positive submission within 24 h of each tagged release. → **Phase 1 (build) + Phase 6 (submission procedure).**
3. **Ready-file ↔ webview-show race → cold-start 404 storm on first launch.** Python can write the ready-file before the threaded server has entered `accept()`. Mitigation: write ready-file only after an in-process HTTP health probe succeeds; Tauri side retries 3× at 50 ms; frontend uses exponential-backoff silent retry during cold-start. → **Phase 3.**
4. **Lost Tauri updater private key = permanently abandoned user base.** Ed25519 pubkey is baked into installed app; rotation requires signing with the OLD key, so rotating from "no key" is impossible. Mitigation: three-copy storage (password manager + GitHub Actions secret + offline encrypted USB or printed QR); documented recovery in `docs/RELEASE.md`; rehearsed rotation in staging before first release; never prefix `TAURI_PRIVATE_KEY` with `VITE_` (GHSA-2rcp-jvr4-r259). → **Phase 6 — process gate.**
5. **Mid-draft force-update destroys champion-select state.** Updater schedule is independent of LCU draft state. Single worst UX failure mode. Mitigation: gate `installAndRelaunch()` on `GET /api/draft/active`; defer updater prompts during champion select; default to "install on next app start"; persist draft state to `%APPDATA%\{bundle_id}\draft_session.json` per pick. → **Phase 5 (`/api/draft/active` + persistence) + Phase 6 (gating).**

**Honorable mentions:**
- Missing PyInstaller hidden imports (`engineio.async_drivers.threading`, `httpx.socks`) → Socket.IO silently dies on first client connect (Phase 1)
- SSL cert missing in bundled sidecar (`certifi` data files not collected) → "Cannot load champion data" (Phase 1)
- `json_repo` ↔ `supabase_repo` signature drift → silent 500s on `/api/recommendations` (Phase 2)
- Cache corruption non-recoverable (truncated JSON on power loss) → permanent offline failure (Phase 2)

## Conflicts & Open Questions (resolve before plan-freeze)

None blocks roadmap creation. All need explicit decisions before the relevant phase:

1. **Final Tauri `identifier`** (`dev.till.lol-draft-analyzer` suggested) — must be fixed before Phase 3 ships.
2. **CDN concrete URL** (`https://{GITHUB_USER}.github.io/{REPO_NAME}/data/`) — baked into `tauri.conf.json` when Phase 2 lands.
3. **"Portable `.exe`" definition.** Tauri v2 has no first-class single-file portable target; NSIS `-setup.exe` is a setup wizard. Pick one: (a) ship NSIS `-setup.exe` as "portable" + FAQ, (b) ship a ZIP of `target/release/` as alternative asset, or (c) drop portable for v1. Recommendation: (a).
4. **Python version for CI:** 3.11 / 3.12 / 3.13 all compatible. Recommendation: 3.12.
5. **Seed dataset for offline-first-run.** Bundling ~1–5 MB of static JSON gives robust offline UX but is NOT in spec §6. Decide: add to Phase 1 OR defer to v1.1.
6. **Cache-busting strategy for CDN.** Spec is silent. Options: content-addressed filenames + `manifest.json`, `?v=<exported_at>` query string, or conditional-GET-only. Default recommendation: manifest-based versioning.
7. **Mid-draft deferral depth.** Spec §5 commits to a prompt but not to LCU-draft-active gating. Confirm `/api/draft/active` + deferral in scope vs. deferring custom updater UI to v1.1.

## Research Flags for Phase Planning

**Needs research (`/gsd-research-phase` recommended):**
- **Phase 2:** GitHub Pages + Fastly edge-cache 304/200 behavior; `exported_at` propagation latency; `gh-pages` force-push interaction with `actions/deploy-pages@v4` vs `peaceiris/actions-gh-pages@v4`. Canary GET before committing to a cache-busting strategy.
- **Phase 3:** Socket-inheritance (pre-bound `TcpListener` handed to child) as alternative to allocate-drop-spawn — prototype; flag for v1.1 upgrade path. Verify exact `@tauri-apps/plugin-updater` npm minor at plan-freeze.
- **Phase 6:** Tauri updater behavior with `latest.json` hosted on `gh-pages` + short `Cache-Control: max-age=60` vs Fastly default. One-build test of NSIS-portable semantics.

**Standard patterns (skip phase research):**
- **Phase 1:** PyInstaller + Flask-SocketIO hidden imports, `certifi` bundling, `_MEIPASS` vs `user_data_dir()`.
- **Phase 4:** Mechanical swap — one import block + frontend base-URL discovery.
- **Phase 5:** Hover-fix is diagnostic-log + patch on existing code.

## Confidence Assessment

| Dimension | Confidence | Rationale |
|-----------|------------|-----------|
| Stack | HIGH | Tauri v2 docs + crates.io + PyPI verified 2026-04-14; cross-checked compatibility matrix. |
| Features | HIGH | Every P1 item traces to spec §8 acceptance gates; every anti-feature to spec §10 / PROJECT.md. |
| Architecture | HIGH | Build order verified against actual code (file paths + line numbers). 9-function contract verified against `supabase_repo.py`. |
| Pitfalls | HIGH | PyInstaller + Tauri lifecycle + updater-key issues grounded in issue trackers (Flask-SocketIO #259/#633, Tauri #11686/#5611, GHSA-2rcp-jvr4-r259). GitHub Pages / Fastly edge-cache: MEDIUM (community sources). SmartScreen reputation: MEDIUM. |

---
*Synthesized from STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md on 2026-04-14.*
