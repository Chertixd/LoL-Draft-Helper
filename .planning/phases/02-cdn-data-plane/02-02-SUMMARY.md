---
phase: 02-cdn-data-plane
plan: 02
subsystem: cdn-data-plane/server-side-export
tags:
  - python
  - supabase
  - json-export
  - sha256
  - etl
  - tdd
requirements:
  - CDN-05
dependency-graph:
  requires: []
  provides:
    - "Daily Supabase -> JSON exporter (supabase-dataset-updater/scripts/export_to_json.py)"
    - "Canonical sha256 envelope contract shared with Plan 02-01 (json_repo.py)"
    - "requirements-dev.txt for future CI wiring (Plan 02-03)"
  affects:
    - "Plan 02-01 (json_repo.py) — MUST use identical canonical sha256 form (orchestrator critical invariant #3)"
    - "Plan 02-03 (GitHub Actions wiring) — will run this script after the TS ETL step"
tech-stack:
  added:
    - "Python 3.12 (dev/CI only; NOT bundled into the .exe)"
    - "supabase-py >= 2.4.0 (dev/CI only)"
    - "python-dotenv (dev/CI only)"
    - "pytest (dev/CI only)"
  patterns:
    - "Canonical JSON sha256 (sort_keys=True, separators=(',', ':'))"
    - "Supabase .range(start, end) pagination with short-page end detection"
    - "Atomic tmp-file + os.replace writes"
    - "argparse CLI with typed Path defaults"
    - "unittest.mock-based client shimming (no live network)"
    - "TDD RED->GREEN discipline with failing-collection sentinel"
key-files:
  created:
    - "supabase-dataset-updater/scripts/__init__.py"
    - "supabase-dataset-updater/scripts/export_to_json.py"
    - "supabase-dataset-updater/scripts/test_export_to_json.py"
    - "supabase-dataset-updater/requirements-dev.txt"
  modified:
    - "supabase-dataset-updater/.gitignore (added __pycache__, .pytest_cache, public/)"
decisions:
  - "Shipped with all 9 tables (champion_stats, champion_stats_by_role, matchups, synergies, items, runes, summoner_spells, champions, patches). Runtime champion_stats schema verification was SKIPPED — no .env present in the worktree; defaulted to the conservative path per the plan's decision tree. If a later run confirms 'name' is already on champion_stats, 'champions' can be elided from TABLES."
  - "Canonical sha256 form pinned to json.dumps(rows, sort_keys=True, separators=(',', ':'), default=_json_default).encode('utf-8'). Plan 02-01's json_repo.py MUST use byte-identical form."
  - "_json_default handles Decimal (-> str, lossless), UUID (-> str), datetime (-> isoformat). Anything else raises TypeError with a diagnostic message (not silenced) so Pitfall #1 surfaces loud on CI."
  - "Exit code 1 on any single-table failure (D-08). Partial files on disk before the failing table are tolerated; CI-level atomicity is Plan 02-03's peaceiris/actions-gh-pages@v4 publish-step responsibility."
  - "main(argv=None) returns int, not sys.exit. __main__ wraps with sys.exit(main()). Eased testability — no SystemExit gymnastics in the failing-table test."
  - "T-02-11 mitigation: str(exc) is redacted for the configured SUPABASE_URL before going to stderr. Service-role key is never touched by log paths."
  - "pytest, supabase>=2.4.0, and python-dotenv all live in requirements-dev.txt. Plan 02-03's workflow will install these ad-hoc in the CI runner. Runtime bundle is unaffected."
metrics:
  duration: "~35 minutes"
  completed: "2026-04-14"
  tasks-executed: 2
  tests-passing: "8/8"
  files-created: 4
  files-modified: 1
  lines-added: 386
---

# Phase 02 Plan 02: Server-Side JSON Exporter Summary

Shipped `supabase-dataset-updater/scripts/export_to_json.py`, a 180-LoC Python daily exporter that reads all 9 Supabase tables via the service-role key and writes `<out-dir>/<table>.json` files with a canonical `__meta` envelope consumed by Plan 02-01's `json_repo.py`. The canonical sha256 form is pinned to `json.dumps(rows, sort_keys=True, separators=(',', ':'), default=_json_default)` — identical byte-for-byte to Plan 02-01's verifier, enforcing the orchestrator critical invariant. Ships with 8 pytest unit tests (envelope shape, canonical sha256 form, Decimal/UUID/datetime serialization, pagination end-detection, single-page fast-path, atomic write, any-single-table-failure-aborts, end-to-end nine-table round-trip); all 8 pass.

## What Shipped

### supabase-dataset-updater/scripts/export_to_json.py

Daily Supabase -> JSON exporter. Structure:

- **Constants:** `SCHEMA_VERSION = 1`, `PAGE_SIZE = 1000`, `TABLES` (9-entry tuple).
- **Helpers:**
  - `_json_default(obj)` — Decimal/UUID/datetime -> str/str/isoformat. Unknown type -> TypeError.
  - `_canonical_rows_sha256(rows)` — canonical-form sha256 hex digest (the invariant #3 contract).
  - `_fetch_table(client, table)` — paginated `.range(start, end)` loop, stops on short page.
  - `_atomic_write_json(path, payload)` — tmp + os.replace (Pattern 2).
  - `export_table(client, out_dir, table)` — builds envelope, atomic-writes to `<out>/<table>.json`.
- **Entry:** `main(argv=None) -> int` with argparse `--out-dir` (default `./public/data`), reads SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (friendly error on KeyError), loops over TABLES with try/except -> returns 1 on any failure. `__main__` wraps with `sys.exit(main())`.

### supabase-dataset-updater/scripts/test_export_to_json.py

8 pytest tests using stdlib `unittest.mock` (no `responses`, no `httpx_mock`, no live network). A helper factory `_make_mock_client(rows_by_table)` builds a `MagicMock` whose `.table(name).select("*").range(s, e).execute().data` returns the correct slice from `rows_by_table[name]`.

### supabase-dataset-updater/scripts/\_\_init\_\_.py

Empty marker so pytest discovers the test module as `scripts.export_to_json`.

### supabase-dataset-updater/requirements-dev.txt

Three lines: `pytest`, `supabase>=2.4.0`, `python-dotenv`. Plan 02-03 will install these in the CI runner.

### supabase-dataset-updater/.gitignore

Added `__pycache__/`, `*.pyc`, `.pytest_cache/`, `public/` (the local export target).

## Key Decisions Made During Execution

### champion_stats schema verification: SKIPPED, defaulted to 9 tables

The plan's Task 1 step 0 required a runtime query of Supabase to determine whether `champion_stats` rows carry a `name` column. The worktree has no `.env` file (and no live Supabase creds are configured), so per the plan's decision tree, the script defaults to the **conservative 9-table path**:

```
champion_stats, champion_stats_by_role, matchups, synergies,
items, runes, summoner_spells, champions, patches
```

The inclusion of `champions` is the conservative choice: if the verification later confirms `name` is already on `champion_stats`, `champions` can be dropped from `TABLES` and Plan 02-01's `json_repo._champion_map` simplified. This is recorded inline in the script docstring and flagged for Plan 02-01 follow-up.

### Extra test: single-page fast-path

Added `test_pagination_single_page_under_limit` — the plan spec calls for 7 tests but doesn't exercise the short-first-page case (N rows where N < PAGE_SIZE). That path is the most-likely production behavior for small tables (`patches`, `items`, `summoner_spells`, `champions`) so coverage is worth the 8 LoC.

### Exception redaction on stderr

`supabase-py` exceptions can include the Supabase project URL in their string representation. T-02-11 in the threat register calls for a mitigation; the implementation replaces any occurrence of `SUPABASE_URL` in `str(exc)` with `<redacted>` before stderr. The service-role key is never passed to any log path.

## TDD Flow

**RED phase (commit `e5e4de1`):** wrote `test_export_to_json.py` importing `from scripts import export_to_json`. Ran `pytest --collect-only` — confirmed collection fails with `ImportError: cannot import name 'export_to_json' from 'scripts'`. The failure is deterministic and points at exactly the module the next commit creates.

**GREEN phase (commit `5a7f477`):** wrote `export_to_json.py` per the RESEARCH Pattern 3 skeleton + plan adjustments. Ran `pytest scripts/test_export_to_json.py -v` — 8/8 pass in 0.85 s.

No REFACTOR commit needed; the skeleton was sized correctly first time.

## Verification Results

| Check                                                                          | Result                                                                                                                 |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `pytest scripts/test_export_to_json.py -v`                                     | 8 passed, 0 failed, 0.85 s                                                                                             |
| `python -c "import ast; ast.parse(...)"`                                       | exit 0 (syntax OK)                                                                                                     |
| `python scripts/export_to_json.py --help` (no creds)                           | exit 0, prints `--out-dir` flag                                                                                        |
| `grep 'sort_keys=True' ... 'separators=(",", ":")'`                            | 1 hit in `_canonical_rows_sha256` (multiline)                                                                          |
| `grep 'os.replace('`                                                           | 1 hit in `_atomic_write_json`                                                                                          |
| `grep 'load_dotenv()'`                                                         | 1 hit in `main`                                                                                                        |
| `grep 'SUPABASE_URL' + 'SUPABASE_SERVICE_ROLE_KEY'`                            | 2 hits (env lookups only; no `print.*SUPABASE_*` anywhere)                                                             |
| `grep 'print.*SUPABASE'`                                                       | 0 hits (no credential leak patterns)                                                                                   |
| `grep 'TABLES = ('`                                                            | 1 hit; all 9 names present                                                                                             |
| `grep 'def _json_default'` + `isinstance(obj, (Decimal\|UUID\|datetime))`      | 3 isinstance branches                                                                                                  |
| `git diff --name-only HEAD~2 HEAD`                                             | 5 files, all under `supabase-dataset-updater/`                                                                         |
| `grep 'scripts/export_to_json' supabase-dataset-updater/.github/`              | 0 hits (no consumer wiring — Plan 02-03's job)                                                                         |

## Deviations from Plan

### Auto-fixed Issues

**None in the Rule 1/2/3 sense.** The plan was executed as written. Two minor additions documented below for transparency:

**1. Added `test_pagination_single_page_under_limit` (1 extra test above the 7 spec'd)**

- **Found during:** Task 1 (writing the test file)
- **Rationale:** Production tables like `patches` + `items` are well under PAGE_SIZE; the plan spec covered only the multi-page case. Added an 8th test that asserts a single short page returns immediately with `client.table.call_count == 1`. Pure additive; does not change any existing assertion.
- **Files modified:** `supabase-dataset-updater/scripts/test_export_to_json.py`
- **Commit:** `e5e4de1`

**2. Added `.gitignore` entries for `__pycache__/`, `.pytest_cache/`, `public/`**

- **Found during:** Task 2 (first `git status` after running pytest)
- **Rationale:** Running pytest creates `__pycache__` + `.pytest_cache` siblings; the default `--out-dir` is `./public/data` which would pollute the tree on a local dev run. Generic Python-project ignore patterns; no surprise.
- **Files modified:** `supabase-dataset-updater/.gitignore`
- **Commit:** `5a7f477`

### Runtime verification path NOT exercised

The plan's Task 1 step 0 asked for a live Supabase query to determine whether to drop `champions` from TABLES. The worktree has no credentials, so the decision-tree's fallback ("default to all 9 tables") was taken. This is the plan-sanctioned path; not a deviation.

## Authentication Gates

None encountered. The tests use `unittest.mock` shims; no live network calls or credential requirements. The `--help` smoke test passes without creds.

## Known Stubs

None. Every function is wired end-to-end: tests exercise the full path from mock Supabase client through envelope construction to on-disk JSON. The script is production-ready; it's just not yet invoked by CI (that's Plan 02-03).

## Threat Flags

None. The threat register's entries (T-02-11 through T-02-16) are either mitigated in this plan (T-02-11 redaction, T-02-12 invariant test, T-02-16 Decimal -> str) or accepted by the plan (T-02-13 DoS, T-02-15 injection surface is zero — TABLES is a hardcoded tuple). No new surface was introduced beyond what the plan's threat model already anticipates.

## Out-of-Scope Discoveries

None. No deferred items logged. Nothing in the repo needed cleanup or spillover work.

## Follow-ups for Future Plans

1. **Plan 02-01 (json_repo.py):** MUST use the identical canonical sha256 form — `json.dumps(rows, sort_keys=True, separators=(',', ':'), default=<callable>)`. The default callable should also handle Decimal/UUID/datetime identically or strings-on-strings comparisons will miss. A future cross-file integration test (Plan 02-04 end-to-end) should round-trip a fixture through both modules and assert the hashes match.

2. **Plan 02-01 (json_repo._champion_map):** If/when `champion_stats.name` is verified present on Supabase, `champions` can drop out of TABLES here and `_champion_map` can derive names from `champion_stats` rows (saves one CDN fetch per startup).

3. **Plan 02-03 (GitHub Actions wiring):**
   - Install `supabase-dataset-updater/requirements-dev.txt` with `pip install -r supabase-dataset-updater/requirements-dev.txt` (or the subset `supabase>=2.4.0 python-dotenv` — pytest is optional in CI).
   - Run `cd supabase-dataset-updater && python scripts/export_to_json.py --out-dir ./public/data`.
   - Then publish `./supabase-dataset-updater/public` via `peaceiris/actions-gh-pages@v4` with `force_orphan: true`. The publish step is the atomicity enforcer (D-08 completes here).

## Self-Check: PASSED

**Files created/modified verified present:**

- FOUND: `supabase-dataset-updater/scripts/__init__.py`
- FOUND: `supabase-dataset-updater/scripts/export_to_json.py`
- FOUND: `supabase-dataset-updater/scripts/test_export_to_json.py`
- FOUND: `supabase-dataset-updater/requirements-dev.txt`
- FOUND: `supabase-dataset-updater/.gitignore` (modified)

**Commits verified:**

- FOUND: `e5e4de1` — `test(02-02): add export_to_json unit tests + requirements-dev (RED phase)`
- FOUND: `5a7f477` — `feat(02-02): implement export_to_json.py with canonical sha256 envelope (GREEN phase)`

**Tests verified:**

- 8/8 passing (`pytest scripts/test_export_to_json.py -v` — 0.85s)

**Acceptance criteria verified:** see Verification Results table above — every grep + behavior check satisfied.
