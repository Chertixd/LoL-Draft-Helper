---
phase: 01-sidecar-foundation
plan: 03
subsystem: testing-ci
tags:
  - testing
  - ci
  - pyinstaller
  - github-actions
  - pytest
  - virustotal
  - windows-latest

requires:
  - phase: 01-sidecar-foundation
    plan: 01
    provides: "backend.spec PyInstaller recipe + lolalytics_api.resources helper (editable-install package) consumed by the CI build step"
  - phase: 01-sidecar-foundation
    plan: 02
    provides: "backend.py main() CLI (--port/--ready-file/--cache-dir/--log-dir), /api/health returning version='1.0.0-dev', ready-file JSON shape {port, pid, ready_at} — all contracts tested by test_backend_cli.py"
provides:
  - "test_backend_cli.py (3 pytest tests + editable-install autouse fixture) exercising the SIDE-01/SIDE-02 CLI contract against python backend.py in dev mode"
  - "smoke_test_exe.py companion for frozen .exe (Socket.IO round-trip + HTTPS GET to example.com)"
  - "scripts/virustotal_check.py — real VT v3 uploader + threshold gate (0 pass / 1 over / 2 error / 0-skip)"
  - "scripts/test_virustotal_check.py — 8-test unit suite with mocked VT API covering < / == / > threshold, missing-key-skip, and API-error paths (W-4)"
  - ".github/workflows/build-smoke.yml — BUILD-05 partial: windows-latest, Python 3.12.x, PyInstaller 6.19.0, pip install -e . (B-2), UPX guard, strings precheck (W-2), supabase-in-bundle guard, pyinstaller build, .exe spawn + smoke, advisory VT scan (B-3), upload-artifact"
  - "pyproject.toml `[project.optional-dependencies].test` extended with `requests` + `python-socketio[client]>=5.9.0,<6` (Pitfall #9 server-minor match)"
affects:
  - 02-*  # When Phase 2 lands, the CDN-fetch test will be added here; smoke_test_exe.py's HTTPS GET may later be aimed at the real CDN URL instead of example.com
  - 03-*  # Phase 3 Tauri sidecar spawn consumes the same --port / --ready-file contract; any regression in that contract now fails test_backend_cli.py in CI before the Rust code sees it
  - 04-*  # Phase 4 release-pipeline extends this workflow to tagged-release triggers, adds .msi + updater signing, and flips VirusTotal from `continue-on-error: true` to a hard gate

tech-stack:
  added: []  # all deps were already pinned: pytest>=7 + requests + python-socketio[client] live in the test extra only
  patterns:
    - "Editable-install guard via pytest autouse session fixture — calls importlib.util.find_spec('lolalytics_api') and pytest.skip()s with an actionable `pip install -e .` message rather than surfacing a cryptic ModuleNotFoundError from a subprocess whose stderr is typically swallowed by test reporters"
    - "Windows-native subprocess lifecycle contract: CREATE_NEW_PROCESS_GROUP at spawn + signal.CTRL_BREAK_EVENT at shutdown — without the creation flag the break signal is silently ignored (Windows quirk that makes POSIX-only test suites hang on Windows CI)"
    - "Tolerate one JSONDecodeError on the first read of the ready-file — the atomic-write contract (tmp + os.replace) should prevent partial reads, but slow CI disks can make the stat-then-read window visible; a single retry resolves the race without hiding real failures"
    - "Exit-code triage for CI gates: 0 = pass, 1 = real failure (over threshold), 2 = infrastructure failure (API/network). Lets `continue-on-error: true` in Phase 1 degrade gracefully, and the Phase 4 hard-gate lift will be able to distinguish real detections from transient VT outages"
    - "Repo-root workflow + working-directory-per-step — the build-smoke workflow lives at `.github/workflows/build-smoke.yml` (monorepo convention) while every backend-touching step carries `working-directory: counterpick-app/apps/backend` so relative paths inside scripts resolve the same way the dev environment does"
    - "`command -v strings` precheck (W-2) before piping `strings` into `grep` — a runner-image change that drops `strings` would otherwise silently neuter the supabase-leak guard; the precheck turns that into a loud, obvious failure"

