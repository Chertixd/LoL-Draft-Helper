---
phase: 01-sidecar-foundation
verified: 2026-04-14T00:00:00Z
status: human_needed
score: 4/4 must-haves verified (code+config); 1 needs CI execution
re_verification: false
human_verification:
  - test: "Run the build-smoke GitHub Actions workflow on windows-latest"
    expected: "All 11 steps pass end-to-end: pytest test_backend_cli.py green; pyinstaller --clean --noconfirm backend.spec produces dist/backend-x86_64-pc-windows-msvc.exe; strings | grep -i supabase finds nothing; built .exe writes ready-file within 10 s; smoke_test_exe.py exits 0 (Socket.IO round-trip + HTTPS GET succeed)."
    why_human: "The workflow has never been executed. All artefacts are wired correctly at the code+config level (verified here), but PyInstaller-specific regressions (missing hidden imports, dropped certifi data, engineio.async_drivers.threading failures) only surface when the actual build runs on windows-latest. Criterion 3 (VirusTotal) is intentionally advisory in Phase 1 per D-22; the integration is wired and threshold logic is correct but no real VT detection count has been observed yet."
  - test: "Observe VirusTotal detections ≤ 3 when VT_API_KEY is configured"
    expected: "scripts/virustotal_check.py uploads the built .exe and reports detections ≤ 3."
    why_human: "Phase 1 wires the VT gate as advisory-only (D-22); actual detection count is a Phase 4 release-gate concern. Cannot verify without a live VT API key + the built .exe."
---

# Phase 1: Sidecar Foundation Verification Report

**Phase Goal:** A built `backend.exe` can stand alone — it accepts a dynamic port, announces readiness only after proving the server accepts connections, fetches HTTPS CDN data successfully, and passes a VirusTotal sanity threshold.

**Verified:** 2026-04-14
**Status:** human_needed — all code/config wired correctly; CI execution and live VT scan are the final gates
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP §Phase 1 Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `python backend.py --port 0 --ready-file <tmp>` binds Flask-SocketIO on caller-chosen loopback port and ready-file appears only after in-process `GET /api/health` returns 200 | ✓ VERIFIED | backend.py:1913 argparse `--port`; :1918 `--ready-file`; :194 `/api/health` route returns 200 with `version`:`1.0.0-dev`; :1948–1961 probe thread spawned BEFORE socketio.run; :1859 probe polls `http://127.0.0.1:{port}/api/health`; :2002 binds `host="127.0.0.1"`; :1870 ready-file written AFTER first 200 via `_atomic_write_ready_file` (`os.replace`) |
| 2 | `pyinstaller apps/backend/backend.spec` produces single-file .exe with `upx=False`, `engineio.async_drivers.threading` + `httpx.socks` hidden imports, certifi bundled, supabase family excluded | ✓ VERIFIED (code) / human_needed (CI run) | backend.spec:102 `upx=False`; :37 `engineio.async_drivers.threading`; :39 `httpx.socks`; :28 `(certifi.where(), 'certifi')` in datas; :70–76 full supabase family in excludes; :98 `name='backend-x86_64-pc-windows-msvc'`. Actual build execution requires CI on windows-latest (never run yet per 01-03-SUMMARY "First-Run CI Result: Not yet observed"). |
| 3 | CI smoke test launches built .exe, round-trips Socket.IO, performs HTTPS CDN fetch, VirusTotal reports ≤ 3 detections | ⚠️ PARTIAL — wiring VERIFIED; CI run + VT scan human_needed | build-smoke.yml:14 runs-on `windows-latest`; :7–10 triggers push+PR to main; :42 `pip install -e .`; :64 `pyinstaller --clean --noconfirm backend.spec`; :88–102 spawns built .exe + waits for ready-file + runs `smoke_test_exe.py --port`; :99 `smoke_test_exe.py` does Socket.IO connect + `https://example.com/` GET; :115 calls real `scripts/virustotal_check.py --max-detections 3`; VT step marked `continue-on-error: true` per D-22 (advisory in Phase 1). |
| 4 | Read-only resources resolve via `bundled_resource()`/`sys._MEIPASS`; r/w paths via `user_data_dir()`/`platformdirs`; no `__file__` or `cwd()` in runtime code | ✓ VERIFIED | resources.py:46 `_is_frozen()` returns `getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")`; :64–70 `bundled_resource()` uses `sys._MEIPASS` when frozen; :83–85, 97–99, 110–112 `user_*_dir()` wrappers on `platformdirs` with `ensure_exists=True`; `grep __file__ backend.py` → 0 hits; `grep os\.getcwd backend.py` → 0 hits; backend.py:70 env_path via `bundled_resource('.env')`, :234 config_path via `bundled_resource('src/lolalytics_api/champion_roles.json')`, cache via `user_cache_dir()`. |

