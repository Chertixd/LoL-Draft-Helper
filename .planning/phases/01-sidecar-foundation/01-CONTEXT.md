# Phase 1: Sidecar Foundation — Context

**Gathered:** 2026-04-14
**Status:** Ready for planning
**Mode:** `--auto` (recommended defaults applied; each choice logged inline below)

<domain>
## Phase Boundary

Phase 1 delivers a standalone Windows `backend.exe` built by PyInstaller from the existing Flask + Flask-SocketIO backend. When invoked with `--port <int> --ready-file <path>`, it must: bind loopback, announce readiness only after an in-process HTTP health probe returns 200, fetch HTTPS CDN data successfully, resolve bundled assets via `_MEIPASS` and user-writable paths via `platformdirs`, and pass a VirusTotal sanity threshold of ≤ 3 detections.

**In scope:** `backend.py` CLI delta + ready-file protocol, `backend.spec`, `resources.py` helper module, CI smoke test, hidden-import seed list, exclude list.

**Out of scope for this phase:**
- Tauri host, sidecar spawn, Job Object, dynamic-port allocation from the Rust side (→ Phase 3)
- `json_repo.py`, CDN export script, `gh-pages` branch (→ Phase 2)
- `.msi`/portable bundling, release workflow, updater signing, README (→ Phase 4)

</domain>

<decisions>
## Implementation Decisions

### CLI & Health Probe