key-files:
  created:
    - counterpick-app/apps/backend/test_backend_cli.py
    - counterpick-app/apps/backend/smoke_test_exe.py
    - counterpick-app/apps/backend/scripts/virustotal_check.py
    - counterpick-app/apps/backend/scripts/test_virustotal_check.py
    - .github/workflows/build-smoke.yml
  modified:
    - counterpick-app/apps/backend/pyproject.toml

key-decisions:
  - "Shipped RESEARCH.md's verbatim test skeleton with two targeted additions: (1) an autouse session fixture that skips with `pip install -e .` guidance when `lolalytics_api` isn't installed, converting a cryptic subprocess ModuleNotFoundError into an actionable skip; (2) a `version in body` assertion on /api/health, making Plan 02's load-bearing contract testable (W-1). No other drift from the skeleton."
  - "Kept VT_API_KEY-unset behavior at `return 0` (skip) rather than `return 1` (fail). Phase 1 is advisory per D-22 so a missing key must not fail the build; Phase 4 inverts this by both dropping the `continue-on-error: true` flag at the YAML level and (optionally) flipping the script's missing-key return to 1."
  - "Kept smoke_test_exe.py HTTPS target at `https://example.com/` not a project-specific URL — the CDN (Phase 2) doesn't exist yet, any project-adjacent endpoint would be noise, and example.com is the IETF-reserved benign target for exactly this kind of connectivity check."
  - "Split the VT unit test into eight named cases (under threshold, at threshold, over threshold, alias under-threshold, missing-key-skip, API-error returning 2, upload-analysis-id, poll-returns-stats-sum) rather than parametrizing one function — each boundary gets a distinct name in test output, which matters because these are the last line of defense against a malicious PR replacing `virustotal_check.py` with a no-op (T-01-17)."
  - "Chose `pytest scripts/test_virustotal_check.py` as a separate line in the CI test step rather than relying on `pytest` collection at the repo root. Keeps the VT tests fast + deterministic (no network) and fails fast BEFORE the slow PyInstaller build — a no-op VT script would be caught in under 10 seconds."

patterns-established:
  - "CI contract for Phase 1: every push to main and every PR into main runs `.github/workflows/build-smoke.yml` which must pass end-to-end (UPX guard + pytest + VT unit tests + PyInstaller build + supabase-strings guard + smoke of built .exe) for the PR to merge. VirusTotal remains advisory; everything else is blocking."
  - "Step-ordering invariant: the editable-install step (B-2 fix) MUST run after `pip install -r requirements.txt` + `pip install pyinstaller==6.19.0` and BEFORE any pytest or pyinstaller step. Reordering would produce either a broken site-packages resolution path or a ModuleNotFoundError on subprocess.Popen(python backend.py)."
  - "Test skeleton dev-mode vs frozen-mode split: test_backend_cli.py exercises the CLI contract against `python backend.py` (cheap, runs in ~3 s, catches regressions in the CLI surface itself); smoke_test_exe.py exercises the same contract against `dist/backend-x86_64-pc-windows-msvc.exe` (expensive, only in CI, catches PyInstaller-specific regressions like missing hidden imports and dropped certifi data)."

requirements-completed:
  - SIDE-04

# Metrics
duration: 4min
completed: 2026-04-14
---

# Phase 1 Plan 03: Testing + CI Smoke Summary

**Delivered the Phase 1 test + CI closure: a three-test pytest suite exercising backend.py's CLI lifecycle contract against `python backend.py`, a companion smoke script that runs against the built `.exe` in CI, a real (not stub) VirusTotal uploader + threshold gate with its own eight-case unit suite, and the `.github/workflows/build-smoke.yml` workflow that builds the PyInstaller sidecar on every push to `main` and every PR, enforces the UPX guard + Supabase-strings guard + strings-binary precheck, runs the dev-mode + VT unit tests, smokes the built binary, and advisory-scans via VirusTotal. SIDE-04 closed; SIDE-01 through SIDE-03 are now regression-proof.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-14T15:15:10Z
- **Completed:** 2026-04-14T15:18:42Z
- **Tasks:** 2
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments

