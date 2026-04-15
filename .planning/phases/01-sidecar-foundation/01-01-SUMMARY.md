---
phase: 01-sidecar-foundation
plan: 01
subsystem: packaging
tags:
  - pyinstaller
  - python
  - packaging
  - platformdirs
  - certifi

requires:
  - phase: 00-research
    provides: "PyInstaller 6.19.0 spec patterns, hidden-import seed list, supabase exclude rationale, platformdirs 4.x API with ensure_exists=True, certifi bundling pattern (#7229), Pitfall #2 UPX, Pitfall #6 __file__/_MEIPASS"
provides:
  - "lolalytics_api.resources module exporting LOL_DRAFT_APP_NAME, bundled_resource(), user_cache_dir(), user_log_dir(), user_data_dir() — installed via the existing editable package"
  - "backend.spec PyInstaller recipe (onefile, upx=False, certifi bundled, supabase family excluded, hidden-imports seeded, pathex=[] for editable-install layout)"
  - "platformdirs>=4.0.0 pinned in apps/backend/requirements.txt"
  - "apps/backend/.gitignore covering PyInstaller output (dist/, build/) and spec backups"
affects:
  - 01-02  # backend.py main() rewrite — imports from lolalytics_api.resources
  - 01-03  # CI smoke test — runs `pyinstaller --clean --noconfirm backend.spec`
  - 02-*   # CDN data plane — json_repo.py will use user_cache_dir() at runtime
  - 03-*   # Tauri host — sidecar build pipeline consumes backend-x86_64-pc-windows-msvc.exe

tech-stack:
  added:
    - platformdirs>=4.0.0  # cross-platform user dir resolution with ensure_exists=True
  patterns:
    - "Canonical frozen-mode detection: getattr(sys, 'frozen', False) AND hasattr(sys, '_MEIPASS') — belt-and-suspenders vs cx_Freeze/py2exe false positives"
    - "Three-function path split (user_cache_dir / user_log_dir / user_data_dir) over a single kind=-dispatched helper — reads and greps more clearly at call sites"
    - "PyInstaller spec pathex=[] with editable-install layout — resolves lolalytics_api via site-packages entry only, avoiding dual-resolution ambiguity in frozen mode"
    - "Explicit hidden-imports for new package submodules (lolalytics_api, lolalytics_api.resources) alongside collect_submodules reliance — documented intent that survives module-loader edge cases"

key-files:
  created:
    - counterpick-app/apps/backend/src/lolalytics_api/resources.py
    - counterpick-app/apps/backend/backend.spec
    - counterpick-app/apps/backend/.gitignore
  modified:
    - counterpick-app/apps/backend/requirements.txt

key-decisions:
  - "Placed resources.py inside the existing lolalytics_api package (src/lolalytics_api/resources.py) rather than as a sibling at src/resources.py — the CONTEXT D-13 wording allowed either; the package-internal path leverages the already-installed editable package and gives a stable, grep-able import path (lolalytics_api.resources) without touching the package-discovery config."
  - "Chose three named functions (user_cache_dir / user_log_dir / user_data_dir) over a single kind=-dispatched helper per CONTEXT §Claude's Discretion bullet 3 — call sites become self-documenting and greppable."
  - "Locked pathex=[] in backend.spec per PLAN (B-1 revision) — editable install resolves lolalytics_api via site-packages; pathex=['src'] would create dual-resolution ambiguity that breaks in frozen mode."
  - "Added explicit 'lolalytics_api' and 'lolalytics_api.resources' hidden-imports alongside the existing collect_submodules('websocket') pattern — explicit > implicit in the spec."
  - "Kept supabase>=2.4.0 in requirements.txt (D-19, N-03) — Phase 1 only excludes it from the PyInstaller bundle; dev-mode Supabase access remains functional until Phase 2's json_repo.py lands."

patterns-established:
  - "resources.py canonical import: `from lolalytics_api.resources import bundled_resource, user_cache_dir, user_log_dir, user_data_dir, LOL_DRAFT_APP_NAME` — all downstream code (Plan 02's backend.py, Phase 2's json_repo.py) MUST import from here; grep-enforced migration (D-14) begins Plan 02."
  - "PyInstaller spec comment convention: pathex rationale, hidden-imports origin, excludes grouping (supabase / async-mode / stdlib), and UPX criticality are all inline — spec discoveries belong in the spec, not in CLI flags."
  - "backend.spec hidden-imports discovery list: commented-out entries (engineio.async_drivers, engineio, socketio, flask_socketio, dns) document iterative expansion path for Plan 03 CI failures."