**Score:** 4/4 truths verified at the code+config level. Truth 2 and Truth 3 have a residual component (actual PyInstaller build + live VT scan) that can only be verified by running the CI workflow.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `counterpick-app/apps/backend/src/lolalytics_api/resources.py` | Path helpers + `LOL_DRAFT_APP_NAME` | ✓ VERIFIED | 113 lines; exports `LOL_DRAFT_APP_NAME` (:33), `_is_frozen` (:36), `bundled_resource` (:49), `user_cache_dir` (:74), `user_log_dir` (:88), `user_data_dir` (:102). Uses `platformdirs` + `ensure_exists=True`. Import verified: `python -c "from lolalytics_api.resources import ..."` returns expected Path object. |
| `counterpick-app/apps/backend/backend.spec` | PyInstaller onefile recipe | ✓ VERIFIED | 112 lines; `ast.parse` succeeds; `upx=False` at :102; `pathex=[]` at :23 (NOT `['src']`); certifi in datas at :28; hidden imports seed at :33–60 including `lolalytics_api.resources`; excludes list at :64–83; `name='backend-x86_64-pc-windows-msvc'` at :98; `console=False` at :105. `grep 'upx\s*=\s*True'` → 0 hits. No COLLECT block. |
| `counterpick-app/apps/backend/requirements.txt` | `platformdirs>=4.0.0` added; `supabase>=2.4.0` retained | ✓ VERIFIED | Line 10: `supabase>=2.4.0` (retained per D-19/N-03); Line 12: `platformdirs>=4.0.0` (appended). |
| `counterpick-app/apps/backend/backend.py` | `main()` with argparse + `/api/health` + probe thread + atomic ready-file + SSL wiring + loopback bind | ✓ VERIFIED | 2011 lines; `import ast; ast.parse()` OK. Line 41 canonical `from lolalytics_api.resources import ...`. Line 194 `/api/health` route returns `{'status':'ok','version':'1.0.0-dev', ...}`. Line 1784 `_configure_logging` with `TimedRotatingFileHandler(when='midnight', backupCount=14, encoding='utf-8')`. Line 1812 `_atomic_write_ready_file` uses `tmp + os.replace`. Line 1832 `_probe_health_then_signal_ready` polls `http://127.0.0.1:{port}/api/health` at 50 ms for 5 s budget; `os._exit(1)` on timeout. Line 1885 `main()` with four argparse flags; SSL_CERT_FILE + REQUESTS_CA_BUNDLE set via `bundled_resource('certifi/cacert.pem')`; stale ready-file cleaned before probe; daemon probe thread spawned BEFORE socketio.run. Line 2002 `host="127.0.0.1"`; :2004 `debug=False`; :2005 `allow_unsafe_werkzeug=True`. `grep host='0.0.0.0'` → 0 hits. `grep __file__` and `grep os\.getcwd` → 0 hits. |
| `counterpick-app/apps/backend/test_backend_cli.py` | pytest integration suite exercising CLI contract | ✓ VERIFIED | 166 lines; three test functions: `test_ready_file_contract` (:105, asserts `port`, `pid`, `ready_at`, and `version in body`), `test_stale_ready_file_is_cleaned` (:134, D-05 regression), `test_socketio_round_trip` (:148). Session-scoped autouse `_ensure_lolalytics_api_installed` fixture at :32 skips with actionable message when editable install is missing. Uses `subprocess.Popen` + `CREATE_NEW_PROCESS_GROUP` + `signal.CTRL_BREAK_EVENT` for Windows-safe lifecycle. |
| `counterpick-app/apps/backend/smoke_test_exe.py` | Frozen-.exe smoke companion | ✓ VERIFIED | 41 lines; `--port` argparse; `socketio.Client(...).connect(f"http://127.0.0.1:{args.port}")`; `requests.get("https://example.com/", timeout=10).raise_for_status()`. Exit 0 = pass. |
| `counterpick-app/apps/backend/scripts/virustotal_check.py` | Genuine VT v3 uploader with threshold gate | ✓ VERIFIED | 80 lines; `upload(path, api_key)` at :16 POSTs to `/api/v3/files`; `poll(analysis_id, api_key)` at :34 GETs `/api/v3/analyses/<id>` every 15 s; `main()` at :58 argparse + VT_API_KEY guard (exit 0 skip if unset per D-22). Exit codes: 0 pass / 0 skip / 1 over threshold / 2 API error. NOT a stub. |
| `counterpick-app/apps/backend/scripts/test_virustotal_check.py` | Mocked VT unit tests covering the threshold boundary | ✓ VERIFIED | 114 lines; 8 test functions including `test_main_passes_at_exact_threshold` (boundary `<=`, not `<`), `test_main_fails_when_detections_over_threshold`, `test_main_skips_when_api_key_unset`, `test_main_returns_2_on_api_error`, `test_detections_under_threshold` (must_haves alias). SUMMARY reports 8 tests pass in 0.22 s with mocked `requests`. |
| `.github/workflows/build-smoke.yml` | windows-latest smoke workflow triggering build + tests + VT | ✓ VERIFIED | 123 lines; `runs-on: windows-latest`; triggers on push to main + PR to main; Python 3.12.x (D-16); PyInstaller 6.19.0 pinned (D-17); `python-socketio[client]>=5.9.0,<6` (Pitfall #9); dedicated `pip install -e .` step (B-2 fix); fast-fail UPX guard; pytest runs before slow build; PyInstaller build; `command -v strings` precheck + `strings | grep -i supabase` guard (W-2); spawn built .exe + smoke test + kill; advisory VT scan with `continue-on-error: true`; upload-artifact@v4 with 7-day retention. |
| `counterpick-app/apps/backend/pyproject.toml` | `test` extra extended | ✓ VERIFIED | :30–34 `test = ["pytest>=7", "requests", "python-socketio[client]>=5.9.0,<6"]` — verified via `tomllib.loads()`. |
| `counterpick-app/apps/backend/.gitignore` | `dist/`, `build/` ignored | ✓ VERIFIED | Lines 3–4 `dist/` and `build/`; spec backups and bytecode caches also ignored. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| backend.spec datas | certifi.where() | `import certifi` + `(certifi.where(), 'certifi')` | ✓ WIRED | backend.spec:16 `import certifi`; :28 `(certifi.where(), 'certifi')`. |
| resources.py `bundled_resource()` | `sys._MEIPASS` | `getattr(sys, 'frozen', False) + hasattr(sys, '_MEIPASS')` guard | ✓ WIRED | resources.py:46 `_is_frozen()`; :65 `base = Path(sys._MEIPASS)`. |
| main() probe thread | /api/health route | `requests.get('http://127.0.0.1:{port}/api/health')` on 50 ms / 5 s | ✓ WIRED | backend.py:1859 URL; :1858 loop with 50 ms sleep; :1832 function signature with defaults `interval_s=0.05, timeout_s=5.0`. |
| main() SSL setup | `bundled_resource('certifi/cacert.pem')` | `os.environ.setdefault('SSL_CERT_FILE', str(cacert))` | ✓ WIRED | backend.py:1957 `cacert = bundled_resource("certifi/cacert.pem")`; :1958–1961 setdefault of `SSL_CERT_FILE` + `REQUESTS_CA_BUNDLE`. |
| main() probe thread | `_atomic_write_ready_file` | `tmp + os.replace` pattern | ✓ WIRED | backend.py:1870 call site; :1828–1829 `tmp.write_text(...)` + `os.replace(tmp, path)`. |
| build-smoke.yml PyInstaller step | backend.spec | `pyinstaller --clean --noconfirm backend.spec` | ✓ WIRED | build-smoke.yml:64. |
| build-smoke.yml smoke step | smoke_test_exe.py | `python smoke_test_exe.py --port <N>` after spawning built .exe | ✓ WIRED | build-smoke.yml:88–102 PowerShell block spawns .exe, waits for ready-file, then runs smoke script. |
| build-smoke.yml VT step | scripts/virustotal_check.py | `python scripts/virustotal_check.py <exe> --max-detections 3` | ✓ WIRED | build-smoke.yml:115 (file exists at that path — B-3 fixed). |
| test_backend_cli.py | backend.py main() | `subprocess.Popen([sys.executable, BACKEND_PY, '--port', ..., '--ready-file', ...])` | ✓ WIRED | test_backend_cli.py:58 Popen; :69 `CREATE_NEW_PROCESS_GROUP` on Windows. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SIDE-01 | 01-02 | `--port`/`--ready-file` CLI; binds 127.0.0.1:<port> | ✓ SATISFIED | backend.py argparse flags + loopback bind confirmed. |
| SIDE-02 | 01-02 | Ready-file written only after in-process health probe | ✓ SATISFIED | Probe thread + atomic write + D-05 stale cleanup all wired. |
| SIDE-03 | 01-01 | PyInstaller spec with upx=False, hidden imports, excludes, certifi | ✓ SATISFIED (code) / ? NEEDS HUMAN (CI run) | Spec file has all required elements; actual build never executed. |
| SIDE-04 | 01-03 | CI smoke test, Socket.IO round-trip, HTTPS, VT ≤ 3 | ⚠️ PARTIAL | Workflow + scripts wired; CI has never executed; VT threshold check is advisory in Phase 1 per D-22 (intentional). |
| SIDE-05 | 01-01 + 01-02 | `sys._MEIPASS` for bundled reads; `platformdirs` for r/w; no `__file__`/`cwd()` in runtime | ✓ SATISFIED | resources.py helpers + backend.py migration; grep guards return zero hits. |

**Orphan check:** No orphaned requirements. Phase 1 maps SIDE-01..05 and all 5 appear in at least one plan's `requirements:` frontmatter.

### Scope Boundary Check (CONTEXT N-01..N-04)

| Constraint | Status | Evidence |
|------------|--------|----------|
| N-01: No Tauri/Rust code | ✓ RESPECTED | `src-tauri/**` glob returns zero files; no Rust sources committed. |
| N-02: No `--cache-dir` wired into `json_repo.py` | ✓ RESPECTED | `json_repo*` glob returns zero files — json_repo.py does not exist yet (correctly deferred to Phase 2). The `--cache-dir` flag exists on backend.py per D-01 but is not consumed by any cache implementation in Phase 1. |
| N-03: `supabase` remains in requirements.txt | ✓ RESPECTED | requirements.txt:10 `supabase>=2.4.0` retained. Phase 1 only excludes it from the PyInstaller bundle (spec excludes list); dev-mode Supabase access still works via `lolalytics_api.supabase_repo` imports in backend.py:11–18. |
| N-04: No seed-dataset bundling | ✓ RESPECTED | backend.spec datas list contains only `(certifi.where(), 'certifi')` — no champion/matchup/seed JSON bundling (deferred to v1.1 per CONTEXT §Deferred). |

### Pitfall Mitigations (Top 5 from Phase 1 research)

| Pitfall | Mitigation | Verified |
|---------|------------|----------|
| #2 UPX triples AV false-positives | `upx=False` locked at spec + CI grep guard | ✓ backend.spec:102 + build-smoke.yml:47–54 |
| #3 Ready-file/webview-show race (writing before server accepts) | In-process health probe + ready-file written only after first 200 | ✓ backend.py:1860–1876 |
| `_MEIPASS` detection ambiguity (cx_Freeze/py2exe also set `sys.frozen`) | Two-attribute idiom `getattr(sys, 'frozen', False) AND hasattr(sys, '_MEIPASS')` | ✓ resources.py:46 |
| Certifi bundle dropped | `datas=[(certifi.where(), 'certifi')]` + runtime `SSL_CERT_FILE` wiring | ✓ backend.spec:28 + backend.py:1957–1961 |
| Missing hidden imports (async_drivers, httpx.socks) | Explicit seed + `collect_submodules('websocket')` + commented discovery list | ✓ backend.spec:37–60 |

Additional belt-and-suspenders:
- Werkzeug reloader disabled (`debug=False`) — Pitfall #7 per RESEARCH.
- `allow_unsafe_werkzeug=True` — correct for single-user desktop sidecar.
- Loopback-only bind (`host='127.0.0.1'`, not `0.0.0.0`) — security fix (PITFALLS §Sec-7).
- `os._exit(1)` on probe timeout (not `sys.exit`) — required because `socketio.run` blocks the main thread.
- `CREATE_NEW_PROCESS_GROUP` on Windows spawn — required for `CTRL_BREAK_EVENT` shutdown to work.

### Data-Flow Trace (Level 4)

Not applicable. Phase 1 does not render user-visible data; artifacts are CLI helpers + build spec + CI workflow. Data flow is `CLI args → argparse → Flask server config → loopback bind`; all links verified at the wiring level.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| backend.py parses as valid Python | `python -c "import ast; ast.parse(open('backend.py').read())"` | "syntax OK" | ✓ PASS |
| backend.spec parses as valid Python | `python -c "import ast; ast.parse(open('backend.spec').read())"` | "spec OK" | ✓ PASS |
| All Wave 3 Python files parse cleanly | ast.parse on virustotal_check.py, test_virustotal_check.py, smoke_test_exe.py, test_backend_cli.py | "all OK" | ✓ PASS |
| build-smoke.yml valid YAML, runs-on windows-latest, triggers push+PR on main | `yaml.safe_load()` + assertions | all assertions pass | ✓ PASS |
| pyproject.toml test extras contain requests + python-socketio[client] pin | `tomllib.loads()` + list inspection | `['pytest>=7', 'requests', 'python-socketio[client]>=5.9.0,<6']` | ✓ PASS |
| virustotal_check.py exposes upload/poll/main | `import virustotal_check; hasattr(...)` | all True | ✓ PASS |
| resources.py imports; `LOL_DRAFT_APP_NAME='lol-draft-analyzer'`; `bundled_resource` returns Path | import + assertions via sys.path injection | OK; returns `F:\...\apps\backend\certifi\cacert.pem` in dev mode | ✓ PASS |
| backend.spec contains no `upx=True` | grep | 0 hits | ✓ PASS |
| backend.spec contains all 17 required markers (upx=False, certifi.where(), hidden imports, excludes, binary name, console=False) | grep | 17 matches | ✓ PASS |
| backend.py host binding is 127.0.0.1 (not 0.0.0.0) | grep | 1 hit at :2002 for 127.0.0.1; 0 hits for 0.0.0.0 | ✓ PASS |
| backend.py contains no `__file__` or `os.getcwd` on runtime path | grep | 0 hits each | ✓ PASS |
| backend.py uses canonical `from lolalytics_api.resources import ...` | grep | 1 hit at :41 | ✓ PASS |
| Workflow step ordering: `pip install -e .` present before pytest/build | grep line numbers | editable install at :42; pytest at :56–60; pyinstaller at :62–64 | ✓ PASS |
| `pytest test_backend_cli.py` against python backend.py passes on Windows | `pip install -e . && pip install -e ".[test]" && pytest test_backend_cli.py` | Not run here (requires full dev env + package install) — covered by human test | ? SKIP |
| `pyinstaller --clean --noconfirm backend.spec` produces dist/backend-x86_64-pc-windows-msvc.exe | CI run | Not run — requires windows-latest runner + PyInstaller 6.19.0 pinned | ? SKIP |
| Built `.exe` spawns, writes ready-file, smoke_test_exe.py exits 0 | CI run | Not run — requires built artifact | ? SKIP |
| VirusTotal detections ≤ 3 on built `.exe` | CI run with VT_API_KEY | Not run — advisory-only in Phase 1 per D-22 | ? SKIP |

Automated spot-checks: all runnable checks pass. Four remaining checks route to human verification because they require a windows-latest runner executing the full build.

### Anti-Patterns Found

None. All files are fully wired.

- `test_backend_cli.py` — real subprocess lifecycle, real Flask/Socket.IO contract assertions, no mocks.
- `smoke_test_exe.py` — real Socket.IO client + real HTTPS GET to example.com, no mocks.
- `virustotal_check.py` — real VT v3 API client with correct URLs, auth header, threshold logic; NOT a stub.
- `test_virustotal_check.py` — mocks `requests.post` / `requests.get` at the boundary (normal unit-test pattern; not a stub).
- `build-smoke.yml` — every step runs a real command; only `continue-on-error: true` is on the VT step (correct Phase 1 advisory behavior per D-22), not on anything else.
- `backend.py` — `/api/health` returns a real JSON body with live `cache_entries` count + timestamp; probe thread is real; atomic write is real.
- `backend.spec` — no `COLLECT` block (onefile); `upx=False`; datas/hidden_imports/excludes all populated with real values.
- `resources.py` — real `platformdirs` calls with `ensure_exists=True`; no TODO/placeholder comments.

No TODO/FIXME/placeholder/"coming soon" patterns found in any Phase 1 file.

### Human Verification Required

#### 1. Run the `build-smoke` GitHub Actions workflow on `windows-latest`

**Test:** Push a commit to `main` (or open a PR) so `.github/workflows/build-smoke.yml` runs.

**Expected:**
- Step "Set up Python 3.12" succeeds with pip cache.
- Step "Install runtime + build deps" succeeds (no version conflicts).
- Step "Install lolalytics_api (editable)" succeeds (editable install works on CI Python).
- Step "Enforce upx=False in spec" passes (fast-fail grep guard).
- Step "Unit + dev-mode integration tests" passes: `pytest test_backend_cli.py -v` shows 3 passed; `pytest scripts/test_virustotal_check.py -v` shows 8 passed.
- Step "PyInstaller build" produces `dist/backend-x86_64-pc-windows-msvc.exe` with no missing-hidden-import errors. If it fails on a missing import, uncomment the relevant entry from the discovery list in `backend.spec:54–59` (Plan-03 mechanical fix per 01-02-SUMMARY "Spec Additions Surfaced During Dev-Mode Testing").
- Step "Verify supabase NOT in bundle" passes (`strings | grep -i supabase` finds nothing).
- Step "Smoke test built .exe" passes: built `.exe` spawns, writes ready-file within 10 s, `smoke_test_exe.py --port` exits 0 (Socket.IO connect + `https://example.com/` GET both succeed).
- Step "Upload built .exe artifact" attaches `backend-exe` artifact with 7-day retention.

**Why human:** The entire CI pipeline has never been exercised (01-03-SUMMARY: "Status: Not yet observed"). PyInstaller-specific regressions (hidden-import misses, certifi-data drop, frozen-mode `_MEIPASS` path bugs, engineio threading driver not bundled) only surface during actual build+run on windows-latest. This is the canonical forcing function for Phase 1 acceptance per D-21.

#### 2. Confirm VirusTotal detections ≤ 3 on the built `.exe`

**Test:** Configure `VT_API_KEY` GitHub secret, then re-run the workflow. Observe the "VirusTotal scan (advisory)" step output.

**Expected:** `python scripts/virustotal_check.py dist/backend-x86_64-pc-windows-msvc.exe --max-detections 3` prints `VirusTotal detections: N (max: 3)` with `N ≤ 3`, exit 0.

**Why human:** D-22 intentionally keeps VT advisory (`continue-on-error: true`) in Phase 1 — Phase 4 flips this to a hard gate. No real VT detection count has been observed yet; the phase goal text ("passes a VirusTotal sanity threshold") technically requires this observation. Until it runs, we have wiring correctness but not threshold confirmation.

### Gaps Summary

No gaps requiring plan rework. Every code/config artefact exists, is substantive (not a stub), is wired to the next layer, and respects all four scope-boundary constraints (N-01..N-04). The 23 locked decisions (D-01..D-23) are all reflected in the committed files. All top-5 pitfalls from Phase 1 research are mitigated.

The only residual unknowns are (a) the first PyInstaller build on windows-latest may surface a missing hidden import that Plan 01's commented discovery list is explicitly designed to absorb, and (b) the VirusTotal advisory check is wired but has no observed detection count — this is an intentional Phase 1 / Phase 4 boundary per D-22 and the phase-level advisory-only acceptance from 01-03-SUMMARY "CI contract for Phase 1".

Both residuals route to `human_needed` rather than `gaps_found` because the codebase is demonstrably complete and the missing data only exists in the CI runner and VT API, not in the repository.

### Re-verification Hints (for future iterations)

- If step "PyInstaller build" fails with `ImportError: No module named X`, uncomment the matching entry in `backend.spec:54–59` discovery list. Retry CI.
- If step "Verify supabase NOT in bundle" fails: a new transitive dep pulled supabase back in. Audit the dependency graph; add missing exclude entries.
- If `test_backend_cli.py` fails with `ModuleNotFoundError: lolalytics_api`, the editable install step (`pip install -e .`) either ran in wrong cwd or Python env. Check step 4 of the workflow.
- If the smoke test times out waiting for ready-file: the probe thread may be deadlocked. Check that `daemon=True` and that the probe starts BEFORE `socketio.run` (backend.py:1948–1961 must remain in this order per Pattern 4).

---

*Verified: 2026-04-14*
*Verifier: Claude (gsd-verifier)*
