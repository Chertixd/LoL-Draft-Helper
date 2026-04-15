---
phase: 01-sidecar-foundation
plan: 02
subsystem: sidecar-lifecycle
tags:
  - python
  - cli
  - flask-socketio
  - lifecycle
  - argparse
  - ready-file
  - loopback-bind
  - pyinstaller-readiness

requires:
  - phase: 01-sidecar-foundation
    plan: 01
    provides: "lolalytics_api.resources module (LOL_DRAFT_APP_NAME, bundled_resource(), user_cache_dir(), user_log_dir(), user_data_dir()) installed via editable package"
provides:
  - "backend.py main() entrypoint with argparse CLI (--port / --ready-file / --cache-dir / --log-dir) binding 127.0.0.1 only"
  - "/api/health route returning {'status': 'ok', 'version': '1.0.0-dev', ...} — load-bearing version field for Plan 03 assertion"
  - "Ready-file lifecycle contract: atomic JSON write of {port, pid, ready_at} after in-process GET /api/health returns 200; os._exit(1) on 5 s probe timeout"
  - "SSL_CERT_FILE / REQUESTS_CA_BUNDLE env vars pointing at bundled_resource('certifi/cacert.pem') when the path exists (frozen mode only)"
  - "TimedRotatingFileHandler on root logger (when='midnight', backupCount=14, encoding='utf-8') writing to log_dir / 'backend.log'"
  - "Zero __file__ / zero os.getcwd() on the runtime path (D-14 invariant achieved file-wide)"
affects:
  - 01-03   # CI smoke test (test_backend_cli.py) — asserts /api/health version field and ready-file shape
  - 02-*    # Phase 2 json_repo.py swaps the cache_data.json reader/writer; path already at user_cache_dir()
  - 03-*    # Phase 3 Tauri sidecar spawn consumes the --port / --ready-file contract directly

tech-stack:
  added: []  # all runtime deps already pinned in Plan 01 (platformdirs) and existing requirements (requests, flask-socketio)
  patterns:
    - "Probe-thread-before-socketio.run — daemon=True health probe spawned FIRST because socketio.run blocks the main thread for the server's lifetime (Pattern 4 / Pitfall #1)"
    - "os._exit(1) on probe timeout — sys.exit from a sub-thread is absorbed by the thread machinery, leaving the main thread still inside socketio.run"
    - "Atomic ready-file write via tmp + os.replace — atomic on both Windows NTFS (Python 3.3+) and POSIX; eliminates half-written JSON race with Tauri host polling"
    - "Stale-ready-file cleanup BEFORE probe starts (D-05) — idempotent restart contract"
    - "host='127.0.0.1' + debug=False + allow_unsafe_werkzeug=True — the three flags that make Flask-SocketIO safe as a single-user desktop sidecar"
    - "Extend existing route rather than duplicate — the pre-existing /api/health was augmented with the load-bearing `version` field rather than replaced, preserving backward compatibility with existing dev-mode consumers (cache_entries, timestamp, service)"
    - "D-14 runtime-path cleanup via three targeted rewrites: dotenv env_path, CACHE_FILE, and champion_roles.json config_path — each routed through bundled_resource() or user_cache_dir() as appropriate"

key-files:
  created: []
  modified:
    - counterpick-app/apps/backend/backend.py  # +272 / -12 (diff from HEAD before task)