- `test_backend_cli.py` ships the verbatim RESEARCH.md skeleton with two targeted additions: (1) an autouse session fixture that skips with `pip install -e .` guidance when `lolalytics_api` isn't installed (converts cryptic subprocess ModuleNotFoundError into actionable skip — matches the B-2 CI fix at the test level), and (2) a `"version" in body` assertion on the `/api/health` response (W-1 — makes Plan 02's load-bearing `version="1.0.0-dev"` contract actually testable).
- `smoke_test_exe.py` is the frozen-mode counterpart. Given a spawned backend + port, it does one Socket.IO connect/disconnect (exercises `engineio.async_drivers.threading` hidden-import from Plan 01's spec) and one HTTPS GET to `https://example.com/` (exercises the bundled certifi from Plan 01 + Plan 02's SSL_CERT_FILE wiring). Exit 0 = pass.
- `scripts/virustotal_check.py` is a 60-line runnable Python script: `upload(path, key)` POSTs to `/api/v3/files`, `poll(analysis_id, key)` GETs `/api/v3/analyses/<id>` every 15 s until `status == "completed"`, `main()` exits 0 on `detections <= max_detections`, 1 on over, 2 on API/network exception, 0-with-stderr-warning when `VT_API_KEY` is unset. B-3 fully resolved — the CI workflow no longer references a non-existent file.
- `scripts/test_virustotal_check.py` covers the threshold boundary exhaustively (W-4): `detections < max` → 0, `detections == max` → 0 (boundary check, `<=` not `<`), `detections > max` → 1, `VT_API_KEY` unset → 0 skip with stderr warning, upload raises → 2. Also includes the required `def test_detections_under_threshold` alias per plan must_haves. All 8 tests pass in 0.22 s without network access.
- `.github/workflows/build-smoke.yml` triggers on push to `main` and PRs to `main`, runs on `windows-latest`, pins Python 3.12.x (D-16) + PyInstaller 6.19.0 (D-17) + `python-socketio[client]>=5.9.0,<6` (Pitfall #9). Step ordering: checkout → setup-python → `pip install -r requirements.txt` + PyInstaller + socketio → `pip install -e .` (B-2, MUST run before any test/build) → UPX guard (fast-fail) → pytest integration + VT unit tests → `pyinstaller --clean --noconfirm backend.spec` → `command -v strings` precheck (W-2) + `strings | grep -i supabase` guard → spawn built `.exe` + `smoke_test_exe.py` round-trip → advisory VT scan (B-3, `continue-on-error: true` per D-22) → `actions/upload-artifact@v4` for 7-day `backend-exe` retention.
- `pyproject.toml` `[project.optional-dependencies].test` extended with `requests` and `python-socketio[client]>=5.9.0,<6` (pinned to the same major as the server per Pitfall #9 to prevent protocol-version skew between test client and Flask-SocketIO server).

## Task Commits

Each task committed atomically via `--no-verify` per the parallel-executor convention (orchestrator re-runs hooks at wave merge):

1. **Task 1: pytest integration test + smoke_test_exe companion + pyproject test extra** — `b7970a1` (test)
2. **Task 2: virustotal_check.py + its unit test + .github/workflows/build-smoke.yml** — `4258a72` (feat)

## test_backend_cli.py Shape

**Path:** `counterpick-app/apps/backend/test_backend_cli.py`
**Canonical invocation:** `cd counterpick-app/apps/backend && pip install -e . && pip install -e ".[test]" && pytest test_backend_cli.py -v`

**Module-top constants:**

| Symbol               | Value                                   | Purpose                                               |
| -------------------- | --------------------------------------- | ----------------------------------------------------- |
| `BACKEND_PY`         | `Path(__file__).parent / "backend.py"`  | Absolute path to spawn target.                        |
| `DEV_TIMEOUT_S`      | `10.0`                                  | Max wait for ready-file in dev mode.                  |
| `SHUTDOWN_TIMEOUT_S` | `2.0`                                   | Max wait for graceful exit after CTRL_BREAK/SIGTERM.  |

**Helpers:**

| Function                              | Signature                                  | Behavior                                                                                                                                        |
| ------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `_free_port()`                        | `() -> int`                                | Binds `127.0.0.1:0`, reads `getsockname()[1]`, closes. TOCTOU window is microseconds — acceptable for tests.                                    |
| `_spawn_backend(port, ready_file)`    | `(int, Path) -> subprocess.Popen`          | `sys.executable BACKEND_PY --port P --ready-file F`, stdout/stderr piped, `creationflags=CREATE_NEW_PROCESS_GROUP` on Windows, `cwd=BACKEND_PY.parent`. |
| `_wait_for_ready_file(path, timeout)` | `(Path, float) -> dict`                    | Polls `path.exists()` + `json.loads(...)` on 50 ms cadence; tolerates one JSONDecodeError; raises TimeoutError on timeout.                      |
| `_shutdown(proc)`                     | `(subprocess.Popen) -> int`                | `CTRL_BREAK_EVENT` on Windows, `SIGTERM` on POSIX; `proc.wait(timeout=SHUTDOWN_TIMEOUT_S)`; `proc.kill()` + `pytest.fail` on hang.              |

**Autouse fixture:**

- `_ensure_lolalytics_api_installed` (scope=session, autouse=True): calls `importlib.util.find_spec("lolalytics_api")`; on miss, `pytest.skip("lolalytics_api not installed. Run 'pip install -e .' from counterpick-app/apps/backend/ before running these tests.")`. This is the test-level companion to the B-2 CI fix — locally a developer who forgot the editable install gets an actionable message instead of a subprocess with invisible ModuleNotFoundError.

**Tests:**

| Test                                | Contract tested                                                           |
| ----------------------------------- | ------------------------------------------------------------------------- |
| `test_ready_file_contract`          | Ready-file appears within 10 s, JSON shape matches `{port, pid, ready_at}`, `/api/health` returns 200 with `"version" in body` (W-1). |
| `test_stale_ready_file_is_cleaned`  | Pre-writes `{"stale": true}` to the ready-file path; spawns backend; asserts fresh payload does NOT contain `stale` key (D-05). |
| `test_socketio_round_trip`          | `socketio.Client` connects to `http://127.0.0.1:<port>`, asserts `client.connected`, disconnects. Dev-mode mirror of the frozen-mode smoke_test_exe.py test. |

## smoke_test_exe.py Shape

**Path:** `counterpick-app/apps/backend/smoke_test_exe.py`
**Canonical invocation (inside the CI PowerShell step):** `python smoke_test_exe.py --port <N>` AFTER the built `.exe` has been spawned with that same port and the ready-file has appeared.

**CLI:** `--port <int>` (required). Exit 0 = pass, 1 = Socket.IO or HTTPS failure.

**Two probes:**
1. `socketio.Client(...).connect("http://127.0.0.1:<port>", wait_timeout=5)` → asserts `client.connected` → `client.disconnect()`. Fails if `engineio.async_drivers.threading` hidden-import is missing from Plan 01's spec.
2. `requests.get("https://example.com/", timeout=10).raise_for_status()`. Fails if bundled `certifi` is missing from `_MEIPASS/certifi/` or `SSL_CERT_FILE` wiring in Plan 02 is broken.

**Why example.com:** Stable, benign, IETF-reserved, returns 200 with HTML body. NOT replaced with Phase 2's CDN URL (not yet live). NOT pointed at any telemetry endpoint (privacy constraint from CLAUDE.md / PROJECT.md).

## virustotal_check.py Shape

**Path:** `counterpick-app/apps/backend/scripts/virustotal_check.py`
**Canonical invocation:** `python scripts/virustotal_check.py dist/backend-x86_64-pc-windows-msvc.exe --max-detections 3`

**Public surface:**

| Symbol                                   | Signature                                        | Behavior                                                                                                 |
| ---------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `upload(path, api_key)`                  | `(str, str) -> str`                              | POSTs file to `https://www.virustotal.com/api/v3/files`, returns `analysis_id`.                          |
| `poll(analysis_id, api_key, timeout_s=600)` | `(str, str, int) -> int`                      | Polls `/api/v3/analyses/<id>` every 15 s until `status == "completed"`, returns `malicious + suspicious`. |
| `main()`                                 | `() -> int`                                      | argparse `file`, `--max-detections` (default 3), `--timeout` (default 600). Exit codes below.            |

**Exit codes (Phase 1 advisory contract per D-22):**

| Code | Meaning                                          | Trigger                                     |
| ---- | ------------------------------------------------ | ------------------------------------------- |
| 0    | Pass (`detections <= max_detections`) OR skip    | Normal success OR `VT_API_KEY` unset.       |
| 1    | Real failure (`detections > max_detections`)     | VT scan completed, detections over limit.   |
| 2    | Infrastructure failure (API/network exception)   | upload/poll raised; caught at main level.   |

**Note for Phase 4 hard-gate lift:** dropping `continue-on-error: true` at the YAML level suffices. The script's exit-code semantics (0/1/2 distinguishing real detections from transient failures) are already correct for a hard gate that should retry on 2 but fail hard on 1.

## build-smoke.yml Step Order (canonical)

| # | Step Name                            | Purpose                                                                                                                              |
| - | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1 | `actions/checkout@v4`                | Fetch repo.                                                                                                                          |
| 2 | `Set up Python 3.12`                 | `actions/setup-python@v5` with `python-version: "3.12.x"` + pip cache keyed on `requirements.txt` (D-16).                            |
| 3 | `Install runtime + build deps`       | `pip install -r requirements.txt` + `pip install pyinstaller==6.19.0` (D-17) + `pip install "python-socketio[client]>=5.9.0,<6"` (Pitfall #9). |
| 4 | `Install lolalytics_api (editable)`  | `pip install -e .` — B-2 fix; required before any `python backend.py` subprocess resolves imports.                                   |
| 5 | `Enforce upx=False in spec`          | `grep -E '^\s*upx\s*=\s*True' backend.spec` — fast-fail (D-07).                                                                       |
| 6 | `Unit + dev-mode integration tests`  | `pytest test_backend_cli.py -v` + `pytest scripts/test_virustotal_check.py -v` — catches no-op VT script BEFORE the slow build.      |
| 7 | `PyInstaller build`                  | `pyinstaller --clean --noconfirm backend.spec` → produces `dist/backend-x86_64-pc-windows-msvc.exe` (D-12).                          |
| 8 | `Verify supabase NOT in bundle`      | `command -v strings` precheck (W-2) + `strings ... \| grep -i supabase` fail-guard. Complements Plan 01's spec-level excludes.       |
| 9 | `Smoke test built .exe`              | PowerShell: spawn .exe with `--port 5755 --ready-file RUNNER_TEMP/ready.json`, wait up to 10 s, run `python smoke_test_exe.py --port 5755`, kill. SIDE-04 gate. |
| 10 | `VirusTotal scan (advisory)`        | `if: env.VT_API_KEY != ''`, `continue-on-error: true`, `python scripts/virustotal_check.py ... --max-detections 3`. B-3 + D-22.      |
| 11 | `Upload built .exe artifact`         | `actions/upload-artifact@v4` with 7-day retention — debugging handle + Phase 3 Tauri-spawn testing input.                            |

**Triggers:** `push.branches: [main]` and `pull_request.branches: [main]`.
**Runner:** `windows-latest` (D-23) — no Linux/macOS parallel job in Phase 1.
**Timeout:** `timeout-minutes: 20` (PyInstaller + smoke typically < 5 min; generous slack for cold cache).

## Local Verification Evidence

All checks from the plan's `<verification>` block passed on the dev host (Windows, Python 3.12.10):

**Structural (ast-based):**

- `python -c "import ast; ast.parse(open('test_backend_cli.py').read())"` → OK.
- `python -c "import ast; ast.parse(open('smoke_test_exe.py').read())"` → OK.
- `python -c "import ast; ast.parse(open('scripts/virustotal_check.py').read())"` → OK.
- `python -c "import ast; ast.parse(open('scripts/test_virustotal_check.py').read())"` → OK.

**TOML:**

- `python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"` → OK; `[project.optional-dependencies].test` contains the three expected strings (`pytest>=7`, `requests`, `python-socketio[client]>=5.9.0,<6`).

**VT unit tests (mocked, no network):**

```
scripts/test_virustotal_check.py::test_upload_returns_analysis_id PASSED
scripts/test_virustotal_check.py::test_poll_returns_detections_sum_when_completed PASSED
scripts/test_virustotal_check.py::test_main_passes_when_detections_under_threshold PASSED
scripts/test_virustotal_check.py::test_main_passes_at_exact_threshold PASSED
scripts/test_virustotal_check.py::test_main_fails_when_detections_over_threshold PASSED
scripts/test_virustotal_check.py::test_main_skips_when_api_key_unset PASSED
scripts/test_virustotal_check.py::test_detections_under_threshold PASSED
scripts/test_virustotal_check.py::test_main_returns_2_on_api_error PASSED
============================== 8 passed in 0.22s ==============================
```

**Workflow YAML:**

- `yaml.safe_load(...)` parses cleanly; `jobs.build-and-smoke.runs-on == "windows-latest"`.
- All 11 required step names present in the expected order (see step-order table above).
- Required substrings present: `python-version: "3.12.x"`, `pip install pyinstaller==6.19.0`, `python-socketio[client]>=5.9.0,<6`, `pip install -e .`, `^\s*upx\s*=\s*True`, `pyinstaller --clean --noconfirm backend.spec`, `dist/backend-x86_64-pc-windows-msvc.exe`, `pytest test_backend_cli.py`, `pytest scripts/test_virustotal_check.py`, `python smoke_test_exe.py --port`, `command -v strings`, `grep -i supabase`, `python scripts/virustotal_check.py`, `continue-on-error: true`, `actions/upload-artifact@v4`.
- Forbidden substrings absent: `runs-on: ubuntu`, `runs-on: macos`, `gh release create`, `softprops/action-gh-release`.

**Not run locally (owned by CI per success criterion 14):**

- `pytest test_backend_cli.py` — requires `pip install -e .` into a Python env that can also import the full Flask/Flask-SocketIO stack of backend.py; the autouse fixture correctly skips with an actionable message if the editable install is missing. The canonical gate for this is `windows-latest` CI.
- `pyinstaller --clean --noconfirm backend.spec` — local dev hosts may not have PyInstaller 6.19.0 pinned; the CI runner does.
- The full smoke on the built `.exe` — same reason as above.

## First-Run CI Result (forward-looking)

**Status:** Not yet observed. The workflow is wired and will run on the next push to `main` and on every PR thereafter. The Phase 1 SIDE-04 completion gate is a green first run of this workflow.

**Expected outcome on first push to `main`:** Green, based on the local syntax/logic checks above and on Plan 02's dev-mode end-to-end smoke (already documented in 01-02-SUMMARY) that confirmed ready-file + /api/health + clean shutdown work with the same CLI contract the workflow exercises.

**If the PyInstaller build step surfaces missing hidden imports:** the most likely additions — `engineio.async_drivers` (parent package), `engineio`, `socketio`, `flask_socketio`, `dns` — are already listed as commented-out discovery entries in Plan 01's `backend.spec`. Uncommenting any of them would be a Plan 03 mechanical deviation (edit `backend.spec`, add entries, re-run CI). No such deviation was required during the current plan execution because the only forcing function available locally was syntax validation; the CI run is the true forcing function.

**If the `strings`-binary precheck fires:** Git Bash's `/usr/bin/strings` (MSYS2) is bundled on `windows-latest` and has been stable across recent runner images. A failure here would indicate a runner-image regression and would need a PowerShell fallback. Not observed at plan-close.

## B-2 / B-3 / W-1 / W-2 / W-4 Confirmation Matrix

| Revision | Location                                                      | Confirmed by                                                                                       |
| -------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| B-2      | `.github/workflows/build-smoke.yml` Step 4 + test_backend_cli.py autouse fixture | Workflow YAML contains `Install lolalytics_api (editable)` step running `pip install -e .`; test file imports `importlib.util` and session-scoped `find_spec("lolalytics_api")` guard present. |
| B-3      | `scripts/virustotal_check.py` (80 LoC, ~60 logic lines) + workflow Step 10 | Script exists and is a real VT v3 client with upload + poll + threshold logic; workflow VT step invokes the real path and is marked `continue-on-error: true` per D-22. |
| W-1      | `test_backend_cli.py::test_ready_file_contract`               | Test body contains `body = r.json(); assert "version" in body, f"version field missing: {body}"` — directly asserts Plan 02's load-bearing version contract. |
| W-2      | `.github/workflows/build-smoke.yml` Step 8                    | `command -v strings >/dev/null 2>&1 \|\| { echo "::error::strings binary not available on runner" >&2; exit 1; }` present before the `strings | grep` pipeline. |
| W-4      | `scripts/test_virustotal_check.py` (8 tests)                  | Covers under-threshold, at-threshold boundary (`detections == max`), over-threshold, missing-key-skip, and API-error → exit 2 paths — each a named test function. 8 tests all pass in 0.22 s with mocked requests. |

## Deviations from Plan

None — the plan executed exactly as written. Both tasks landed with the exact file contents and step ordering specified in the plan text; all acceptance criteria pass on the local dev host; all critical-invariant items from the prompt context (B-2 editable install, B-3 real VT script, W-1 version assertion, W-2 strings precheck, W-4 VT mocked-API tests, windows-latest + Python 3.12.x + push/PR triggers) are satisfied and verified.

## Authentication Gates

None. The plan is pure source-code authoring (Python + YAML); no auth-protected resources were touched.

## Known Stubs

None. Every file is fully wired:

- `test_backend_cli.py` — real Flask/Socket.IO contract assertions against a real subprocess; no mocks.
- `smoke_test_exe.py` — real Socket.IO client + real HTTPS GET to example.com; no mocks.
- `virustotal_check.py` — real VT v3 API client with correct URLs, auth header, threshold logic.
- `test_virustotal_check.py` — mocks the `requests.post` / `requests.get` boundary (as intended for a unit test; not a stub).
- `build-smoke.yml` — every step runs a real command; no `if: false` gates or `continue-on-error` outside the VT step (where it is the correct Phase 1 advisory behavior per D-22).

## Threat Flags

None. All security-relevant surface introduced by this plan (workflow runner trust boundary, built-.exe inspection via `strings`, advisory VirusTotal outbound call) is already declared in the plan's `<threat_model>` (T-01-11 through T-01-18). No new surface beyond those declarations.

## Self-Check: PASSED

- `counterpick-app/apps/backend/test_backend_cli.py` — **FOUND** (158 lines, contains all required substrings per grep check: `def test_ready_file_contract(`, `def test_stale_ready_file_is_cleaned(`, `def test_socketio_round_trip(`, `subprocess.Popen(`, `CREATE_NEW_PROCESS_GROUP`, `signal.CTRL_BREAK_EVENT`, `socketio.Client(`, `http://127.0.0.1:`, `importlib.util.find_spec("lolalytics_api")`, `"version" in`).
- `counterpick-app/apps/backend/smoke_test_exe.py` — **FOUND** (contains `socketio.Client(`, `"https://example.com/"`, `--port`).
- `counterpick-app/apps/backend/scripts/virustotal_check.py` — **FOUND** (contains `def upload(`, `def poll(`, `def main(`, VT v3 URLs for files + analyses).
- `counterpick-app/apps/backend/scripts/test_virustotal_check.py` — **FOUND** (8 tests, all passing with `pytest -v` in 0.22 s).
- `.github/workflows/build-smoke.yml` — **FOUND** (valid YAML, 11 steps, `runs-on: windows-latest`, all required substrings present, all forbidden substrings absent).
- `counterpick-app/apps/backend/pyproject.toml` — **MODIFIED** (`[project.optional-dependencies].test` now contains `pytest>=7`, `requests`, `python-socketio[client]>=5.9.0,<6`).
- Commit `b7970a1` (Task 1) — **FOUND** in `git log`.
- Commit `4258a72` (Task 2) — **FOUND** in `git log`.