requirements-completed:
  - SIDE-03
  - SIDE-05

# Metrics
duration: 15min
completed: 2026-04-14
---

# Phase 1 Plan 01: Sidecar Foundation Artifacts Summary

**Delivered the two foundation files Phase 1 depends on — `lolalytics_api.resources` path helper module and the PyInstaller `backend.spec` recipe — plus the `platformdirs` pin and `.gitignore` hygiene that unblock Plan 02 (backend.py main() rewrite) and Plan 03 (CI smoke build).**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-14T14:45:00Z
- **Completed:** 2026-04-14T15:00:00Z
- **Tasks:** 2
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments

- `lolalytics_api.resources` submodule lands inside the existing editable package, giving every downstream caller a single canonical import path for both bundled (`bundled_resource`) and user-writable (`user_cache_dir`, `user_log_dir`, `user_data_dir`) paths — closes the `__file__`/`cwd()` escape hatch that Plan 02's grep guard will enforce across `backend.py`.
- `backend.spec` locks the full PyInstaller contract: `upx=False`, supabase family excluded, `certifi.where()` bundled via `datas`, hidden-imports seeded with `engineio.async_drivers.threading` + `httpx.socks` + `collect_submodules('websocket')` + explicit `lolalytics_api.resources`, onefile EXE named `backend-x86_64-pc-windows-msvc` for Tauri's externalBin convention, `pathex=[]` per the editable-install layout (B-1 revision).
- `platformdirs>=4.0.0` pinned, `.gitignore` written once so future plans do not re-check.

## Task Commits

Each task was committed atomically (parallel-executor `--no-verify` to avoid hook contention with sibling agents; orchestrator validates hooks after wave completion):

1. **Task 1: Create resources.py helper module and add platformdirs to requirements** — `1f882ab` (feat)
2. **Task 2: Create backend.spec PyInstaller recipe** — `9470f33` (feat)

## Resources Helper Module Shape

**Path:** `counterpick-app/apps/backend/src/lolalytics_api/resources.py`
**Canonical import:** `from lolalytics_api.resources import ...`
**Precondition:** `pip install -e .` from `counterpick-app/apps/backend/` (already the established workflow via `start.ps1` line 78).

**Public surface:**

| Symbol | Signature | Behaviour |
|--------|-----------|-----------|
| `LOL_DRAFT_APP_NAME` | `str = "lol-draft-analyzer"` | Mutable placeholder per D-15; Phase 3 (TAURI-01) swaps for the finalized Tauri identifier. Imported from here — never inlined. |
| `bundled_resource(relative_path: str)` | `-> Path` | Frozen: `Path(sys._MEIPASS) / relative_path`. Dev: walks three `.parent` steps (`resources.py` → `lolalytics_api/` → `src/` → `apps/backend/`) to match the `_MEIPASS` layout created by `datas=[(certifi.where(), 'certifi')]`. Never raises; caller verifies existence. |
| `user_cache_dir()` | `-> Path` | `platformdirs.user_cache_dir(LOL_DRAFT_APP_NAME, ensure_exists=True)` wrapped in `Path`. Windows: `%LOCALAPPDATA%\lol-draft-analyzer\Cache`. |
| `user_log_dir()` | `-> Path` | Same pattern, `user_log_dir`. Windows: `%LOCALAPPDATA%\lol-draft-analyzer\Logs`. |
| `user_data_dir()` | `-> Path` | Same pattern, `user_data_dir`. Windows: `%APPDATA%\lol-draft-analyzer`. |

**Private helper:** `_is_frozen()` — returns `getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")`. Both checks mandatory because cx_Freeze / py2exe set `sys.frozen` without `_MEIPASS`; the two-attribute idiom is the canonical PyInstaller runtime-information contract.

**Module imports:** `from __future__ import annotations`, `os`, `sys`, `pathlib.Path`, `platformdirs` — nothing else.

## backend.spec Summary

**Path:** `counterpick-app/apps/backend/backend.spec`
**Build:** `pyinstaller --clean --noconfirm apps/backend/backend.spec`
**Target artifact:** `dist/backend-x86_64-pc-windows-msvc.exe` (Tauri externalBin triple).

**Analysis-block essentials:**