- **D-01:** `backend.py` uses stdlib `argparse` for `--port <int>` (default 5000 for native dev) and `--ready-file <path>` (default None). Also expose `--cache-dir <path>` (default `platformdirs.user_cache_dir("lol-draft-analyzer")`) and `--log-dir <path>` (default `platformdirs.user_log_dir("lol-draft-analyzer")`) so Phase 3 / tests can override without env vars. _[auto: stdlib argparse is zero-dep and matches existing codebase conventions]_
- **D-02:** Ready-file protocol: Tauri (or test harness) provides a writable path. Python MUST NOT create the ready-file until an in-process HTTP `GET http://127.0.0.1:<port>/api/health` returns 200. This verifies the Flask threaded server has actually entered `accept()`, not merely that `socketio.init_app()` completed. _[auto: mitigates Pitfall #3 "ready-file/webview-show race"]_
- **D-03:** Health-probe implementation: a new `/api/health` route returning `{"status": "ok", "version": "<app-version>"}`. A background probe thread (started before `socketio.run`) polls `127.0.0.1:<port>/api/health` on a 50 ms interval with a 5 s overall timeout; on first 200 it writes the ready-file atomically (`open(path + ".tmp", "w") ... os.replace(...)`). On timeout the process exits non-zero. _[auto: atomic rename prevents partial-write visible to poller]_
- **D-04:** Ready-file content is the JSON `{"port": <n>, "pid": <pid>, "ready_at": "<iso8601>"}`. This gives the Tauri host everything it needs to verify it's talking to the correct sidecar (defensive; not load-bearing in v1). _[auto: cheap future-proofing]_
- **D-05:** On startup, if the ready-file path already exists, delete it first — prevents a stale flag from fooling the host. _[auto: idempotent cleanup]_

### PyInstaller Spec (`apps/backend/backend.spec`)

- **D-06:** `--onefile` output; output name `backend-x86_64-pc-windows-msvc.exe` to match Tauri sidecar naming conventions. _[auto: aligns with Tauri v2 sidecar expectations]_
- **D-07:** `upx=False` at spec level AND enforced by a CI grep check in the release workflow. Any PR that flips `upx=True` fails CI. _[auto: UPX triples AV false-positive rate — Pitfall #2, non-negotiable]_
- **D-08:** Initial `hiddenimports` seed: `['engineio.async_drivers.threading', 'httpx.socks', 'websocket', 'charset_normalizer', 'urllib3', 'certifi']`. Expand iteratively via first CI failure — spec comments document the discovery process. _[auto: spec §4.1 + python-socketio #633 + Flask-SocketIO #259]_
- **D-09:** `excludes=['supabase', 'gotrue', 'postgrest', 'realtime', 'storage3', 'supabase_functions', 'supabase_auth']` — eliminates Supabase from the bundle surface area entirely. _[auto: no supabase on runtime path — spec §6.5]_
- **D-10:** `certifi` data files bundled via `datas=[(certifi.where(), 'certifi')]` and `SSL_CERT_FILE` env var set on startup to the resolved bundled path via the `resources.py` helper. _[auto: pinned by spec §4.1 + PyInstaller #7229]_
- **D-11:** No binary-file embedding of `cache_data.json` or other runtime-mutable files — those live in `user_cache_dir`, not in the bundle. `dragontail-15.24.1/` and any other static assets that the backend serves remain bundled via `datas=[...]`. _[auto: mutable vs immutable asset split is mandatory for PyInstaller onefile]_
- **D-12:** Build command: `pyinstaller --clean --noconfirm apps/backend/backend.spec`. `--clean` prevents stale artifacts from bleeding across CI runs. _[auto: PyInstaller best-practice]_

### Resource Resolution Helper (`apps/backend/src/resources.py`)

- **D-13:** New module `apps/backend/src/resources.py` exporting four helpers:
  - `bundled_resource(relative_path: str) -> pathlib.Path` — resolves via `sys._MEIPASS` when frozen, via `__file__`-anchored fallback in dev mode.
  - `user_cache_dir() -> pathlib.Path` — uses `platformdirs.user_cache_dir("lol-draft-analyzer")`, creates the directory if missing.
  - `user_log_dir() -> pathlib.Path` — uses `platformdirs.user_log_dir("lol-draft-analyzer")`, creates the directory if missing.
  - `user_data_dir() -> pathlib.Path` — uses `platformdirs.user_data_dir("lol-draft-analyzer")`, for any non-cache persistent state.
  _[auto: single source of truth; `platformdirs` ≥ 4.0 added to requirements]_
- **D-14:** Migration rule: **no** `__file__`-relative path resolution or `os.getcwd()` remains in the runtime code path after this phase. Grep-enforced in the phase verification step. _[auto: frozen `_MEIPASS` path is ephemeral; any `__file__` path is a runtime bug waiting to happen]_
- **D-15:** App-name constant `LOL_DRAFT_APP_NAME = "lol-draft-analyzer"` lives in `resources.py`. Phase 3 will change this to the finalized Tauri `identifier` (e.g. `dev.till.lol-draft-analyzer`) when the bundle_id is locked — Phase 1 ships with the placeholder value documented as mutable. _[auto: bundle_id finalization is explicitly deferred to Phase 3 per SUMMARY.md open questions]_

### Dependencies & Python Version

- **D-16:** CI Python version: **3.12** (pinned via `actions/setup-python@v5` with `python-version: "3.12.x"`). PyInstaller 6.19 + Flask-SocketIO + python-socketio all support 3.12; 3.13 is usable but not picked as default to minimize transitive-dep surprise. _[auto: SUMMARY.md recommendation]_
- **D-17:** PyInstaller is installed in CI via `pip install pyinstaller==6.19.0` — version pinned to prevent drift between local and CI builds. _[auto: pinning is cheap; surprises from minor bumps are expensive]_
- **D-18:** Add `platformdirs>=4.0.0` to `apps/backend/requirements.txt`. _[auto: needed for `user_cache_dir`/`user_log_dir` helpers]_
- **D-19:** **Do not** remove `supabase-py` from `requirements.txt` in Phase 1 — that deletion happens in Phase 2 when `json_repo.py` lands. Phase 1 only marks it in the PyInstaller `excludes`, which keeps dev-mode Supabase access working for the existing ETL/dev tooling while keeping the bundled `.exe` clean. _[auto: respects Phase 2 boundary; avoids breaking dev environment prematurely]_

### CI Smoke Test (`test_backend_cli.py` + release-workflow job)

- **D-20:** New pytest integration test `test_backend_cli.py`: spawns `python backend.py --port 0 --ready-file <tmp>` via `subprocess.Popen`, waits up to 10 s for ready-file, asserts it exists and contains valid JSON with a matching pid, then sends SIGTERM and asserts clean exit within 2 s. This exercises the ready-file contract in BOTH dev-mode and frozen-exe mode. _[auto: contract test doubles as regression guard for the entire CLI surface]_
- **D-21:** Release-workflow smoke test launches the BUILT `backend.exe` (not `python backend.py`), verifies Socket.IO round-trip via a Python test client, and performs one HTTPS `GET https://example.com/` to confirm `certifi` bundling works. _[auto: catches PyInstaller-specific regressions the unit test can't]_
- **D-22:** VirusTotal scan: optional CI step gated on `VT_API_KEY` secret. If the key is absent the step is skipped with a warning; if present the step fails the build when detections > 3. **Not blocking for Phase 1 acceptance** — this gate is a release-readiness check that only bites on tagged releases in Phase 4. Phase 1's CI simply ensures the integration is wired and the threshold logic is correct. _[auto: don't block day-one development on VT API availability]_
- **D-23:** Smoke test runs on `windows-latest` GitHub runner — this is the only OS we target. Local development on any platform still works because the non-PyInstaller path (`python backend.py`) is unchanged. _[auto: Windows-only v1 per PROJECT.md Out-of-Scope]_

### Scope Boundaries / Anti-Decisions (explicitly NOT done in this phase)

- **N-01:** No Tauri-side code, no Rust. Phase 1 is purely Python + PyInstaller + CI YAML.
- **N-02:** No `--cache-dir` being wired up to `json_repo.py` yet — that's Phase 2. Phase 1 adds the CLI flag and the `resources.user_cache_dir()` helper but nothing reads from the cache directory yet.
- **N-03:** No removal of `supabase_repo.py` imports from `backend.py`. Phase 1 ships with the existing Supabase code path intact; the PyInstaller `excludes` means the BUNDLED `.exe` can't import supabase, but in dev-mode (`python backend.py`) it still can. When Phase 2 lands `json_repo.py` and flips the import, the excluded-Supabase state is already correct.
- **N-04:** No seed-dataset bundling (the SUMMARY.md open question "seed dataset for offline-first-run") — **deferred to v1.1**. Phase 1 has no offline-first-run UX; that's the job of Phase 2's cache + Phase 3's UX. _[auto: keeps Phase 1 tight]_

### Claude's Discretion

- Exact probe interval inside `/api/health` polling loop (50 ms is the documented default; bump to 25 ms if CI flakes).
- Retry structure inside the CI smoke test (number of retries around the subprocess spawn, etc.).
- Whether to collapse `user_cache_dir` / `user_log_dir` / `user_data_dir` into a single helper with a `kind=` argument vs. three separate functions — downstream planner picks.
- Exact `log` level/handlers setup in `backend.py` initialization (spec says structured + daily-rotating, but the concrete `logging.handlers.TimedRotatingFileHandler` configuration is planner's call).

### Folded Todos

None — this is the first phase, no pre-existing todos.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Primary spec (source of truth)
- `docs/superpowers/specs/2026-04-14-delivery-form-design.md` §4.1 (Stage 1 — Python Sidecar), §5 (IPC, Ports & Lifecycle — particularly §5.1–5.4 Python-side changes), §5.5 (AV mitigation), §7 (Error handling table rows relevant to sidecar startup)

### Project-level
- `.planning/PROJECT.md` — Core Value, locked Key Decisions, Constraints (Windows-only, no code signing, installer ≤ 100 MB)
- `.planning/REQUIREMENTS.md` — Requirements SIDE-01 through SIDE-05 assigned to this phase

### Research outputs
- `.planning/research/STACK.md` — PyInstaller 6.19.0 version pin, hidden-import gotchas, `createUpdaterArtifacts` (informational, Phase 4), `certifi` bundling pattern
- `.planning/research/ARCHITECTURE.md` — Integration points in existing code: `backend.py` lines 11–19, bottom-of-file `socketio.run`; critical-path ordering
- `.planning/research/PITFALLS.md` — Pitfall #2 (UPX), #3 (ready-file race), plus honorable mentions for hidden imports and `certifi` — all mapped to Phase 1
- `.planning/research/SUMMARY.md` — Phase 1 "Foundation" summary and gate criteria

### Existing codebase maps (authoritative for current state)
- `.planning/codebase/STACK.md` — Current Python 3.10+ baseline, Flask/Flask-SocketIO versions
- `.planning/codebase/ARCHITECTURE.md` — Layering; where Flask routes/socket handlers live
- `.planning/codebase/STRUCTURE.md` — File tree for `apps/backend/`
- `.planning/codebase/CONVENTIONS.md` — Existing coding/testing conventions (to not accidentally break)
- `.planning/codebase/TESTING.md` — Existing pytest setup to integrate with

### External references (upstream issue trackers — cited by pitfalls)
- PyInstaller docs: <https://pyinstaller.org/en/stable/runtime-information.html> (`_MEIPASS` semantics)
- Flask-SocketIO #259: <https://github.com/miguelgrinberg/Flask-SocketIO/issues/259> (packaging)
- python-socketio #633: <https://github.com/miguelgrinberg/python-socketio/issues/633> (async_mode hidden import)
- PyInstaller #7229: <https://github.com/pyinstaller/pyinstaller/issues/7229> (certifi bundling)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `counterpick-app/apps/backend/backend.py` — entrypoint; currently hardcodes port via `socketio.run(app, host='0.0.0.0', port=5000)` at the bottom. CLI-arg delta lands here.
- `counterpick-app/apps/backend/src/lolalytics_api/` — existing module layout. `resources.py` goes here (or at `apps/backend/src/resources.py`, parallel to the package; planner picks).
- `counterpick-app/apps/backend/requirements.txt` — current deps. Add `platformdirs>=4.0.0`; DO NOT remove `supabase` here (that's Phase 2).
- `counterpick-app/apps/backend/pyproject.toml` — pytest config; reuse for the new `test_backend_cli.py` integration test.

### Established Patterns
- Flask blueprint pattern is NOT currently used — routes are registered directly on `app`. The new `/api/health` route follows the same inline-decorator style.
- Existing ETL tests (if any) use stdlib `unittest`/`pytest` — new tests stay in pytest.
- `.env` loading via `python-dotenv` is already imported at backend startup — keep as-is for dev mode; PyInstaller build does not need `.env` values baked in because the CDN URL lives in Tauri config (Phase 2) and Supabase creds don't enter the bundle.

### Integration Points
- `backend.py` top-of-file imports (line ~11–19) — add `import argparse`, `import os`, `import threading`, `from pathlib import Path`, `from src.resources import user_cache_dir, user_log_dir, bundled_resource`. The `supabase_repo` import stays untouched (Phase 2 swaps it).
- `backend.py` bottom-of-file `socketio.run(...)` — wrap in the new `main()` function that parses args, sets up logging, spawns the probe thread, writes ready-file on success, and calls `socketio.run(host='127.0.0.1', port=args.port)`.
- `apps/backend/backend.spec` — new file at the backend root; no changes to existing .py modules beyond `backend.py` itself (and the new `resources.py`).
- GitHub Actions: new workflow or extension of existing — smoke test runs on `windows-latest`. Release workflow proper is Phase 4, but the build-smoke-on-main subset (BUILD-05) of the full pipeline is introduced here so PyInstaller regressions are caught immediately.

</code_context>

<specifics>
## Specific Ideas

- Match existing `socketio.run` argument style and threading model — don't switch to eventlet/gevent to "fix" something; the spec locks `async_mode='threading'`.
- Keep `backend.py` readable end-to-end: the `main()` function should be short (~30 LoC), delegating setup to helpers in `resources.py`. Downstream planner should not produce a `main.py` wrapper that obscures the entrypoint.
- Logging directory layout (Phase 3 formalizes this further): for now, `resources.user_log_dir() / "backend-<YYYY-MM-DD>.log"` via `TimedRotatingFileHandler`. LCU auth redaction (LOG-05) is a Phase 3 concern — Phase 1 only needs the rotating handler wired.
- The CI smoke test should exercise the **frozen** `backend.exe` (not just `python backend.py`) — running only the unit test would miss PyInstaller-specific regressions (hidden-import misses, `_MEIPASS` path bugs).

</specifics>

<deferred>
## Deferred Ideas

- **Seed dataset for offline-first-run** — bundling a 1–5 MB snapshot of champion/matchup data so the app works offline on first launch with no CDN reachable. Deferred to **v1.1**. Rationale: adds complexity to Phase 1 that Phase 2's cache + Phase 3's UX ultimately address for the online-first-time user; true offline-first is a separable feature.
- **Nuitka migration as PyInstaller alternative** — already in PROJECT.md Out of Scope; only reconsidered if AV friction becomes dominant after launch.
- **Rebuilding the PyInstaller bootloader from source** — stronger AV mitigation than `upx=False` alone. Deferred to **Phase 6 / post-launch**; only worth the CI complexity if VirusTotal detections become problematic on real release builds. In Phase 1 we ship with the stock bootloader and rely on `upx=False` + hash publication.
- **VirusTotal API hard-gate in CI** (fail build on > 3 detections instead of warning) — Phase 4 decision; Phase 1 wires the integration but keeps the threshold advisory only.
- **Moving log-handler / LCU-auth redaction logic into Phase 1** — deferred to **Phase 3** per the roadmap (LOG-01..05 are Phase 3 requirements). Phase 1 lands only the bare `TimedRotatingFileHandler` because the sidecar needs SOMETHING to log to during CI smoke tests; full policy is Phase 3.
- **Finalizing `{bundle_id}` to a concrete identifier** — Phase 3 concern (TAURI-01). Phase 1 uses `LOL_DRAFT_APP_NAME = "lol-draft-analyzer"` as a mutable placeholder in `resources.py`.

### Reviewed Todos (not folded)
None.

</deferred>

---

*Phase: 01-sidecar-foundation*
*Context gathered: 2026-04-14 (auto mode)*
