# LoL Draft Analyzer

## What This Is

A desktop tool that reads the live champion-select state from the League of Legends client and produces per-role pick recommendations scored against current meta data. The product currently exists as a manually-started Flask + Vue web app with a Supabase backend; this milestone packages it into a one-click Windows installer so non-technical LoL players can download, run, and auto-update it like any normal desktop app.

## Core Value

Zero-friction delivery: a non-technical LoL player downloads one installer and has working draft recommendations — no Python, no Node, no credentials, no command line.

## Requirements

### Validated

<!-- Existing capabilities in the codebase, inherited from prior work. -->

- ✓ Vue 3 frontend with draft-tracker and champion-lookup views — existing
- ✓ Flask + Flask-SocketIO backend with REST endpoints and Socket.IO real-time channel — existing
- ✓ League Client bridge: LCU HTTP auth + WebSocket event relay — existing
- ✓ Recommendation engine with Wilson-Score-based matchup/synergy scoring across all 5 roles — existing
- ✓ Supabase as source-of-truth for champion stats, matchups, synergies, items, runes, summoner spells — existing
- ✓ Nightly Lolalytics ETL into Supabase via GitHub Actions — existing
- ✓ Shared TypeScript type package (`@counterpick/core`) for request/response contracts — existing
- ✓ Blind-pick recommendation mode (recommendations with no enemy picks yet visible) — existing

### Active

<!-- v1 desktop delivery scope per the delivery-form design spec. -->