- `scripts=['backend.py']`
- `pathex=[]` — editable-install resolution via site-packages only. **Not** `['src']`; that would dual-resolve in frozen mode.
- `datas=[(certifi.where(), 'certifi')]` — drops the CA bundle into `_MEIPASS/certifi/`. `SSL_CERT_FILE` is set at runtime by Plan 02.
- `hiddenimports` (8 entries plus `collect_submodules('websocket')` expansion):
  - `engineio.async_drivers.threading` — Flask-SocketIO #259
  - `httpx.socks` — conditional dep
  - `*collect_submodules('websocket')` — websocket-client lazy-loaded protocol handlers
  - `charset_normalizer`, `urllib3`, `certifi` — requests trim-out guards
  - `lolalytics_api`, `lolalytics_api.resources` — Phase 1 additions, belt-and-suspenders over package auto-collection
  - Commented discovery list (`engineio.async_drivers`, `engineio`, `socketio`, `flask_socketio`, `dns`) left in place for iterative Plan 03 CI expansion.
- `excludes` (10 entries):
  - Supabase family (credential leak mitigation): `supabase`, `gotrue`, `postgrest`, `realtime`, `storage3`, `supabase_functions`, `supabase_auth`
  - async_mode alternatives (locked at `threading`): `eventlet`, `gevent`
  - Dead stdlib weight: `tkinter`

**EXE-block essentials:**

- `name='backend-x86_64-pc-windows-msvc'`
- `upx=False` — CRITICAL (Pitfall #2). Plan 03 CI grep guard enforces.
- `console=False` — no terminal flash on sidecar spawn.
- No `COLLECT` block — onefile.

## Discretionary Choices Logged

- **File location:** `src/lolalytics_api/resources.py` (package-internal) over `src/resources.py` (sibling). Both were permitted by CONTEXT D-13; the package-internal path leverages the existing editable-install surface and yields the cleaner `lolalytics_api.resources` import path.
- **Three-function split** over single `kind=`-dispatched helper, per CONTEXT §Claude's Discretion bullet 3.
- **Header comment phrasing in backend.spec** avoids the literal string `pathex=['src']` so the Plan 03 CI regex guard `pathex\s*=\s*\['src'\]` cannot false-positive on the documentation itself (the comment conveys the same intent in prose).

## .gitignore Entries Added

First-time creation of `counterpick-app/apps/backend/.gitignore` with:

- `dist/` and `build/` — PyInstaller output directories
- `*.spec.bak` — spec backups
- `__pycache__/` and `*.pyc` — Python bytecode caches

Plan 03 does not need to re-check these.

## Deviations from Plan

None. The plan executed exactly as written with one trivial spec-comment rewording (Task 2) to keep the Plan 03 CI regex guard happy against the documentation itself — this is a prose refactor, not a semantic change.

## Verification Evidence

All automated checks from the plan's `<verification>` block pass on the development environment:

- `python -c "from lolalytics_api.resources import ..."` — imports succeed, `LOL_DRAFT_APP_NAME == 'lol-draft-analyzer'`, cache / log / data dirs created at `C:\Users\till-\AppData\Local\lol-draft-analyzer\{Cache,Logs}` and `%APPDATA%\lol-draft-analyzer`.
- `python -c "import ast; ast.parse(open('backend.spec').read())"` — spec parses as valid Python.
- Regex guards: `pathex=['src']` absent; `pathex=[]` present; `upx=True` absent; supabase family + hidden-imports seed + binary name all present.
- `requirements.txt`: `platformdirs>=4.0.0` pinned; `supabase>=2.4.0` intact (D-19 invariant).
- `.gitignore`: `dist/` and `build/` both present.

## Self-Check: PASSED

- `counterpick-app/apps/backend/src/lolalytics_api/resources.py` — FOUND
- `counterpick-app/apps/backend/backend.spec` — FOUND
- `counterpick-app/apps/backend/.gitignore` — FOUND
- `counterpick-app/apps/backend/requirements.txt` — MODIFIED (platformdirs pinned, supabase retained)
- Commit `1f882ab` (Task 1) — FOUND in `git log`
- Commit `9470f33` (Task 2) — FOUND in `git log`

No stubs introduced (no placeholder text, no hardcoded empty defaults flowing to UI). No new threat surface beyond what Phase 1's `<threat_model>` declares — supabase exclusion (T-01-01), UPX lock (T-01-02), cert staleness accept (T-01-03), and path-resolution clarity (T-01-04) are all addressed at the spec / module level as planned.