key-decisions:
  - "Kept the existing /api/health route and augmented it with `version: '1.0.0-dev'` rather than adding a new duplicate route — the existing route already returned status:'ok' and had a stable consumer shape (cache_entries, service, timestamp). Adding `version` is the only behaviorally load-bearing change; the rest remain for backward-compat with any existing dev-mode clients."
  - "Migrated CACHE_FILE from `Path(__file__).parent / 'cache_data.json'` to `user_cache_dir() / 'cache_data.json'` — required to satisfy D-14 (zero __file__ on runtime path). N-02 only forbids wiring --cache-dir into json_repo.py (which does not exist until Phase 2); using user_cache_dir() here is the exact call out from the plan's Edit 5 (\"Write cache/state → `user_cache_dir() / '<filename>'`\"). This is a behavior change for dev mode — the cache file now lives at `%LOCALAPPDATA%\\lol-draft-analyzer\\Cache\\cache_data.json` instead of next to backend.py — but it is the correct direction and pre-positions Phase 2's json_repo.py swap."
  - "Converted env_path and champion_roles.json config_path to `bundled_resource(...)` — both were `__file__`-anchored and both now route through the resources helper. `.env` does not exist in the frozen bundle (spec does not include it) so load_dotenv becomes a no-op there; the existence guard `if env_path.exists():` prevents the call from raising. `champion_roles.json` ships inside the lolalytics_api package; `bundled_resource('src/lolalytics_api/champion_roles.json')` resolves in both modes."
  - "Probe interval locked at 50 ms and timeout at 5 s per D-03 default — no CI flakiness justification to deviate."
  - "Log level at INFO — adequate for CI smoke test per CONTEXT §Claude's Discretion bullet 4. Full LCU-auth redaction policy lands in Phase 3 (LOG-01..05 are Phase 3 requirements)."
  - "Reworded one comment to avoid the literal substring `os.getcwd` (now `the current-working-directory helper`) — the CI-style grep guard `! grep -n 'os\\.getcwd' backend.py` would otherwise false-positive on prose. Identical spec-file-comment rewording pattern Plan 01 used for pathex (recorded in 01-01-SUMMARY)."

patterns-established:
  - "backend.py CLI contract: `python backend.py --port <N> --ready-file <path>` binds 127.0.0.1:<N>, writes <path> atomically only after `GET /api/health` returns 200 in-process, exits non-zero on 5 s probe timeout. Plan 03's test_backend_cli.py consumes this directly. Phase 3's Tauri sidecar-spawn Rust code also consumes this — the protocol is now frozen."
  - "Ready-file JSON shape: {\"port\": <int>, \"pid\": <int>, \"ready_at\": \"<iso8601 UTC>\"}. `ready_at` uses `datetime.now(timezone.utc).isoformat()` (ends with `+00:00` — not the `Z` suffix). Plan 03 tests should match this exact shape."
  - "Health-endpoint version string = `\"1.0.0-dev\"` — Plan 03 tests MUST assert this exact substring (or loosen to `r'\\d+\\.\\d+\\.\\d+(-\\w+)?'` if preferred); Phase 4 release-build will flip `-dev` to the tagged version."

requirements-completed:
  - SIDE-01
  - SIDE-02

# Metrics
duration: 20min
completed: 2026-04-14
---

# Phase 1 Plan 02: backend.py main() Rewrite Summary

**Rewrote the bottom of `backend.py` to land the full Phase 1 sidecar-lifecycle contract: argparse-driven CLI (`--port` / `--ready-file` / `--cache-dir` / `--log-dir`), a load-bearing `version` field on `/api/health`, a daemon probe thread that atomically writes the ready-file after the server is actually serving, SSL_CERT_FILE wiring to bundled certifi, daily-rotating file logging, and loopback-only bind. Eliminated all three `__file__` references from the runtime path per D-14 — backend.py is now `__file__`- and `cwd()`-free.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-04-14T17:03:00Z
- **Completed:** 2026-04-14T17:10:00Z
- **Tasks:** 1
- **Files modified:** 1 (0 created, 1 modified)

## Accomplishments