- [ ] Ship a Windows `.msi` installer and portable `.exe` as GitHub Release artifacts
- [ ] Bundle the Python Flask backend as a PyInstaller sidecar inside a Tauri desktop app
- [ ] Tauri host spawns the sidecar on a dynamically-allocated localhost port and manages its lifecycle (start, graceful shutdown, crash recovery, Job Object kill-on-close)
- [ ] Vue frontend discovers the backend port via Tauri IPC instead of hardcoded `localhost:5000`
- [ ] Replace client-side Supabase access with a CDN JSON read path (`json_repo.py`) plus local cache with conditional GET
- [ ] Add a GitHub Actions export step that dumps the relevant Supabase tables to JSON and publishes them to GitHub Pages after each ETL run
- [ ] Remove the `supabase` Python dependency and all Supabase credentials from the runtime bundle
- [ ] AV false-positive mitigation: PyInstaller without UPX, SHA256 hashes published in release notes, README troubleshooting section, Microsoft false-positive submissions
- [ ] Tauri auto-updater wired to GitHub Releases with signed `latest.json`
- [ ] Fix hover-detection bug in `league_client_websocket.py` so hovered picks are factored in with reduced weight rather than ignored
- [ ] First-run UX: cold-start downloads CDN data with visible progress; graceful error if offline
- [ ] Error states: backend-disconnected banner with Restart button, LoL-client-waiting view, cached-data staleness indicator
- [ ] Structured backend logging to `%APPDATA%\{bundle_id}\logs\` with daily rotation for user-reported bug diagnosis
- [ ] README documents: installer download, SmartScreen workaround, AV guidance, log-folder location
- [ ] Dev workflow: `pnpm tauri dev` spawns native Python backend with hot-reload Vite frontend preserved
- [ ] CI/CD: `.github/workflows/release.yml` on `windows-latest`, triggered by `v*` tags, builds sidecar + Tauri bundle and publishes the Release

### Out of Scope

<!-- Explicit boundaries from the delivery-form spec §10 and §8. -->

- macOS and Linux builds — LoL on macOS has ~5% share, Linux is unsupported by Riot; backlog only
- Code signing with an EV certificate (~$200–400/year) — not justified for a non-commercial v1; reconsider only if AV friction dominates user feedback
- Nuitka migration as PyInstaller replacement — only if AV false-positive reports become frequent
- FastAPI migration — Flask is adequate; revisit only if it becomes a real bottleneck
- User settings / preferences (language, theme, role override) — none shipped in v1
- Telemetry, crash reporting — v1 is privacy-preserving; if ever added, must be opt-in
- Non-Summoner's-Rift and non-draft modes (ARAM, Arena, Nexus Blitz, TFT, LoL Blind Pick queue, Co-op vs AI, Practice Tool, Custom) — no matchup data applies and Blind Pick queue exposes no champion-select state
- Supabase DB performance review (pooling, indexing, query audit) — deferred follow-on spec; urgency reduced because clients no longer hit Supabase
- Overlay UX polish (graphics performance, expanded hover UX beyond the targeted fix) — separate spec
- GitHub publishing readiness (license selection, legal review of Lolalytics scraping, README polish beyond install/troubleshooting) — separate spec
- Direct Supabase connectivity from the installed client — replaced by CDN JSON read path; Supabase remains the ETL target only

## Context

**Existing codebase (brownfield):**
- Monorepo under `counterpick-app/` (pnpm) with `apps/frontend` (Vue 3 + Vite), `apps/backend` (Flask + Flask-SocketIO), `packages/core` (shared TS types).
- Separate `supabase-dataset-updater/` Node.js ETL project with its own GitHub Actions schedule.
- Existing codebase map lives at `.planning/codebase/` (ARCHITECTURE.md, STACK.md, STRUCTURE.md, CONVENTIONS.md, INTEGRATIONS.md, CONCERNS.md, TESTING.md) and should be treated as authoritative for current state.

**Target users:**
- Non-technical LoL players on Windows. They expect a download link and an installer. Asking them to run `pip install` or `pnpm dev` will lose the audience.

**Known issues inherited into this milestone:**
- Hover detection exists but does not actually apply reduced weight — carried into this spec as a targeted fix because the root cause sits in `league_client_websocket.py`, which the lifecycle rework must touch anyway.
- Hardcoded `localhost:5000` in the frontend must be replaced to allow dynamic port allocation.
- Supabase credentials currently reach the client via `apps/backend/.env`; removed from the bundle in v1.

**Ruled out in prior brainstorming (informs this spec's boundaries):**
- Backend stack replacement (Flask → FastAPI) — not pursued.
- Tauri-IPC-first communication between Vue and Python — rejected in favor of preserving the existing HTTP + Socket.IO path over a dynamic localhost port; Tauri is launcher + updater + window host only.

## Constraints

- **Platform:** Windows 10 and Windows 11 only for v1 — macOS/Linux deferred.
- **Tech stack (locked):** Flask + Flask-SocketIO backend, Vue 3 + Vite frontend, Tauri (Rust) desktop host, PyInstaller for sidecar packaging, Supabase remains source of truth for the ETL, GitHub Pages as CDN.
- **No code signing in v1:** AV false-positive mitigation is procedural (UPX disabled, hashes published, README guidance, Microsoft submissions) — an EV certificate is out of scope.
- **Non-commercial release:** No budget for paid signing, telemetry, or crash-reporting SaaS.
- **Installer size:** ≤ 100 MB as a success criterion.
- **Installation model:** Installer must complete on a clean Windows machine without admin rights.
- **Privacy:** No telemetry, no network calls beyond CDN reads and Riot's own LCU; log files stay local.
- **Data path:** Installed clients never talk to Supabase; all read data flows through the public GitHub Pages CDN.
- **Minimum-invasive change:** The Flask/Socket.IO code path stays structurally unchanged — the sidecar is the same backend, reached over localhost.

## Key Decisions

<!-- Decisions baked into the delivery-form spec and inherited here. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Tauri desktop app with PyInstaller sidecar | Keeps Flask/Socket.IO code path untouched; Tauri handles launcher + window + updater; no Python-to-Rust rewrite needed | — Pending |
| HTTP + Socket.IO over dynamic localhost port (not Tauri IPC bridge) | Preserves the existing client-server architecture; Tauri is purely the shell | — Pending |
| CDN (GitHub Pages) as client-side data source, Supabase as ETL-only source-of-truth | Eliminates client-side credentials, removes Supabase attack surface from installed binaries, leverages existing daily ETL | — Pending |
| Windows-only for v1, no code signing | Focused scope; LoL user base is predominantly Windows; EV cert cost not justified pre-distribution | — Pending |
| Tauri updater via GitHub Releases with signed `latest.json` | Standard Tauri pattern; no separate update infrastructure needed | — Pending |
| PyInstaller without UPX + SHA256 hashes + README guidance for AV mitigation | Cheapest procedural mitigation; Nuitka / EV-cert fallback parked in backlog | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-14 after initialization*