- `main()` entrypoint with four-flag argparse CLI matches Plan 03's consumer contract and Phase 3's Tauri sidecar spawn contract exactly. `--help` exits 0 and lists all four flags.
- `/api/health` now returns `{"status": "ok", "version": "1.0.0-dev", "service": "lolalytics-backend", "cache_entries": <n>, "timestamp": "<iso>"}` — the `status` + `version` pair is the load-bearing Plan 03 assertion; the remaining fields are preserved for backward compatibility with existing dev-mode consumers.
- Daemon probe thread spawned BEFORE `socketio.run` (the critical Pattern 4 ordering) polls `http://127.0.0.1:<port>/api/health` on a 50 ms interval with a 5 s overall budget; on the first 200 it writes the ready-file atomically (`tmp + os.replace`) with payload `{port, pid, ready_at}`; on timeout it calls `os._exit(1)` (not `sys.exit`, which the thread machinery would absorb).
- `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` env vars set at startup to `bundled_resource("certifi/cacert.pem")` when that path exists (frozen mode only; dev mode falls back to pip-installed certifi). `os.environ.setdefault(...)` so the existing test-harness overrides still win.
- Stale ready-file at the given path is deleted BEFORE the probe starts (D-05 idempotent cleanup) — prevents a Tauri host from seeing a stale flag before Python has rewritten it.
- `socketio.run(app, host="127.0.0.1", port=args.port, debug=False, allow_unsafe_werkzeug=True)` — loopback-only bind (security fix: the existing code was `host='0.0.0.0'` which exposed the LCU bridge over LAN), Werkzeug reloader disabled (breaks PyInstaller --onefile and the ready-file protocol), and Flask-SocketIO 5+ production flag set.
- Root logger wired to a `TimedRotatingFileHandler(log_dir / "backend.log", when="midnight", backupCount=14, encoding="utf-8")` with formatter `%(asctime)s [%(levelname)s] %(name)s: %(message)s` — INFO level per CONTEXT's discretion allowance; full redaction policy is deferred to Phase 3.
- D-14 file-wide cleanup: three existing `__file__` references (line 48 `.env` load, line 56 `CACHE_FILE`, line 182 `champion_roles.json`) all migrated to `bundled_resource()` / `user_cache_dir()`. `grep -n '__file__' backend.py` and `grep -n 'os\.getcwd' backend.py` both return zero hits.
- Existing Flask routes, Socket.IO event handlers, `lolalytics_api.supabase_repo` imports, and the dev-mode startup banner (`print("=" * 60)` etc.) are all preserved per N-02 / N-03.

## Task Commits

1. **Task 1: Rewrite backend.py main() — CLI, health route, probe thread, ready-file, SSL wiring** — `c7c0ab2` (feat)

(Commit used `--no-verify` per wave-2 parallel-executor convention; orchestrator will re-run hooks at wave merge.)

## Final main() / Helpers Shape

**CLI (argparse):**

| Flag             | Type   | Default                      | Purpose                                           |
| ---------------- | ------ | ---------------------------- | ------------------------------------------------- |
| `--port`         | `int`  | `5000`                       | Loopback bind port; `0` for OS-assigned.          |
| `--ready-file`   | `Path` | `None`                       | Ready-marker JSON target.                         |
| `--cache-dir`    | `Path` | `user_cache_dir()`           | Override for platformdirs cache location.         |
| `--log-dir`      | `Path` | `user_log_dir()`             | Override for platformdirs log location.           |

**Helper functions (all private, all file-scope):**

| Function                              | Signature                                                                                      | Behavior                                                                                                          |
| ------------------------------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `_configure_logging(log_dir)`         | `(Path) -> None`                                                                               | Creates `log_dir`, attaches `TimedRotatingFileHandler(log_dir / "backend.log", "midnight", backupCount=14)` to root at INFO. |
| `_atomic_write_ready_file(path, payload)` | `(Path, dict) -> None`                                                                     | Ensures parent exists; writes `tmp = path.with_suffix(path.suffix + ".tmp")`; `os.replace(tmp, path)`.            |
| `_probe_health_then_signal_ready(port, ready_file, interval_s=0.05, timeout_s=5.0)` | `(int, Path\|None, float, float) -> None` | Polls `http://127.0.0.1:{port}/api/health` on `interval_s` until 200 or `timeout_s`; writes ready-file on success via the atomic helper; calls `os._exit(1)` on timeout. |
| `main()`                              | `() -> None`                                                                                   | Parse args → configure logging → setdefault SSL_CERT_FILE/REQUESTS_CA_BUNDLE → unlink stale ready-file → start daemon probe thread → print dev-mode banner → `socketio.run(app, host="127.0.0.1", port=args.port, debug=False, allow_unsafe_werkzeug=True)`. |

**Probe interval / timeout:** locked at the D-03 defaults of 50 ms / 5 s; not tuned down to 25 ms because live smoke test on this machine flipped the ready-file in well under 1 s.

**Log level:** INFO on root (per CONTEXT §Claude's Discretion bullet 4). Adequate for CI smoke test; full LCU-auth-redaction policy lands in Phase 3.

## D-14 / SIDE-05 Migration Ledger

Three `__file__` references existed on the runtime path of the original backend.py. All three were converted:

| Original (line#)                                                                 | Converted to                                                      | Why this works                                                                                                |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `env_path = Path(__file__).parent / '.env'` (line 48)                            | `env_path = bundled_resource('.env')` + `if env_path.exists():`  | Dev mode resolves to `apps/backend/.env`; frozen mode has no `.env` (spec excludes it) so `load_dotenv` no-ops cleanly. |
| `CACHE_FILE = Path(__file__).parent / 'cache_data.json'` (line 56)               | `CACHE_FILE = user_cache_dir() / 'cache_data.json'`                | Moves the cache file to `%LOCALAPPDATA%\lol-draft-analyzer\Cache\cache_data.json`; Phase 2 swaps this to json_repo.py. |
| `config_path = os.path.join(os.path.dirname(__file__), 'src', 'lolalytics_api', 'champion_roles.json')` (line 182) | `config_path = bundled_resource('src/lolalytics_api/champion_roles.json')` | Dev mode: backs out to apps/backend/ and descends; frozen mode: `_MEIPASS/src/lolalytics_api/champion_roles.json` (PyInstaller collect_submodules lolalytics_api keeps this). |

Post-migration `grep -n '__file__' backend.py` → **0 hits**. Post-migration `grep -n 'os\.getcwd' backend.py` → **0 hits**.

**Note on cache file location change:** This is a dev-mode behavior change: the cache file now lives at `%LOCALAPPDATA%\lol-draft-analyzer\Cache\cache_data.json` rather than next to `backend.py`. Any existing dev cache will be ignored (a new one will be built on first run) — acceptable because cache_data.json is a 24 h TTL cache, not persistent state. The plan's Edit 5 explicitly directs this ("Write cache/state → `user_cache_dir() / '<filename>'`"), and Phase 2's json_repo.py will replace the read/write logic entirely.

## Health-Endpoint Contract (for Plan 03)

- **Method / Path:** `GET /api/health`
- **Status:** `200 OK`
- **Body (JSON):** `{"status": "ok", "version": "1.0.0-dev", "service": "lolalytics-backend", "cache_entries": <int>, "timestamp": "<iso-8601>"}`
- **Load-bearing keys (MUST assert):** `status == "ok"`, `version == "1.0.0-dev"` (or regex `^\d+\.\d+\.\d+(-\w+)?$`).
- **Diagnostic keys (MAY assert):** `service`, `cache_entries`, `timestamp` — preserved for backward compatibility; free to ignore in Plan 03.

**Version string:** `"1.0.0-dev"` — matches the spec-level dev placeholder. Phase 4 release-build will update this to the tagged release version.

## Import Path Confirmation

`backend.py` imports the Plan 01 resources helper as:

```python
from lolalytics_api.resources import (
    LOL_DRAFT_APP_NAME,
    bundled_resource,
    user_cache_dir,
    user_log_dir,
)
```

This is **the canonical path** matching the existing `from lolalytics_api import ...` style at line 10 (which works because `pip install -e .` picks up `[tool.setuptools.package-dir] "" = "src"` from pyproject.toml).

**Verified absent:**
- `from src.resources` — **0 hits**
- `from src.lolalytics_api` — **0 hits**

(The plan's negative grep guards pass.)

## Spec Additions Surfaced During Dev-Mode Testing

**None so far.** The dev-mode smoke test (`python backend.py --port 5077 --ready-file /tmp/rtest.json`) succeeded end-to-end with zero hidden-import errors:
- Flask starts,
- Probe thread fires,
- Ready-file written within <1 s,
- `/api/health` returns 200 with the correct JSON shape,
- Clean SIGTERM exit (143 = 128 + 15).

**Plan 03 / frozen-bundle surprises (forward-looking):** if Plan 03's CI run of `pyinstaller --clean --noconfirm backend.spec` surfaces missing hidden imports, the most likely additions (already listed as commented-out in `backend.spec` by Plan 01's Task 2) are `engineio.async_drivers`, `engineio`, `socketio`, `flask_socketio`, `dns`. Uncommenting any of these is a Plan 03 mechanical deviation — no spec change to this plan's artifacts needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing critical functionality] Extended existing `/api/health` route rather than adding a second one**

- **Found during:** Task 1 pre-edit inspection
- **Issue:** The existing `backend.py` already has a `/api/health` route at line 165 returning `{status, service, cache_entries, timestamp}`. The plan text reads "add `/api/health` route" as if no such route existed. Adding a second `@app.route('/api/health')` decorator would have triggered a Flask `AssertionError: View function mapping is overwriting an existing endpoint function`.
- **Fix:** Modified the existing route in place — added the load-bearing `"version": "1.0.0-dev"` field (which Plan 03's assertion depends on) and a comprehensive docstring; preserved the three pre-existing diagnostic fields (`service`, `cache_entries`, `timestamp`) for backward compatibility with any existing dev-mode consumers.
- **Files modified:** `counterpick-app/apps/backend/backend.py` (lines 166–182, inside the existing route handler)
- **Commit:** `c7c0ab2`
- **Plan-facing contract impact:** none — `status == "ok"` and `version == "1.0.0-dev"` are both present. Plan 03 assertions unchanged.

**2. [Rule 2 — Missing critical functionality] Migrated CACHE_FILE from `__file__`-anchor to `user_cache_dir()` — behavior change for dev-mode cache location**

- **Found during:** D-14 grep-pass (Edit 5 of the task)
- **Issue:** D-14 requires zero `__file__` on the runtime path; the existing `CACHE_FILE = Path(__file__).parent / 'cache_data.json'` violates this. N-02 forbids wiring `--cache-dir` into `json_repo.py` (which doesn't exist yet), but does not forbid moving the existing CACHE_FILE to `user_cache_dir()`.
- **Fix:** `CACHE_FILE = user_cache_dir() / 'cache_data.json'` — follows the plan's own Edit 5 direction verbatim ("Write cache/state → `user_cache_dir() / '<filename>'`"). Cache file now lives at `%LOCALAPPDATA%\lol-draft-analyzer\Cache\cache_data.json` in dev mode.
- **Files modified:** `counterpick-app/apps/backend/backend.py` (line 56 area)
- **Commit:** `c7c0ab2`
- **Behavior impact:** Dev-mode cache resets on first launch (the old `apps/backend/cache_data.json` is ignored). Acceptable because cache_data.json has a 24 h TTL and is regenerated on demand. Phase 2's json_repo.py will replace the read/write logic entirely.

**3. [Rule 3 — Blocking issue] Reworded D-14 documentation comment to avoid `os.getcwd` literal substring**

- **Found during:** verification battery run (`! grep -n 'os\.getcwd' backend.py`)
- **Issue:** A comment explaining the D-14 invariant contained the literal `os.getcwd()`. The CI-style grep guard `! grep -n 'os\.getcwd' backend.py` is substring-based and would false-positive on the comment.
- **Fix:** Reworded to `the current-working-directory helper` — identical pattern to Plan 01's spec-comment rewording for `pathex=['src']` (documented in 01-01-SUMMARY).
- **Files modified:** `counterpick-app/apps/backend/backend.py` (line 63)
- **Commit:** `c7c0ab2` (squashed into the single task commit)

### Authentication Gates

None. No auth gates were hit; all work was source-code edits plus in-process smoke tests against a loopback port.

## Verification Evidence

All automated checks from the plan's `<verification>` block pass against the dev environment (`pip install -e .` + `pip install -r requirements.txt` completed):

**Structural (ast-based):**
- `import ast; ast.parse(open('backend.py').read())` → syntax OK.
- Top-level function set ⊇ `{'main', '_probe_health_then_signal_ready', '_atomic_write_ready_file', '_configure_logging'}` → **OK**.

**CLI surface:**
- `python backend.py --help` exits 0 and prints all four flags (`--port`, `--ready-file`, `--cache-dir`, `--log-dir`) with help text.

**Security invariants:**
- `grep -E "host=['\"]0\.0\.0\.0['\"]" backend.py` → **0 hits** (OK).
- `grep -E "host=['\"]127\.0\.0\.1['\"]" backend.py` → **1 hit** inside `socketio.run(...)` (OK).
- `grep -E 'debug=False' backend.py` → present.
- `grep -E 'allow_unsafe_werkzeug=True' backend.py` → present.

**Lifecycle invariants:**
- `grep -E 'daemon=True' backend.py` → present (probe thread + other daemon threads preserved).
- `grep -E 'os\.replace\(' backend.py` → present (atomic ready-file write).
- `grep -E 'threading\.Thread\(target=_probe_health_then_signal_ready' backend.py` → present.

**Import invariants:**
- `grep -E 'from lolalytics_api\.resources import' backend.py` → present.
- `grep -E 'from src\.resources' backend.py` → **0 hits**.
- `grep -E 'from src\.lolalytics_api' backend.py` → **0 hits**.

**D-14 invariants:**
- `grep -n '__file__' backend.py` → **0 hits**.
- `grep -n 'os\.getcwd' backend.py` → **0 hits**.

**End-to-end behavioral smoke (not strictly required by this plan; Plan 03 owns this):**

```
$ python backend.py --port 5077 --ready-file /tmp/rtest.json &
$ sleep 3
$ cat /tmp/rtest.json
{"port": 5077, "pid": 3620, "ready_at": "2026-04-14T15:09:19.289189+00:00"}
$ curl -s http://127.0.0.1:5077/api/health
{"cache_entries":0,"service":"lolalytics-backend","status":"ok","timestamp":"2026-04-14T17:09:20.727143","version":"1.0.0-dev"}
$ kill <pid>                           # exits 143 = 128 + SIGTERM
```

Ready-file appears within <1 s of process start, matches the D-04 shape exactly, `/api/health` returns the correct body including `version`, and clean SIGTERM exit. Plan 03's `test_backend_cli.py` will formalize this assertion.

## Self-Check: PASSED

- `counterpick-app/apps/backend/backend.py` modified and on disk — **FOUND** (now 2,010 lines; was 1,751 pre-edit).
- Commit `c7c0ab2` (Task 1) — **FOUND** in `git log`:

```
$ git log --oneline -3
c7c0ab2 feat(01-02): rewrite backend.py main() with CLI, health probe, ready-file
022c90d docs(01-01): complete sidecar-foundation plan 01
9470f33 feat(01-01): add backend.spec PyInstaller recipe
```

- `.planning/phases/01-sidecar-foundation/01-02-SUMMARY.md` created (this file).
- No stubs introduced. No hardcoded empty `=[]` / `={}` defaults flowing to UI. `version = "1.0.0-dev"` is a real version string consumed by Plan 03 and Phase 4 will flip it to the tagged release.
- Threat surface stays within this plan's `<threat_model>` declarations:
  - T-01-05 (LAN exposure) — **mitigated**: `host="127.0.0.1"` verified by grep.
  - T-01-06 (Werkzeug debug RCE) — **mitigated**: `debug=False` verified.
  - T-01-07 (ready-file half-write) — **mitigated**: `os.replace` verified.
  - T-01-08 (probe-timeout process liveness) — **mitigated**: `os._exit(1)` on timeout.
  - T-01-09 (port out-of-range) — **accepted**: argparse `type=int` + OS bind failure is the guardrail.
  - T-01-10 (ready-file ACL) — **accepted**: user-private temp dirs.

No new security-relevant surface introduced beyond what the threat model already declared.
