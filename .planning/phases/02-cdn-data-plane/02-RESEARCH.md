# Phase 2: CDN Data Plane — Research

**Researched:** 2026-04-14
**Domain:** GitHub Pages CDN + conditional-GET local cache + Supabase → JSON export, on top of Phase 1's frozen-Python sidecar
**Confidence:** HIGH (all major components verified against existing source, official docs, or CONTEXT.md locked decisions)

## Summary

Phase 2 has two cleanly separable workstreams — server-side `export_to_json.py` (~150 LoC, runs in CI) and client-side `json_repo.py` (~250 LoC, runs in the frozen sidecar). The 30 locked decisions in CONTEXT.md fix nearly every stack, layout, and policy choice; this research provides concrete how-to for the remaining mechanics: Supabase pagination, atomic writes, conditional-GET interaction with GitHub Pages' Fastly edge, the Decimal/UUID JSON-serialization quirks the export script will hit, the `peaceiris/actions-gh-pages@v4` YAML, and the contract-test pattern that proves `supabase_repo` and `json_repo` return identical data.

The single most important sequencing risk is the `backend.py` import swap interacting with the `requirements.txt` removal of `supabase` and the `backend.spec` excludes restoration: at every intermediate commit the frozen `.exe` must still build (Phase 1 commit `451e8f7` is the cautionary tale — flipping any one of the three out of order broke the bundle). The plan must order the cutover as **(1) land `json_repo.py` and contract tests with no consumer, (2) flip `backend.py` import block, (3) remove `supabase` from `requirements.txt` and re-add the excludes to `backend.spec`, (4) re-enable the CI guard** — and validate in-between.

**Primary recommendation:** Author `json_repo.py` and `export_to_json.py` in parallel against a hand-crafted JSON fixture; defer the `backend.py` cutover to a single atomic commit that pairs the import swap with the spec/requirements/CI changes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Server-Side Export:**

- **D-01:** New script at `supabase-dataset-updater/scripts/export_to_json.py`. Python (not Node), same language as `backend.py` — shared mental model and easier contract parity with `json_repo.py`. Runtime depends on `supabase-py`, `python-dotenv`, stdlib `json`, stdlib `hashlib`. _[auto: Python parity with the consumer side is worth one more dependency in the ETL runner]_
- **D-02:** Export step is **appended to the existing** `supabase-dataset-updater/.github/workflows/update-dataset.yml` daily workflow — NOT a separate workflow. A single CI run does ETL → JSON export, which guarantees the CDN never lags the DB by more than a few minutes. _[auto: spec §6.2 intent; single failure mode is easier to reason about]_
- **D-03:** Target branch: orphan `gh-pages`. Each export rewrites the branch history via force-push (the branch is a content snapshot, not source code). `gh-pages` is independent of `main` so rollback is `git push --force origin <old-sha>:gh-pages`. _[auto: standard GitHub Pages pattern; preserves clean `main` history]_
- **D-04:** Tables to export: seed list from spec §6.2 = `champion_stats`, `champion_stats_by_role`, `matchups`, `synergies`, `items`, `runes`, `summoner_spells`. Actual list verified at implementation time by querying Supabase information_schema; any additions are logged in PLAN.md. _[auto: exact table list from spec §6.2]_
- **D-05:** JSON envelope per file (single top-level object): `{"__meta": {"exported_at": "<iso8601Z>", "sha256": "<hex>", "row_count": <int>, "schema_version": 1}, "rows": [...]}`. Downstream `json_repo.py` returns `body["rows"]` (matching `supabase_repo`'s return shape). `__meta.sha256` is computed over the canonical JSON serialization of the rows array, without the `__meta` field, so the client can verify integrity. _[auto: fixed schema avoids ambiguity; `schema_version` lets future migrations be explicit]_
- **D-06:** Authentication: `export_to_json.py` uses `SUPABASE_SERVICE_ROLE_KEY` from a GitHub Actions secret. The key never leaves CI; it is not logged. _[auto: standard service-role pattern; already used by the existing ETL]_
- **D-07:** Publish mechanism: the workflow step uses `peaceiris/actions-gh-pages@v4` (or a raw `git` commit + `push --force` flow) to publish `data/<table>.json` to the `gh-pages` branch. The action is well-maintained and widely used; the manual-git fallback is documented for when the action is unavailable. _[auto: action is simpler than inline git]_
- **D-08:** Export script layout: single file, one function per table (`export_champion_stats(client, out_dir)` etc.) orchestrated by a `main()`. ~150 LoC total. Error handling: a single table's failure aborts the entire run — partial CDN updates are not allowed. _[auto: atomic-or-nothing semantics match spec §6]_
- **D-09:** Local testing: the script accepts a `--out-dir` CLI flag (defaults to `./public` relative to repo root) so a developer can run it locally without pushing. Integration test checks the schema of each generated file. _[auto: testability]_

**Client-Side Read Path (`json_repo.py`):**

- **D-10:** Module location: `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` — same package as `supabase_repo.py`. Editable install (Phase 1 D-14) handles it without any pyproject.toml change. _[auto: convention parity with supabase_repo]_
- **D-11:** Public-API contract: mirrors **exactly** the 9 public functions in `supabase_repo.py`:
  - `get_champion_stats(patch=None)`
  - `get_champion_stats_by_role(champion, patch=None, role=None)`
  - `get_matchups(champion, patch=None, role=None, min_games=...)`
  - `get_synergies(champion, patch=None, role=None, min_games=...)`
  - `get_items(patch=None)`
  - `get_runes(patch=None)`
  - `get_summoner_spells(patch=None)`
  - plus helpers: `_wilson_score`, `_normalize_slug`, `_champion_map`, `_get_latest_patch`, `_resolve_champion`, `_determine_role`, `_attach_names`
  Identical signatures. Identical return shapes. A contract test per public function asserts both. _[auto: spec §6.3 — drop-in replacement]_
- **D-12:** Helper-function strategy: the pure helpers (`_wilson_score`, `_normalize_slug`, `_determine_role`, `_attach_names`) are **re-imported from `supabase_repo.py`** to avoid duplication (they don't touch Supabase). The data-access helpers (`_champion_map`, `_get_latest_patch`, `_resolve_champion`) are **reimplemented** because they read from the CDN cache, not Supabase. _[auto: DRY where sensible]_
- **D-13:** Cache location: `resources.user_cache_dir() / "cdn"` — a `cdn/` subdirectory so it doesn't collide with the legacy `cache_data.json` at the same `user_cache_dir()` root. Each table stored as two files: `<table>.json` (the payload) and `<table>.meta.json` (ETag, Last-Modified, fetched_at, sha256). _[auto: clean separation from Phase 1 cache; supports table-level staleness]_
- **D-14:** Cache-busting strategy: **conditional GET only** (If-None-Match + If-Modified-Since). GitHub Pages reliably sets `ETag` and `Last-Modified` on each response. Manifest.json / `?v=<timestamp>` approaches not needed for 7 small JSON files. _[auto: SUMMARY Q6 recommendation; simplest path works]_
- **D-15:** Conditional GET client: hand-written ~30 LoC using stdlib `requests` — not `requests-cache`. The `requests-cache` library pulls SQLite + 3 MB of transitive deps and inflates the AV-fingerprint surface; a manual cache is cheaper. _[auto: STACK.md recommendation — "Do not use requests-cache"]_
- **D-16:** Startup policy: on backend startup, `json_repo` issues one conditional GET per table **concurrently** (via `concurrent.futures.ThreadPoolExecutor(max_workers=7)`) to keep startup fast. A 304 reuses the cache file; a 200 atomically replaces it via `tmp + os.replace`. _[auto: 7 sequential requests can be slow on first run; threaded fan-out is ~1 s vs. ~5 s]_
- **D-17:** Atomic write pattern: write to `<table>.json.tmp` in the same directory, `json.dumps` the new payload, `os.replace(tmp, final)`. Same-volume rename is atomic on Windows and POSIX. Pair-write for the `.meta.json` file uses the same pattern. _[auto: PITFALLS.md cache corruption mitigation]_
- **D-18:** Corrupt-cache recovery: on `json.JSONDecodeError` when reading a cache file, delete the file (and the paired `.meta.json`) and refetch from CDN. No user action required. _[auto: pitfall #18 mitigation]_
- **D-19:** Network-error policy:
  - Reachable CDN + 200 or 304 → normal path.
  - Reachable CDN + 4xx/5xx → raise `CDNError` with upstream status; `backend.py` startup fails loud (Phase 3 UX adds the friendly error banner).
  - Unreachable CDN + cache present → log warning, use cached data, set `stale=True` flag on the table's meta. `/api/health` surfaces `{"cached": {table: stale_bool}}` so Phase 3 can render a staleness indicator. _[auto: spec §6.4 + §7]_
  - Unreachable CDN + no cache → raise `CDNError`. _[auto: first-run offline UX is Phase 3]_
- **D-20:** CDN base URL configuration: a module-level constant `CDN_BASE_URL` with a baked-in default pointing at the concrete GitHub Pages URL (see D-25). Env var `CDN_BASE_URL` can override for local testing. Phase 3's Tauri config will NOT need to inject this — the baked default is correct for production. _[auto: env override for testability; baked default for ship-readiness]_
- **D-21:** Timeout: each HTTP request uses `timeout=(connect=5, read=15)`. Covers typical GitHub Pages latency + a generous read budget for the largest file (matchups, ~800 KB). _[auto: conservative defaults]_

**Backend Cutover (`backend.py` and `backend.spec`):**

- **D-22:** Import swap in `backend.py` (one block, lines 11–21): `from lolalytics_api.supabase_repo import ...` → `from lolalytics_api.json_repo import ...`. All `sb_*` aliases renamed to `json_*` (or kept if semantic). The two lines importing `supabase_client` and `config.get_supabase_url` are removed. _[auto: spec §6.3]_
- **D-23:** Remove `supabase>=2.4.0` from `apps/backend/requirements.txt`. Phase 1 left it intact per N-03; Phase 2's cutover removes it because `json_repo.py` doesn't need it. `supabase_repo.py` stays in source (unused at runtime) for reference + for the contract tests that compare shapes. _[auto: spec §6.5]_
- **D-24:** Re-add to `backend.spec` excludes: `supabase`, `gotrue`, `postgrest`, `realtime`, `storage3`, `supabase_functions`, `supabase_auth`. These were dropped in Phase 1's late fix (`451e8f7`); Phase 2 restores them now that the import is gone. Bundle size shrinks ~5 MB. _[auto: completes the Phase 1 deferred resolution]_
- **D-25:** Re-enable the "Verify supabase NOT in bundle" CI guard in `.github/workflows/build-smoke.yml` (uncomment the block commented out in Phase 1). _[auto: completes the Phase 1 deferred resolution]_

**GitHub Pages Setup (one-time, documented):**

- **D-26:** Concrete CDN URL: **must be finalized before Phase 2 ships**. Placeholder used during planning: `https://{GITHUB_USER}.github.io/{REPO_NAME}/data/`. Implementation plan MUST ask the user for the actual `GITHUB_USER` and `REPO_NAME` (or detect from `git remote -v`) before hardcoding. _[auto: flagged as open question for planner]_
- **D-27:** Branch setup: a new `docs/DATA-PIPELINE.md` documents the one-time `gh-pages` branch bootstrap (`git checkout --orphan gh-pages; git rm -rf .; ...`). After Phase 2 ships, the branch is maintained entirely by CI. _[auto: operator runbook]_
- **D-28:** GitHub Pages configuration: enable Pages with source = `gh-pages` branch, path = `/ (root)`. The `data/<table>.json` files live under `data/` per spec §6.2. This is a manual one-time action — not automatable via CLI without admin token. Documented in `DATA-PIPELINE.md`. _[auto: standard setup]_

**Contract Testing:**

- **D-29:** New test file `counterpick-app/apps/backend/test_json_repo_contract.py`: one test per public function, each running BOTH `supabase_repo.get_X(...)` and `json_repo.get_X(...)` with the same args and asserting deep-equal on the result (modulo ordering for list-of-dicts). Tests require live CDN + live Supabase access, so they run in the daily CI (after the export step lands new data) rather than per-commit. _[auto: spec §9 testing strategy; contract-equivalence is the whole point of the phase]_
- **D-30:** New unit test `test_json_repo_cache.py`: mocked HTTP, covering cache-hit (304), cache-cold (200), corrupt-cache recovery (`json.JSONDecodeError` path), atomic-write (tmp file exists during rename window), concurrent startup fan-out. _[auto: unit-level coverage, no network]_

### Claude's Discretion

- Exact `concurrent.futures.ThreadPoolExecutor` max_workers value (5 vs 7 vs 10).
- Exact column ordering in `peaceiris/actions-gh-pages@v4` parameters.
- Whether to use `requests.Session()` pooling in `json_repo.py` vs. one-off `requests.get`.
- Whether contract tests run every PR or only daily (recommendation: daily due to network dependence).
- Whether `test_json_repo_cache.py` uses `responses` library for HTTP mocking vs. a custom `monkeypatch` shim (planner picks).
- Logging verbosity of cache hit/miss in `json_repo.py` (info-level on cold fetch, debug-level on 304).

### Scope Boundaries / Anti-Decisions

- **N-01:** No Tauri/Rust (Phase 3).
- **N-02:** No frontend changes — `apps/frontend/src/api/*` stays hardcoded to `http://localhost:5000`. Phase 3's `getBackendURL()` handles that.
- **N-03:** No hover-detection work (Phase 3).
- **N-04:** No Tauri updater, `.msi`, release workflow (Phase 4).
- **N-05:** No offline-first-run seed dataset (v1.1). Phase 2 has no first-run-offline UX — if the cache is empty and the CDN is unreachable, the backend fails loud. Phase 3 adds the retry UX.
- **N-06:** No manifest.json or `?v=<ts>` cache-busting (deferred; conditional GET is sufficient).

### Deferred Ideas (OUT OF SCOPE)

- **Seed dataset for offline-first-run** — v1.1.
- **Manifest-based cache-busting** (`manifest.json` with content hashes) — deferred. Conditional GET is sufficient for 7 small files.
- **Query-string cache-busting** (`?v=<exported_at>`) — deferred; same rationale.
- **CDN response signing** — Ed25519 signatures on the JSON envelope so a compromised GitHub account couldn't ship malicious data. Backlog. Currently we trust GitHub + TLS.
- **Moving `supabase_repo.py` out of source** — could be deleted in a later milestone once `json_repo` has been battle-tested. Phase 2 keeps it in source for reference + contract tests.
- **Rearranging `gh-pages` layout to drop the `data/` subfolder** — spec §6.2 pins `data/<table>.json`; not changing without a design discussion.
- **Parallel daily runs of ETL + export on different schedules** — single workflow is simpler for v1.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CDN-01 | `json_repo.py` mirrors public API of `supabase_repo.py` — identical signatures and return shapes for the 9 public functions | "Public API Surface" table below + verbatim function signatures pulled from `supabase_repo.py`; "Code Examples" section provides the skeleton; D-11/D-12 fix the helper strategy. |
| CDN-02 | Fetches from GitHub Pages CDN, caches as `<table>.json` + `<table>.meta.json` in `user_cache_dir()/cdn/` | "Cache Layout" + "Conditional-GET Cache Pattern" code below; D-13 fixes location; Phase 1 `resources.user_cache_dir()` already shipped. |
| CDN-03 | Conditional GET (If-None-Match + If-Modified-Since); 304 reuses cache; 200 atomically replaces via tmp+rename | "Conditional-GET Specifics" section + atomic-write pattern; D-16 (concurrent fan-out) + D-17 (atomic rename) fix the mechanics. |
| CDN-04 | Corrupt cache (JSONDecodeError) auto-deleted and re-fetched | "Corrupt-Cache Recovery" pattern below; D-18 fixes the contract; pitfall #13 root cause documented. |
| CDN-05 | `export_to_json.py` exports tables with `__meta` envelope (`exported_at`, `sha256`); publishes to `gh-pages` | "Export Script Skeleton" section + D-05 envelope format + Decimal/UUID serialization quirks documented. |
| CDN-06 | ETL workflow runs export step after each ETL write — daily refresh | "GitHub Actions Workflow Extension" with full YAML fragment for `peaceiris/actions-gh-pages@v4`; D-02 pins single-workflow design. |
| CDN-07 | GitHub Pages configured to serve `gh-pages` branch at stable public URL, baked into config | "GitHub Pages One-Time Bootstrap" section + D-26/D-27/D-28; the URL is baked into `json_repo.CDN_BASE_URL` (Phase 2) NOT `tauri.conf.json` (Phase 3 doesn't need to know). |
| CDN-08 | `supabase-py` removed from runtime `requirements.txt`; `supabase_repo.py` stays in-repo for ETL/dev use | "Cutover Ordering" section; D-22/D-23/D-24/D-25 fix the four-step sequence; Phase 1 commit `451e8f7` documented as the cautionary tale. |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md is a generated GSD context file mirroring `PROJECT.md` + `STACK.md` + `CONVENTIONS.md` — no project-specific bans beyond what's in the source docs. Relevant directives extracted:

- **GSD workflow:** all file-changing work must enter through a GSD command (`/gsd-execute-phase` for planned phase work). Phase 2 plans MUST be created via `/gsd-plan-phase 2`, executed via `/gsd-execute-phase 2`.
- **Coding conventions (from CONVENTIONS.md):**
  - Python: `snake_case` modules, `snake_case` functions, `UPPER_SNAKE_CASE` constants, `_underscore` for private helpers, 4-space indent, double-quoted docstrings with `:param name:` style.
  - Mixed German/English comments are conventional in this repo — neither is a violation.
  - No structured logging framework; `print()` with `[MODULE_NAME]` prefix is the existing pattern, but Phase 1's `backend.py` rewrite landed proper `logging` with TimedRotatingFileHandler — `json_repo.py` SHOULD use `logging.getLogger(__name__)` to follow the post-Phase-1 convention.
- **Privacy constraint (from PROJECT.md Constraints):** No telemetry, no network calls beyond CDN reads and Riot's own LCU. `json_repo.py` is the only module making CDN calls; do not add any other outbound HTTP.
- **Data-path constraint:** Installed clients never talk to Supabase. After Phase 2 cutover, no Supabase imports may exist on the runtime path of the bundled `.exe`. The CI guard (D-25) enforces this.
- **Minimum-invasive change:** The Flask/Socket.IO code path stays structurally unchanged — Phase 2 swaps ONE import block in `backend.py`. Do not touch route handlers, do not refactor `recommendation_engine`.
- **Windows-only:** `os.replace()` is atomic on Windows since Python 3.3 (relevant for D-17). `concurrent.futures.ThreadPoolExecutor` works on Windows. No Linux-specific code paths needed.

## Standard Stack

### Core (already pinned by Phase 1, no changes)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | `>=2.32` (verified locally: `2.33.1`) | HTTP fetch + conditional GET | Existing dep; stdlib for HTTP; certifi already bundled in Phase 1 spec [VERIFIED: `pip show requests`] |
| `platformdirs` | `>=4.0.0` (verified locally: `4.9.6`) | `user_cache_dir()` for `cdn/` subfolder | Phase 1 D-18 already pinned; `lolalytics_api.resources.user_cache_dir()` already shipped [VERIFIED: `pip show platformdirs`] |
| `json` | stdlib | Envelope parse + serialize | Always [VERIFIED: stdlib] |
| `hashlib` | stdlib | sha256 verification of `__meta.sha256` | Always [VERIFIED: stdlib] |
| `concurrent.futures` | stdlib | `ThreadPoolExecutor` for parallel startup fetch | Always; D-16 [VERIFIED: stdlib] |
| `os` | stdlib | `os.replace()` for atomic cache writes | Always; D-17 [VERIFIED: stdlib] |

### Server-Side Export (`supabase-dataset-updater/scripts/export_to_json.py`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `supabase` | `>=2.4.0` (verified locally: `2.28.3`) | Read tables via service_role key | D-06; same client the existing TS ETL uses, just Python flavor [VERIFIED: `pip show supabase`] |
| `python-dotenv` | already in `requirements.txt` | Read `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` from env in local-dev mode | CI uses real env vars; `.env` for local `--out-dir` runs (D-09) [VERIFIED: existing dep] |
| `decimal` | stdlib | Handle PostgreSQL `numeric` columns surfacing as `Decimal` | Required by `json.dumps` custom encoder pattern (see Pitfall #1) [VERIFIED: stdlib + WebSearch] |
| `uuid` | stdlib | Handle PostgreSQL `uuid` columns surfacing as `UUID` | Same pattern [VERIFIED: stdlib + WebSearch] |

CI runner side: `actions/setup-python@v5` already used by Phase 1's `build-smoke.yml`; reuse the same `python-version: "3.12.x"` for consistency.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `responses` | latest (test-only) | Mock `requests.get` in `test_json_repo_cache.py` | Optional; Claude's discretion bullet 5. Alternative: `unittest.mock.patch('requests.get')` with a custom shim. Recommendation: `responses` because it has first-class support for asserting `If-None-Match` / `If-Modified-Since` headers and returning 304 status. Adds 1 dep to `requirements.txt` (or pyproject `[test]` extras only, not runtime). |
| `pytest` | already in `requirements.txt` | Test framework | Existing; D-29 + D-30 add two new test files. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `requests` + manual ETag cache | `requests-cache` | Rejected by D-15 / STACK.md. `requests-cache` adds ~3 MB + SQLite + transitive deps that bloat the AV-fingerprint surface. Manual cache is ~30 LoC. |
| `peaceiris/actions-gh-pages@v4` | Inline `git commit` + `git push --force` | Both work. The action is one declarative YAML block; the inline approach is ~10 lines of bash. CONTEXT D-07 picked the action; the manual fallback is documented in `DATA-PIPELINE.md` for when the action is unavailable. |
| Per-table file pair (`<t>.json` + `<t>.meta.json`) | Single SQLite cache | Rejected. SQLite would re-introduce the dep-bloat problem D-15 rejects, and per-file is the cache layout the spec §6.4 explicitly calls for. |
| Stdlib `json` with custom encoder | `orjson` | `orjson` natively serializes `UUID`, `datetime`, `Decimal` — but adds a binary wheel and is overkill for ~7 small files exported once a day. Stdlib + 10-line `default=` callable suffices. |
| Service-role key in CI secret | Anon key | Rejected. Some tables may have RLS policies blocking anon reads. Service role bypasses RLS, which is correct because the export script needs every row. Key is a CI secret, never logged. (D-06) |

**Installation:** No `pip install` changes needed for the client side — `requests` and `platformdirs` are already in `requirements.txt`. The export script side will need the existing `requirements.txt` plus `pip install supabase>=2.4.0 python-dotenv` in CI (already pinned). No new test deps unless `responses` is chosen.

**Version verification (performed 2026-04-14):**
```bash
pip show requests       # 2.33.1   [VERIFIED]
pip show supabase       # 2.28.3   [VERIFIED]
pip show platformdirs   # 4.9.6    [VERIFIED]
```

## Architecture Patterns

### Recommended Project Structure

```
counterpick-app/apps/backend/
├── backend.py                                       [MODIFIED: import swap, lines 11-21]
├── backend.spec                                     [MODIFIED: re-add supabase excludes]
├── requirements.txt                                 [MODIFIED: remove supabase>=2.4.0]
├── test_json_repo_cache.py                          [NEW: D-30, mocked HTTP unit tests]
├── test_json_repo_contract.py                       [NEW: D-29, live-CDN+live-Supabase parity]
└── src/lolalytics_api/
    ├── json_repo.py                                 [NEW: ~250 LoC, mirrors supabase_repo public API]
    ├── supabase_repo.py                             [UNCHANGED: stays for contract tests + helper re-import]
    ├── supabase_client.py                           [UNCHANGED: not imported at runtime any more]
    ├── config.py                                    [UNCHANGED: get_supabase_url no longer called at runtime]
    └── resources.py                                 [UNCHANGED: user_cache_dir() consumed]

supabase-dataset-updater/
├── scripts/
│   └── export_to_json.py                            [NEW: ~150 LoC, run by CI after ETL]
└── .github/workflows/
    └── update-dataset.yml                           [MODIFIED: append export+publish step]

.github/workflows/
└── build-smoke.yml                                  [MODIFIED: uncomment "Verify supabase NOT in bundle" guard]

docs/
└── DATA-PIPELINE.md                                 [NEW: one-time gh-pages bootstrap runbook]
```

### Pattern 1: Conditional-GET Cache (the load-bearing pattern)

**What:** Each table is stored as a `<table>.json` body file plus a sibling `<table>.meta.json` ETag/Last-Modified record. Startup issues 7 conditional GETs in parallel; 304 reuses the cached body, 200 atomically replaces it.

**When to use:** Every CDN read in `json_repo`. Single code path; no branching by table.

**Source contract:** verified against `supabase_repo.py` lines 1–444 (9 public functions, 6 helper functions); GitHub Pages ETag/Last-Modified behavior verified per [STACK.md HIGH-confidence section](file:.planning/research/STACK.md) (cross-checked: GitHub Pages docs, MDN HTTP/1.1 conditional requests, RFC 7232).

**Skeleton (annotated for the planner — not for direct copy-paste):**

```python
# counterpick-app/apps/backend/src/lolalytics_api/json_repo.py
"""
CDN-backed read repository. Mirrors the public API of supabase_repo.py exactly.

CONTRACT: All 9 public functions return values structurally identical to the
matching supabase_repo function. Contract-equivalence is asserted by
test_json_repo_contract.py; do not change return shapes here without
updating both modules and the contract test.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# CONTEXT D-12: pure helpers re-imported (they don't touch Supabase).
from lolalytics_api.supabase_repo import (
    _wilson_score,
    _normalize_slug,
    _determine_role as _supabase_determine_role,  # rebound below; see _determine_role()
    _attach_names,
)
from lolalytics_api.resources import user_cache_dir

logger = logging.getLogger(__name__)

# CONTEXT D-20: baked default; env override for local testing.
CDN_BASE_URL = os.environ.get(
    "CDN_BASE_URL",
    "https://{GITHUB_USER}.github.io/{REPO_NAME}/data",  # placeholder per D-26 — open question
)

# CONTEXT D-21: connect=5s, read=15s.
_HTTP_TIMEOUT = (5, 15)
# CONTEXT D-16: max 7 because spec §6.2 lists 7 tables.
_FAN_OUT_MAX_WORKERS = 7

# CONTEXT D-13: cdn/ subdir under user_cache_dir(). Created lazily on first use.
def _cache_dir() -> Path:
    p = user_cache_dir() / "cdn"
    p.mkdir(parents=True, exist_ok=True)
    return p

# CONTEXT D-19: live state — table-name → bool ("did the last fetch use cache because CDN was unreachable?").
_stale_state: Dict[str, bool] = {}
_stale_state_lock = threading.Lock()

class CDNError(RuntimeError):
    """Raised on unrecoverable CDN failure (4xx/5xx, or unreachable + no cache)."""

# In-memory data cache: table → list[dict]. Loaded once at startup, refreshed
# on every conditional-GET 200. Read-only after startup so no per-request lock.
_data: Dict[str, List[Dict[str, Any]]] = {}
_data_lock = threading.Lock()

# ----- low-level fetch + cache primitives (~30 LoC, the load-bearing block) -----

def _atomic_write_json(path: Path, payload: dict | list) -> None:
    """CONTEXT D-17: write to .tmp + os.replace. Atomic on Windows + POSIX."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)

def _load_meta(table: str) -> Optional[dict]:
    meta_path = _cache_dir() / f"{table}.meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # CONTEXT D-18: corrupt meta → delete both, refetch.
        logger.warning("[json_repo] corrupt meta for %s, deleting cache pair", table)
        meta_path.unlink(missing_ok=True)
        (_cache_dir() / f"{table}.json").unlink(missing_ok=True)
        return None

def _load_body(table: str) -> Optional[dict]:
    body_path = _cache_dir() / f"{table}.json"
    if not body_path.exists():
        return None
    try:
        return json.loads(body_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # CONTEXT D-18 (pitfall #13).
        logger.warning("[json_repo] corrupt body for %s, deleting cache pair", table)
        body_path.unlink(missing_ok=True)
        (_cache_dir() / f"{table}.meta.json").unlink(missing_ok=True)
        return None

def _fetch_one(table: str) -> List[Dict[str, Any]]:
    """Conditional-GET one table; return the rows list."""
    url = f"{CDN_BASE_URL}/{table}.json"
    meta = _load_meta(table)
    headers = {}
    if meta:
        if etag := meta.get("etag"):
            headers["If-None-Match"] = etag
        if last_mod := meta.get("last_modified"):
            headers["If-Modified-Since"] = last_mod

    try:
        resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        # CONTEXT D-19: unreachable CDN + cache present → use cache + flag stale.
        body = _load_body(table)
        if body is not None:
            with _stale_state_lock:
                _stale_state[table] = True
            logger.warning("[json_repo] CDN unreachable, using cached %s (stale)", table)
            return body["rows"]
        # No cache → loud failure (Phase 3 wraps in friendly UX).
        raise CDNError(f"CDN unreachable and no cache for {table}: {exc}") from exc

    if resp.status_code == 304:
        body = _load_body(table)
        if body is None:
            # ETag matched but local body vanished — degenerate; force re-fetch.
            logger.warning("[json_repo] 304 but cache missing for %s; refetching", table)
            return _fetch_one_unconditional(table)
        with _stale_state_lock:
            _stale_state[table] = False
        return body["rows"]

    if resp.status_code != 200:
        raise CDNError(f"CDN returned {resp.status_code} for {table}: {resp.text[:200]}")

    body = resp.json()  # body has {"__meta": {...}, "rows": [...]}

    # CONTEXT D-05: schema_version enforcement (see "schema_version handling").
    schema_v = body.get("__meta", {}).get("schema_version")
    if schema_v is None or schema_v > 1:
        raise CDNError(f"Unsupported schema_version={schema_v} for {table}; client supports 1")
    if schema_v < 1:
        logger.warning("[json_repo] %s has older schema_version=%d; proceeding", table, schema_v)

    # CONTEXT D-05: verify __meta.sha256 against canonical(rows).
    expected = body["__meta"].get("sha256")
    actual = hashlib.sha256(
        json.dumps(body["rows"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if expected and expected != actual:
        raise CDNError(f"sha256 mismatch for {table}: expected {expected}, got {actual}")

    # CONTEXT D-17: atomic-write body and meta.
    _atomic_write_json(_cache_dir() / f"{table}.json", body)
    _atomic_write_json(_cache_dir() / f"{table}.meta.json", {
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "fetched_at": resp.headers.get("Date"),
        "sha256": expected,
    })
    with _stale_state_lock:
        _stale_state[table] = False
    logger.info("[json_repo] fetched %s (%d rows)", table, len(body["rows"]))
    return body["rows"]

def _fetch_one_unconditional(table: str) -> List[Dict[str, Any]]:
    """Drop cache + meta, force a 200. Used by the recovery path."""
    (_cache_dir() / f"{table}.json").unlink(missing_ok=True)
    (_cache_dir() / f"{table}.meta.json").unlink(missing_ok=True)
    return _fetch_one(table)

# ----- startup-time fan-out (CONTEXT D-16) -----

# CONTEXT D-04: tables to fetch.
_TABLES = (
    "champion_stats",
    "champion_stats_by_role",
    "matchups",
    "synergies",
    "items",
    "runes",
    "summoner_spells",
)

def warm_cache() -> None:
    """Called from backend.py main() at startup. Fan-out 7 conditional GETs."""
    with ThreadPoolExecutor(max_workers=_FAN_OUT_MAX_WORKERS) as ex:
        future_to_table = {ex.submit(_fetch_one, t): t for t in _TABLES}
        results: Dict[str, List[Dict[str, Any]]] = {}
        for fut in as_completed(future_to_table):
            t = future_to_table[fut]
            results[t] = fut.result()  # propagates CDNError if raised
    with _data_lock:
        _data.update(results)
    logger.info("[json_repo] warm_cache complete; %d tables loaded", len(results))

def stale_status() -> Dict[str, bool]:
    """For backend.py /api/health to surface per-table stale flag (CONTEXT D-19)."""
    with _stale_state_lock:
        return dict(_stale_state)

# ----- public API: 9 functions mirroring supabase_repo.py (CONTEXT D-11) -----

def _table(name: str) -> List[Dict[str, Any]]:
    """Lazy load if warm_cache() wasn't called (e.g. dev mode + first call)."""
    with _data_lock:
        if name in _data:
            return _data[name]
    # Cold path — single fetch, no fan-out.
    rows = _fetch_one(name)
    with _data_lock:
        _data[name] = rows
    return rows

def _champion_map() -> Dict[str, Any]:
    """CONTEXT D-12: reimplemented to read from cache, not Supabase."""
    # supabase_repo._champion_map reads from supabase.table("champions") — but
    # `champions` is NOT in CONTEXT D-04's table list. The implementation MUST
    # derive the slug→key→name map from what IS exported. Recommended source:
    # champion_stats rows (each row has champion_key + the rows are joined to
    # name elsewhere) — but cleaner: add `champions` to the export list as a
    # PLAN.md addendum if validation finds it's needed. (See "Open Questions".)
    raise NotImplementedError("see Open Question #1: champions table source")

def _get_latest_patch(fallback: Optional[str] = None) -> str:
    """CONTEXT D-12: reimplemented from cache. Source: derive from any rows[].patch."""
    # supabase_repo reads from `patches` table (not in D-04 list). Recommended:
    # use champion_stats rows[].patch via max() — every row carries patch.
    rows = _table("champion_stats")
    if not rows:
        if fallback:
            return fallback
        raise RuntimeError("No patch found in CDN data.")
    return max(r["patch"] for r in rows)

def _resolve_champion(champion: str) -> Tuple[str, str]:
    """CONTEXT D-12: reimplemented. Same algorithm as supabase_repo._resolve_champion."""
    maps = _champion_map()  # see Open Question #1
    slug_map = maps["slug_map"]
    key_to_name = maps["key_to_name"]
    slug = _normalize_slug(champion)
    if slug in slug_map:
        return slug_map[slug]
    if champion in key_to_name:
        return champion, key_to_name[champion]
    raise ValueError(f"Champion '{champion}' not found in CDN data.")

def _determine_role(champion_key: str, patch: str, requested_role: Optional[str]) -> str:
    """CONTEXT D-12: reimplemented. Picks the most-played role from cache."""
    if requested_role:
        return requested_role
    rows = [
        r for r in _table("champion_stats")
        if r["patch"] == patch and r["champion_key"] == champion_key
    ]
    if not rows:
        raise ValueError(f"No stats for champion {champion_key} and patch {patch}.")
    rows.sort(key=lambda r: r.get("games", 0) or 0, reverse=True)
    return rows[0]["role"]

# ----- the 9 public functions follow the same shape:
#       1. _get_latest_patch / _resolve_champion / _determine_role
#       2. filter _table(<name>) by patch + champion_key + role
#       3. compute the same wilson scores / deltas / sorts that supabase_repo does
#       4. _attach_names() and return
#
# The contract test (test_json_repo_contract.py) asserts that for the same
# inputs the return value is deeply equal to supabase_repo.<same>(...). Build
# each function by copy-modifying the supabase_repo equivalent — replacing
# every `supabase.table(...).select(...)...execute().data` call with
# `[r for r in _table("<name>") if <where-clause>]`. The post-processing (
# wilson, delta, normalized_delta, attach_names) is identical and can be
# copied verbatim because the helpers are imported.
```

**Implementation note for the planner:** the public-function block below `_determine_role` is ~150–200 LoC and mirrors `supabase_repo.py` lines 108–439 line-for-line. Each function:

1. Calls `_get_latest_patch()` if `patch is None`.
2. Calls `_resolve_champion(champion)` if `champion` arg present.
3. Calls `_determine_role(champion_key, patch, role)` if `role` arg present.
4. Replaces every `supabase.table("X").select(...).eq(...).execute().data` with a list-comp filter over `_table("X")`.
5. Runs identical post-processing (wilson, delta, normalized_delta, sort, slice, attach_names).
6. Returns the same dict shape.

### Pattern 2: Atomic Write (D-17)

**What:** Write payload to `<final>.tmp` in the same directory, then `os.replace(tmp, final)`. Same-volume rename is atomic on Windows NTFS (Python 3.3+) and on POSIX.

**Why this matters:** Power loss between `write` and rename leaves the `.tmp` file dangling, but the canonical `<final>` is either fully old or fully new — never half-written. Pitfall #13 root cause is `cache_file.write_text(json.dumps(...))` without atomicity, which leaves a truncated file on the next read.

**Code:** see `_atomic_write_json` in the skeleton above (5 lines). Same pattern Phase 1's `backend.py` already uses for the ready-file write — `_atomic_write_ready_file` in `backend.py` is the template (Phase 1 Plan 02 commit `c7c0ab2`).

### Pattern 3: Server-Side Export Script (D-01, D-08)

**What:** ~150 LoC Python script: connect to Supabase via service-role key → for each table, paginate via `.range(start, end)` → assemble `{"__meta": {...}, "rows": [...]}` envelope → atomic-write to `<out_dir>/data/<table>.json`.

**Skeleton (annotated for the planner):**

```python
# supabase-dataset-updater/scripts/export_to_json.py
"""
Daily Supabase → JSON exporter. Reads service-role key from env. Writes
`data/<table>.json` files with a __meta envelope per CONTEXT D-05. Designed
to run inside .github/workflows/update-dataset.yml after the existing TS ETL
step. CONTEXT D-08: a single table failure aborts the entire run — partial
publishing is forbidden.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from dotenv import load_dotenv
from supabase import create_client, Client

SCHEMA_VERSION = 1  # CONTEXT D-05
PAGE_SIZE = 1000     # supabase-py default page max; bump down if rows are huge

TABLES = (
    "champion_stats",
    "champion_stats_by_role",
    "matchups",
    "synergies",
    "items",
    "runes",
    "summoner_spells",
)
# OPEN QUESTION #1: add "champions" + "patches" if json_repo._champion_map
# can't be derived from the existing 7. See "Open Questions" below.

def _json_default(obj: Any) -> Any:
    """JSON-serialize Decimal, UUID, datetime — types Supabase can return."""
    if isinstance(obj, Decimal):
        # Lossless: Decimal → str preserves precision (vs float which loses).
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj).__name__} not JSON-serializable: {obj!r}")

def _canonical_rows_sha256(rows: list[dict]) -> str:
    """sha256 over the canonical JSON of `rows` only (no __meta), per D-05."""
    canonical = json.dumps(
        rows, sort_keys=True, separators=(",", ":"), default=_json_default
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def _fetch_table(client: Client, table: str) -> list[dict]:
    """Paginate through a Supabase table using .range(start, end) inclusive bounds."""
    all_rows: list[dict] = []
    start = 0
    while True:
        end = start + PAGE_SIZE - 1  # range is INCLUSIVE on both ends
        resp = client.table(table).select("*").range(start, end).execute()
        page = resp.data or []
        all_rows.extend(page)
        if len(page) < PAGE_SIZE:
            break  # short page → end of table
        start += PAGE_SIZE
    return all_rows

def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, default=_json_default, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, path)

def export_table(client: Client, out_dir: Path, table: str) -> None:
    rows = _fetch_table(client, table)
    payload = {
        "__meta": {
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "sha256": _canonical_rows_sha256(rows),
            "row_count": len(rows),
            "schema_version": SCHEMA_VERSION,
            "source_table": table,
        },
        "rows": rows,
    }
    out_path = out_dir / f"{table}.json"
    _atomic_write_json(out_path, payload)
    print(f"[export] {table}: {len(rows)} rows → {out_path}")

def main() -> int:
    parser = argparse.ArgumentParser()
    # CONTEXT D-09: --out-dir for local-dev runs.
    parser.add_argument("--out-dir", type=Path, default=Path("./public/data"))
    args = parser.parse_args()

    load_dotenv()  # local-dev only; CI uses real env vars.
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # D-06
    client = create_client(url, key)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # CONTEXT D-08: atomic-or-nothing — fail fast if any table errors.
    for table in TABLES:
        try:
            export_table(client, args.out_dir, table)
        except Exception as exc:
            print(f"[export] FATAL: {table} failed: {exc}", file=sys.stderr)
            return 1

    print(f"[export] all {len(TABLES)} tables exported to {args.out_dir}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Pattern 4: GitHub Actions Workflow Extension (D-02, D-07)

**What:** Append to `supabase-dataset-updater/.github/workflows/update-dataset.yml`. The existing workflow runs the TS ETL via `pnpm update`. Phase 2 adds: setup-python → pip install → run export script → publish via `peaceiris/actions-gh-pages@v4` with `force_orphan: true` (D-03).

**YAML fragment (full file replacement — keeps existing job, appends steps):**

```yaml
# supabase-dataset-updater/.github/workflows/update-dataset.yml
name: "Update Supabase Dataset"
on:
  schedule:
    - cron: "0 12 * * *"
  workflow_dispatch:

# CONTEXT D-07: peaceiris/actions-gh-pages@v4 needs contents:write to push gh-pages.
permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      # ===== existing TS ETL (unchanged) =====
      - name: Install PNPM
        run: npm install -g pnpm
      - name: Sync node version and setup cache
        uses: actions/setup-node@v4
        with:
          node-version: "lts/*"
          cache: "pnpm"
      - name: Install dependencies
        run: pnpm install
      - name: Update Supabase dataset
        run: pnpm update
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}

      # ===== NEW (Phase 2) — Supabase → JSON export =====
      - name: Setup Python 3.12 for export
        uses: actions/setup-python@v5
        with:
          python-version: "3.12.x"

      - name: Install Python deps for export
        run: pip install supabase>=2.4.0 python-dotenv

      - name: Export Supabase tables to JSON
        working-directory: supabase-dataset-updater
        run: python scripts/export_to_json.py --out-dir ./public/data
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}

      - name: Publish to gh-pages branch
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./supabase-dataset-updater/public
          publish_branch: gh-pages
          force_orphan: true                 # CONTEXT D-03: rewrite history each push
          user_name: 'github-actions[bot]'
          user_email: 'github-actions[bot]@users.noreply.github.com'
          commit_message: 'data: refresh ${{ github.run_id }}'
```

**Layout note:** the action publishes the contents of `publish_dir` to the root of `gh-pages`. With `publish_dir: ./supabase-dataset-updater/public`, the action takes everything inside `public/` (which the export script wrote as `public/data/<table>.json`) and pushes it as `data/<table>.json` at the branch root. GitHub Pages then serves `https://<user>.github.io/<repo>/data/<table>.json`. ✅ matches spec §6.2.

[CITED: peaceiris/actions-gh-pages README — `force_orphan: true`, `permissions: contents: write` requirement, `publish_dir` default, gh-pages branch default — verified via WebFetch 2026-04-14.]

### Anti-Patterns to Avoid

- **Don't** read both cache files in series — fan-out is the difference between ~1 s and ~5 s startup. Use `ThreadPoolExecutor` (D-16). [VERIFIED: PITFALLS.md anti-pattern 7]
- **Don't** delete the `gh-pages` branch on rollback — `git push --force origin <prev-sha>:gh-pages` is the rollback path. Deletion would cause GitHub Pages to 404 (D-03). [CITED: D-03]
- **Don't** use `requests-cache` "for convenience" — D-15 explicitly rejects it. Adds 3 MB + SQLite dep + bloats AV-fingerprint surface. [CITED: D-15, STACK.md "What NOT to Use"]
- **Don't** branch `json_repo.py` on dev-vs-prod — both modes hit the CDN. The `CDN_BASE_URL` env override (D-20) is for local mock testing only.
- **Don't** import from `lolalytics_api.supabase_client` or `lolalytics_api.config` in `json_repo.py` — those carry the Supabase URL helper that this phase deletes from the runtime. The `supabase_repo` re-imports (D-12) only pull pure stdlib helpers (`_wilson_score`, `_normalize_slug`, etc.). [VERIFIED: read of `supabase_client.py` and `config.py` confirms they import `supabase` package; importing them at runtime would defeat D-23.]
- **Don't** put the `__meta.sha256` over `json.dumps(rows)` without `sort_keys=True` and `separators=(",", ":")` — the export side and the verify side MUST use identical canonical serialization or the hash won't match. [VERIFIED: D-05 specifies "canonical JSON serialization"]
- **Don't** forget `force_orphan: true` on the `peaceiris/actions-gh-pages@v4` step — without it, `gh-pages` history accumulates daily JSON diffs that bloat the repo (Pitfall #17). [CITED: PITFALLS.md #17]
- **Don't** enable `keep_files: true` on the publish step — `keep_files` is incompatible with `force_orphan` in v3 and the v4 README still flags it as not supported together. [CITED: WebFetch peaceiris README]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Conditional GET ETag handling | Custom HTTP client wrapping urllib | stdlib `requests` + 30 LoC manual `If-None-Match`/`If-Modified-Since` | `requests` already in deps; 304 status check is one branch. CONTEXT D-15 forbids `requests-cache`. |
| Atomic file replace | `shutil.move` + try/except + cleanup loop | `os.replace(tmp, final)` | Atomic on Windows + POSIX since Python 3.3. One stdlib call. [VERIFIED: stdlib docs] |
| sha256 verification | Re-implement SHA-256 | `hashlib.sha256(canonical_bytes).hexdigest()` | stdlib; constant-time comparison not needed (this isn't a MAC). |
| Git force-push to orphan branch | Bash script with `git checkout --orphan; git rm -rf .; git add; git commit; git push --force` | `peaceiris/actions-gh-pages@v4` with `force_orphan: true` | The action handles all the edge cases (no commits yet, force-push permissions, user.name/email config). Fallback inline-bash documented in `DATA-PIPELINE.md` for when the action is unavailable (D-07). |
| Supabase pagination | Manual page-size + offset arithmetic | `.range(start, end)` (inclusive bounds) | Supabase's documented pagination primitive; detect end-of-table when returned page is shorter than `PAGE_SIZE`. [CITED: Supabase Python `.range()` docs] |
| Decimal/UUID/datetime → JSON | Type-by-type isinstance branches at every call site | One `default=` callable passed to `json.dumps(...)` | Standard pattern. ~10 LoC handles all three types. Alternative `orjson` is overkill. [CITED: WebSearch + Python json docs] |
| Deep-equal of two list-of-dicts | Manual loop comparing fields | `assert sorted(a, key=stable_key) == sorted(b, key=stable_key)` (or `unittest`'s `assertCountEqual` for unordered) | List ordering from Supabase and CDN may differ; sort by a stable composite key first (e.g. `(patch, champion_key, role, opponent_key)` for matchups). |
| `concurrent.futures` cancellation/error propagation | Per-future try/except with manual aggregation | `for fut in as_completed(futures): result = fut.result()` re-raises in the main thread | Idiomatic; CDNError propagates out of `warm_cache()` so `backend.py` startup fails loud. |

**Key insight:** every "tricky" piece in this phase has a stdlib or first-class third-party answer that's smaller than the bug surface of a custom solution. The discipline is to keep `json_repo.py` to ~250 LoC and `export_to_json.py` to ~150 LoC by leaning on these primitives.

## Common Pitfalls

### Pitfall 1: PostgreSQL types blow up `json.dumps` in the export script

**What goes wrong:** `supabase-py` returns `Decimal` for `numeric` columns, `UUID` for `uuid` columns, possibly `datetime` for `timestamptz`. `json.dumps` raises `TypeError: Object of type Decimal is not JSON serializable`. CI fails on the first table that has a non-trivial schema.

**Why it happens:** Python's stdlib `json` module deliberately doesn't serialize anything beyond the JSON spec types. `supabase-py` returns whatever `postgrest-py` deserializes from the wire format, which for `numeric` is `Decimal` (correct for precision) and for `uuid` is `str` in some versions and `UUID` in others.

**How to avoid:** Always pass `default=_json_default` to `json.dumps(...)`. The `_json_default` callable handles `Decimal → str` (preserves precision; `float` would lose it), `UUID → str`, `datetime → isoformat()`. Anything else raises `TypeError` so the planner sees an explicit error and can extend the list.

**Warning signs:** First CI run of `export_to_json.py` errors with `TypeError: Object of type X is not JSON serializable`. Add `X` to `_json_default`.

[CITED: WebSearch — Python json module + Decimal/UUID custom encoder pattern, multiple sources.]

### Pitfall 2: `__meta.sha256` mismatch between exporter and verifier

**What goes wrong:** Exporter computes sha256 over `json.dumps(rows)` (with default kwargs); verifier in `json_repo.py` computes sha256 over `json.dumps(body["rows"], sort_keys=True, separators=(",", ":"))`. The bytes differ → sha256 differs → CDNError on every fetch → app won't start.

**Why it happens:** `json.dumps` default output has spaces after `,` and `:`, and dict-key order depends on the input order. The "canonical" choice is `sort_keys=True, separators=(",", ":")` — but BOTH sides MUST agree.

**How to avoid:** Define `_canonical_rows_sha256(rows)` once in each module, with identical kwargs. Document the canonical form in `DATA-PIPELINE.md` so future maintainers don't break it. Add a smoke test: round-trip a small fixture through `export_to_json` then through `json_repo._fetch_one` and assert no CDNError.

**Warning signs:** The first end-to-end CDN→client fetch raises `CDNError: sha256 mismatch ...`. The numbers in the error message tell you which side is wrong.

[VERIFIED: D-05 explicitly says "canonical JSON serialization" but doesn't pin separators — picking `(",", ":")` and `sort_keys=True` is the standard canonical form.]

### Pitfall 3: Cutover ordering — the .exe stops building mid-PR

**What goes wrong:** Phase 1 commit `451e8f7` is the lesson: the supabase excludes were added to `backend.spec` (D-09) BEFORE the `supabase_repo` import was removed from `backend.py`. The frozen .exe crashed at startup with `ModuleNotFoundError: No module named 'supabase'`. The `build-smoke.yml` "Verify supabase NOT in bundle" guard was also active, so even the build broke if the excludes worked. Resolution required a hot-fix that deferred all three changes to Phase 2.

**Why it happens:** Three load-bearing changes (backend.py import swap, requirements.txt removal, backend.spec excludes restoration, build-smoke.yml guard re-enable) MUST happen in lockstep. If any single one is committed first, CI breaks.

**How to avoid:** Plan the cutover as a single atomic commit (or a single tightly-coupled wave), not as separate tasks across waves:

- **Step 1 (safe, can land alone):** Land `json_repo.py` + `test_json_repo_cache.py` + `test_json_repo_contract.py`. No consumer; both `supabase_repo` and `json_repo` co-exist. CI keeps passing.
- **Step 2 (atomic — single commit):** Apply ALL FOUR of these together:
  - `backend.py`: swap `supabase_repo` import block → `json_repo` (lines 11–21).
  - `backend.py`: remove `from lolalytics_api.supabase_client import get_supabase_client` (line 20) and `from lolalytics_api.config import get_supabase_url` (line 21).
  - `backend.py`: add `json_repo.warm_cache()` call at startup (after Phase 1's argparse, before `socketio.run`).
  - `requirements.txt`: remove `supabase>=2.4.0` line.
  - `backend.spec`: re-add the 7 supabase-family excludes (uncommenting the block at lines 64–82).
  - `.github/workflows/build-smoke.yml`: uncomment the "Verify supabase NOT in bundle" block (lines 73–82).
- **Step 3 (post-merge validation):** Confirm CI smoke passes; confirm `strings dist/backend-x86_64-pc-windows-msvc.exe | grep -i supabase` returns empty.

**Warning signs:** Any PR that touches one of the four files but not the others. The plan should produce a verification step that grep-asserts all four are touched together.

[VERIFIED: read of `backend.py` lines 11–21 confirms the supabase_repo import block is exactly there; read of `backend.spec` lines 64–82 confirms the excludes block is commented with the Phase 2 restore note; read of `build-smoke.yml` lines 66–82 confirms the guard block is commented with the same note; commit `451e8f7` message confirms the rationale.]

### Pitfall 4: GitHub Pages edge cache serves stale JSON after fresh export

**What goes wrong:** GitHub Pages is fronted by Fastly with a default `Cache-Control: max-age=600`. After a force-push to `gh-pages`, Fastly may continue serving the old body for up to 10 minutes. Conditional GET 304 from the edge can also lie if the edge hasn't revalidated.

**Why it happens:** The CDN edge cache is independent of origin freshness. GitHub doesn't expose Fastly purge to free Pages users.

**How to avoid (within Phase 2 scope):**
1. **Accept it.** Pitfall #15 in research/PITFALLS.md flags this and CONTEXT D-14 + N-06 explicitly defer manifest-versioning. Daily refresh with up to 10 min edge lag is acceptable for v1.
2. **Surface the lag to the user via `__meta.exported_at`.** The client logs `exported_at` and Phase 3's UX shows "data from <date>" — so if a patch dropped 6 hours ago and the cache shows 2-day-old data, the indicator goes amber/red.
3. **Optional CI canary** (post-export step, deferred — out of phase 2 unless trivial): `curl https://<user>.github.io/<repo>/data/champion_stats.json` and check `__meta.exported_at` is within 10 min. Beyond Phase 2 scope.

**Warning signs:** Issue reports of "the new patch isn't showing up" within an hour of an ETL run. The 10-min Fastly TTL means the edge should always catch up within an hour; if it doesn't, file a GitHub Pages support issue.

[CITED: STACK.md "GitHub Pages-specific confirmations" + PITFALLS.md #15 — "GitHub Pages applies a default `Cache-Control: max-age=600` (10 min) at the edge."]

### Pitfall 5: ETL/export race — partial data published

**What goes wrong:** The TS ETL writes rows in batches (matchups can be millions of rows). If the export step queries Supabase mid-write, `champion_stats` may reference champion_keys that aren't in `matchups` yet. Recommendation engine silently skips them. Users get wrong scores for some champions.

**Why it happens:** ETL + export share no transactional boundary. GitHub Actions enforces step ordering, not Supabase consistency.

**How to avoid (within Phase 2 scope):** The CONTEXT does not require a staging-table migration (that's flagged MEDIUM in PITFALLS.md #16). Cheaper Phase 2 mitigation:
1. Run the export step **only after** the TS ETL step succeeds (the YAML in Pattern 4 already does this — `pnpm update` is a separate step before `python export_to_json.py`, and GitHub Actions fail-fast aborts the workflow if `pnpm update` errored).
2. Optional integrity check inside `export_to_json.py`: every `champion_key` in `matchups.rows` must appear in `champion_stats.rows` for the same patch. ~10 LoC validator. Aborts on violation per D-08.

**Warning signs:** Sporadic "champion X missing recommendation" reports the day after an ETL run. Diff between consecutive `gh-pages` commits shows some tables updated but not others (force_orphan makes this hard to see — fall back to comparing `__meta.exported_at` across files; they should all be within seconds of each other since one script writes them all).

[CITED: PITFALLS.md #16 ETL/export race; CONTEXT D-08 atomic-or-nothing semantics.]

### Pitfall 6: schema_version=1 enforcement is a one-way door

**What goes wrong:** `json_repo` accepts `schema_version <= 1` and rejects `> 1`. The first time the export script bumps to `schema_version=2`, every installed v1.0.x client breaks instantly. Users see "backend stopped unexpectedly" until they upgrade.

**Why it happens:** The reject-on-`>1` rule is intentional (D-05 + spec §6) — it's a deliberate forcing function for breaking-change migrations. The pitfall is operational, not implementation: Phase 2 ships v1, and a future v2 export must coordinate with a Tauri auto-update push.

**How to avoid (within Phase 2 scope):** Document the rule in `DATA-PIPELINE.md` next to the `gh-pages` runbook. State explicitly: "Bumping schema_version requires a coordinated client release; do not bump until the new client is in `latest.json` (Phase 4)." Add a rate-limited test that exercises both the `> 1` reject path and the `< 1` warn-but-proceed path so the contract is locked.

**Warning signs:** A future PR that bumps `SCHEMA_VERSION = 2` in the exporter without first shipping a client that knows about v2. Pre-merge guard: a unit test in `test_json_repo_cache.py` that asserts the current client SUPPORTED_VERSIONS set, with a comment "do not change without coordinating client release".

[VERIFIED: D-05 + CONTEXT additional context bullet 7. The rule is in scope; the operational hazard is forward-looking.]

### Pitfall 7: Contract-test live-credential leakage

**What goes wrong:** `test_json_repo_contract.py` calls `supabase_repo.get_X(...)` which requires a real Supabase URL + key. If a contributor runs `pytest` without `.env` set, the test crashes with an unrelated error ("SUPABASE_URL is not set"). On CI the tests need real credentials — accidentally running them on a public-fork PR would expose the key.

**Why it happens:** D-29 acknowledges contract tests need live CDN + live Supabase access. Standard pytest discovery will pick them up by default.

**How to avoid:**
1. **Mark the test:** `@pytest.mark.contract` decorator + `pytest.ini` config `markers = contract: requires live Supabase + CDN`. Default pytest run skips them; CI explicitly adds `-m contract`.
2. **Env guard at module level:** `pytestmark = pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="contract test needs live Supabase")`. Skip with clear message when creds absent.
3. **CI scope:** the contract test job in CI uses `pull_request` trigger restricted to first-party PRs (e.g. `if: github.event.pull_request.head.repo.full_name == github.repository`). Don't run with secrets on fork PRs.
4. **Run cadence:** Recommendation per CONTEXT discretion bullet 4 — contract tests run **daily** (after the export step lands new data) rather than per-commit. Wire into `update-dataset.yml` as a final step OR a separate scheduled workflow that runs ~30 min after.

**Warning signs:** A PR from a fork triggers the contract test job; CI would either skip-with-creds-absent (correct) or expose the key (security incident).

[CITED: D-29 + CONTEXT discretion bullet 4]

## Code Examples

### Example 1: Conditional-GET cache hit/miss path (D-14, D-16, D-17)

The full skeleton is in "Pattern 1" above. The 30-LoC load-bearing block (excerpted):

```python
# Source: D-15 manual ETag pattern; STACK.md GitHub Pages confirmations
def _fetch_one(table: str) -> List[Dict[str, Any]]:
    url = f"{CDN_BASE_URL}/{table}.json"
    meta = _load_meta(table)
    headers = {}
    if meta:
        if etag := meta.get("etag"):
            headers["If-None-Match"] = etag
        if last_mod := meta.get("last_modified"):
            headers["If-Modified-Since"] = last_mod
    resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
    if resp.status_code == 304:
        return _load_body(table)["rows"]  # cache hit
    resp.raise_for_status()
    body = resp.json()
    _atomic_write_json(_cache_dir() / f"{table}.json", body)
    _atomic_write_json(_cache_dir() / f"{table}.meta.json", {
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "fetched_at": resp.headers.get("Date"),
        "sha256": body["__meta"].get("sha256"),
    })
    return body["rows"]
```

### Example 2: Concurrent fan-out (D-16) — ~10 LoC

```python
# Source: stdlib concurrent.futures docs; CONTEXT D-16
from concurrent.futures import ThreadPoolExecutor, as_completed

def warm_cache():
    with ThreadPoolExecutor(max_workers=7) as ex:
        future_to_table = {ex.submit(_fetch_one, t): t for t in _TABLES}
        for fut in as_completed(future_to_table):
            t = future_to_table[fut]
            _data[t] = fut.result()  # propagates CDNError (loud failure path)
```

### Example 3: Contract test pattern (D-29)

```python
# counterpick-app/apps/backend/test_json_repo_contract.py
"""
CDN-01 verification: json_repo and supabase_repo return identical data.

This test requires LIVE Supabase + LIVE CDN access. CI runs it daily after
the export step lands new data. Skip locally unless creds are present.
"""

from __future__ import annotations

import os
import pytest

from lolalytics_api import supabase_repo, json_repo

# Pitfall #7 mitigation: skip when creds absent.
pytestmark = [
    pytest.mark.contract,  # CI uses `pytest -m contract`
    pytest.mark.skipif(
        not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
        reason="contract test needs live Supabase credentials",
    ),
]

# ----- helpers -----

def _stable_sort(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Sort list-of-dicts by composite key so order-insensitive compare works."""
    return sorted(rows, key=lambda r: tuple(r.get(k) for k in keys))

def _assert_rows_equal(a: list[dict], b: list[dict], keys: tuple[str, ...]) -> None:
    """Deep-equal two list-of-dicts modulo ordering, on the given key tuple."""
    sa, sb = _stable_sort(a, keys), _stable_sort(b, keys)
    assert sa == sb, (
        f"row count: supabase={len(sa)} cdn={len(sb)}; "
        f"first diff: supabase={sa[0] if sa else None} cdn={sb[0] if sb else None}"
    )

# ----- one test per public function -----

def test_get_items_parity():
    a = supabase_repo.get_items()
    b = json_repo.get_items()
    _assert_rows_equal(a, b, keys=("patch", "item_id"))

def test_get_runes_parity():
    a = supabase_repo.get_runes()
    b = json_repo.get_runes()
    _assert_rows_equal(a, b, keys=("patch", "rune_id"))

def test_get_summoner_spells_parity():
    a = supabase_repo.get_summoner_spells()
    b = json_repo.get_summoner_spells()
    _assert_rows_equal(a, b, keys=("patch", "spell_key"))

def test_get_champion_stats_parity():
    # supabase_repo.get_champion_stats requires a champion arg — see source.
    a = supabase_repo.get_champion_stats("Aatrox")
    b = json_repo.get_champion_stats("Aatrox")
    assert a == b  # single-row dict; structural equality

def test_get_champion_stats_by_role_parity():
    a = supabase_repo.get_champion_stats_by_role("Ahri")
    b = json_repo.get_champion_stats_by_role("Ahri")
    assert a == b

def test_get_matchups_parity():
    a = supabase_repo.get_matchups("Lux", role="middle")
    b = json_repo.get_matchups("Lux", role="middle")
    # get_matchups returns a dict with rows + base_winrate + base_wilson + role.
    # Compare top-level scalars exactly; sort the rows lists.
    assert a["base_winrate"] == pytest.approx(b["base_winrate"])
    assert a["base_wilson"] == pytest.approx(b["base_wilson"])
    assert a["role"] == b["role"]
    _assert_rows_equal(a["by_delta"], b["by_delta"], keys=("opponent_key",))
    _assert_rows_equal(a["by_normalized"], b["by_normalized"], keys=("opponent_key",))

def test_get_synergies_parity():
    a = supabase_repo.get_synergies("Lulu", role="support")
    b = json_repo.get_synergies("Lulu", role="support")
    assert a["base_winrate"] == pytest.approx(b["base_winrate"])
    assert a["role"] == b["role"]
    _assert_rows_equal(a["rows"], b["rows"], keys=("mate_key",))
```

**Marker config addition** (in `pyproject.toml` `[tool.pytest.ini_options]` or new `pytest.ini`):

```ini
[pytest]
markers =
    contract: live-credential parity test (skipped by default; CI: pytest -m contract)
```

### Example 4: Cache unit test with mocked HTTP (D-30)

```python
# counterpick-app/apps/backend/test_json_repo_cache.py
"""
CDN-02..CDN-04 verification: cache lifecycle without network.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from lolalytics_api import json_repo

@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point user_cache_dir() at a tmp_path so each test gets fresh state."""
    monkeypatch.setattr(
        "lolalytics_api.json_repo._cache_dir",
        lambda: tmp_path / "cdn",
    )
    (tmp_path / "cdn").mkdir(parents=True, exist_ok=True)
    yield tmp_path / "cdn"

def _make_resp(status: int, body: dict | None = None, headers: dict | None = None):
    m = MagicMock()
    m.status_code = status
    m.headers = headers or {}
    m.content = json.dumps(body).encode() if body else b""
    m.json.return_value = body
    m.text = json.dumps(body) if body else ""
    return m

def test_cache_cold_fetch_writes_pair(isolated_cache):
    """200 path writes both <table>.json and <table>.meta.json."""
    body = {
        "__meta": {
            "exported_at": "2026-04-14T03:15:00Z",
            "sha256": "irrelevant_test",  # bypass via mock; real test in test_sha256_mismatch
            "row_count": 0,
            "schema_version": 1,
        },
        "rows": [],
    }
    headers = {"ETag": 'W/"abc123"', "Last-Modified": "Mon, 14 Apr 2026 03:15:00 GMT"}
    with patch("lolalytics_api.json_repo.requests.get",
               return_value=_make_resp(200, body, headers)):
        # Disable sha256 check for this test by patching the canonical fn:
        with patch("lolalytics_api.json_repo.hashlib.sha256") as m:
            m.return_value.hexdigest.return_value = "irrelevant_test"
            rows = json_repo._fetch_one("items")
    assert rows == []
    assert (isolated_cache / "items.json").exists()
    assert (isolated_cache / "items.meta.json").exists()
    meta = json.loads((isolated_cache / "items.meta.json").read_text())
    assert meta["etag"] == 'W/"abc123"'

def test_cache_304_reuses_cached_body(isolated_cache):
    """304 path reads <table>.json and skips network write."""
    cached = {"__meta": {"schema_version": 1}, "rows": [{"id": 1}]}
    (isolated_cache / "items.json").write_text(json.dumps(cached))
    (isolated_cache / "items.meta.json").write_text(json.dumps({
        "etag": 'W/"old"', "last_modified": "Mon, 13 Apr 2026 00:00:00 GMT"
    }))
    with patch("lolalytics_api.json_repo.requests.get",
               return_value=_make_resp(304, headers={"ETag": 'W/"old"'})) as get:
        rows = json_repo._fetch_one("items")
    assert rows == [{"id": 1}]
    sent = get.call_args.kwargs["headers"]
    assert sent.get("If-None-Match") == 'W/"old"'

def test_corrupt_cache_recovers(isolated_cache):
    """JSONDecodeError on body → delete pair → refetch."""
    (isolated_cache / "items.json").write_text("{ truncated...")
    (isolated_cache / "items.meta.json").write_text(json.dumps({"etag": "x"}))
    body = {"__meta": {"schema_version": 1, "sha256": "x"}, "rows": []}
    with patch("lolalytics_api.json_repo.requests.get",
               return_value=_make_resp(200, body)):
        with patch("lolalytics_api.json_repo.hashlib.sha256") as m:
            m.return_value.hexdigest.return_value = "x"
            rows = json_repo._fetch_one("items")
    assert rows == []  # refetched, no crash

def test_atomic_write_no_partial(isolated_cache):
    """tmp file is replaced — final never half-written."""
    target = isolated_cache / "items.json"
    json_repo._atomic_write_json(target, {"x": 1})
    # On POSIX/NTFS, after os.replace, target exists, tmp doesn't.
    assert target.exists()
    assert not target.with_suffix(target.suffix + ".tmp").exists()
    assert json.loads(target.read_text()) == {"x": 1}
```

### Example 5: Conditional-GET wire details

**304 contract:**
- Status: `304 Not Modified`
- Body: empty (`Content-Length: 0`); `resp.json()` would raise — check `status_code` first.
- Headers: per RFC 7232, the server MUST include any of `Cache-Control`, `Content-Location`, `Date`, `ETag`, `Expires`, `Vary` it would have sent in the 200 response. GitHub Pages returns at minimum `ETag` and `Date`.
- Client MUST reuse cached body — don't try to parse `resp.content` on 304.

**`If-None-Match` header:** Send with the previous `ETag` value verbatim, including the `W/` prefix for weak ETags (GitHub Pages uses weak ETags). Don't strip the quotes — `If-None-Match: W/"abc123"`.

**`If-Modified-Since` header:** Send with the previous `Last-Modified` value verbatim (RFC 7231 IMF-fixdate format, e.g. `Mon, 14 Apr 2026 03:15:00 GMT`). Don't reformat.

**Both at once:** Send both `If-None-Match` AND `If-Modified-Since`. Per RFC 7232, the server prefers `If-None-Match` if both are present. GitHub Pages honors both correctly. Sending both is the safest pattern — it adds zero bytes of meaningful overhead.

[CITED: RFC 7232 Section 4.1 (304 Not Modified); MDN HTTP conditional requests; verified against STACK.md "GitHub Pages-specific confirmations".]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Client → Supabase via `supabase-py` | Client → GitHub Pages CDN via `requests` + manual ETag cache | Phase 2 of this milestone | Removes ~15–20 MB from PyInstaller bundle, eliminates all client-side credentials, ~5 MB bundle reduction after re-adding excludes (D-24). |
| `cache_data.json` in `apps/backend/` (24h TTL, single file, dev-mode-only) | Per-table cache in `user_cache_dir()/cdn/<table>.json` + `<table>.meta.json` (conditional-GET refresh on startup) | Phase 1 moved `cache_data.json` to `user_cache_dir()`; Phase 2 introduces the new `cdn/` subdirectory layout | Cache survives reinstall; per-table staleness is detectable; corrupt-cache auto-recovery (D-18). |
| `peaceiris/actions-gh-pages@v3` | `peaceiris/actions-gh-pages@v4` | v4 GA in 2024; v3 still works but is end-of-life | v4 fixes a `keep_files`+`force_orphan` interaction bug (per the v4 README — flagged as "future support" in v3). For our use case (force_orphan=true, keep_files default false), the behavior is identical. Use v4 because v3 is in maintenance mode. |
| `requests-cache` for HTTP caching | Manual `If-None-Match` / `If-Modified-Since` (D-15) | Decision in this milestone | Simpler, smaller, avoids SQLite dep. The tradeoff (no automatic cache eviction policy) doesn't matter for 7 known files. |
| Storing JSON in `main` branch | Orphan `gh-pages` branch with force-push (D-03) | Decision in this milestone | Avoids 3 GB/year of git history bloat (Pitfall #17). Loses commit history but `__meta.exported_at` + ETL workflow logs are the audit trail. |

**Deprecated/outdated:**
- `supabase-py` 1.x — version pin is `>=2.4.0`; current install is `2.28.3`. No reason to revisit pinning.
- `requests` 2.31 and earlier — pin `>=2.32` because security-relevant CVE fixes; current install `2.33.1` is fine.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `champions` and `patches` tables, used by `supabase_repo._champion_map()` and `_get_latest_patch()`, can be derived from the 7 tables in CONTEXT D-04 OR can be added to the export list with a planner-side amendment | "Pattern 1" `_champion_map` skeleton, Open Question #1 | If neither: `json_repo` cannot resolve champion names. Mitigation: add `champions` and `patches` to D-04 in PLAN.md. Low risk — both tables are tiny (~170 rows + ~10 rows). |
| A2 | `supabase-py` `.range(start, end)` works the same in version `2.28.3` as documented for current versions (inclusive bounds, both ends) | "Pattern 3" pagination loop | Off-by-one in pagination → some rows missing from CDN. Mitigation: add a row-count assertion to the export script (`assert row_count == client.table(t).select("*", count="exact").execute().count`). |
| A3 | Stable sort key tuple `(patch, champion_key, role, opponent_key)` is sufficient to deterministically order matchups for contract test deep-equal | Example 3 contract test | False positive contract failures if rows differ only in ordering with a different effective key. Mitigation: pick the actual primary key from the Supabase schema once verified. |
| A4 | `peaceiris/actions-gh-pages@v4` works with `publish_dir: ./supabase-dataset-updater/public` (subdirectory of the repo root) | "Pattern 4" YAML | If only repo-root paths work, planner adjusts to `cd supabase-dataset-updater && python ...` and uses a relative `publish_dir`. Low risk — the action accepts arbitrary paths per its README. |
| A5 | GitHub Pages behavior described (ETag, Last-Modified, 304 contract) is unchanged in 2026 from the STACK.md research | "Pattern 1" + "Conditional-GET Specifics" | Cache bypassed (always 200 instead of 304) → wasted bandwidth but functional. Or: always 304 even after change → stale data. Mitigation: end-to-end test against the real CDN URL once D-26 is resolved. |
| A6 | The `__meta.sha256` canonical form `(sort_keys=True, separators=(",",":"))` is acceptable as the canonical form (CONTEXT D-05 only says "canonical JSON serialization") | Pattern 1 + Pitfall #2 | Hash mismatch on every fetch. Mitigation: define the canonical form in ONE place (`DATA-PIPELINE.md`) and reference from both modules. |
| A7 | The contract-test marker pattern (`@pytest.mark.contract`) is acceptable for the existing pytest config; no `pytest.ini` exists currently and adding one is OK | Pitfall #7 + Example 3 | If `pyproject.toml` already has a `[tool.pytest.ini_options]` section that conflicts, planner adjusts. Verified: `pyproject.toml` does NOT currently have pytest config — the `[project.optional-dependencies] test = [...]` is the only pytest-related entry. Adding markers config is safe. |
| A8 | Re-importing `_wilson_score`, `_normalize_slug`, `_attach_names` from `supabase_repo` (D-12) does NOT import the supabase package transitively, because those are pure functions in `supabase_repo.py` lines 6–22 + 25–29 + 99–105 that don't reference `get_supabase_client` | Pattern 1 + D-12 | Wrong: importing `supabase_repo` runs `from lolalytics_api.supabase_client import get_supabase_client` (line 3 of supabase_repo.py), which imports `supabase`. So importing ANY name from `supabase_repo` triggers the supabase import chain → defeats D-23/D-24 → frozen .exe re-breaks (the `451e8f7` regression). **HIGH RISK — see Open Question #2.** |

## Open Questions

1. **Champions table source for `json_repo._champion_map()` / `_get_latest_patch()`**
   - What we know: `supabase_repo._champion_map()` reads from `supabase.table("champions")`; `_get_latest_patch()` reads from `supabase.table("patches")`. Neither table is in CONTEXT D-04's export list.
   - What's unclear: Whether to add `champions` + `patches` to D-04, or to derive both from the existing exports (e.g., champion names from `champion_stats` joined with… nothing — names aren't there; latest patch from `max(champion_stats.rows[].patch)` — works).
   - Recommendation: **Add `champions` + `patches` to the export list in PLAN.md as a D-04 amendment.** Both are tiny tables (~170 + ~10 rows). The alternative — deriving the champion name map from elsewhere — requires either changing the export schema (more work) or hardcoding a static list (brittle on new champion releases). Cost: 2 extra HTTP calls in fan-out (10 → 9 stays under the 7-thread pool fine).

2. **D-12 helper re-import imports `supabase_client` transitively** (Assumption A8 — HIGH RISK)
   - What we know: `supabase_repo.py` line 3: `from lolalytics_api.supabase_client import get_supabase_client`. This runs at module-import time. Therefore `from lolalytics_api.supabase_repo import _wilson_score` triggers `import supabase` somewhere in the chain.
   - What's unclear: Whether `lazy import` patterns or restructuring `supabase_repo.py` to defer the `get_supabase_client` import inside each function (rather than at module top) is acceptable. CONTEXT N-03 says `supabase_repo.py` stays unchanged in source.
   - Recommendation: **Move the pure helpers (`_wilson_score`, `_normalize_slug`, `_attach_names`) into a new sibling module `lolalytics_api/_helpers.py`** that has zero supabase imports. Both `supabase_repo.py` and `json_repo.py` import from `_helpers`. This honors D-12 intent (no duplication) and D-22/D-23/D-24 (no supabase in the runtime). Alternative: copy the helpers verbatim into `json_repo.py` (small functions, ~30 LoC total) — slight duplication but zero risk of import chain regression. **Strongly recommend the planner pick one before writing tasks.**

3. **Concrete `CDN_BASE_URL` value (D-26)**
   - What we know: Placeholder `https://{GITHUB_USER}.github.io/{REPO_NAME}/data`. Repo: `Chertixd/LoL-Draft-Helper` (verified from `git remote -v`).
   - What's unclear: Is the actual GitHub user `Chertixd`? Should the URL be `https://chertixd.github.io/LoL-Draft-Helper/data`? GitHub Pages URLs are case-sensitive on the path (`LoL-Draft-Helper` vs `lol-draft-helper`).
   - Recommendation: Planner asks user to confirm `chertixd.github.io/LoL-Draft-Helper/data` before hardcoding. Detected default from `git remote -v`: `https://chertixd.github.io/LoL-Draft-Helper/data`. After confirmation, bake into `json_repo.CDN_BASE_URL` default.

4. **Whether `champion_stats` rows have a `name` field already, or if names live exclusively in the `champions` table**
   - What we know: `supabase_repo._attach_names(rows, key_to_name, key_field)` is called explicitly to add `row["name"]` based on `row["opponent_key"]` or `row["mate_key"]`. So the row tables have keys, not names.
   - What's unclear: Whether `champion_stats_by_role` or `champion_stats` ALSO have names attached, or if the consumer code that gets stats also has to call `_champion_map()` to resolve the displayed name. (Worth checking before assuming `champions` table is needed.)
   - Recommendation: Planner runs a Supabase query against `champion_stats` to confirm column list; if `name` is present, Open Question #1 trivializes (no need to export `champions` table). Phase 2 plan should include this verification step.

5. **Daily contract-test cadence wiring**
   - What we know: D-29 says "run in the daily CI (after the export step lands new data)". CONTEXT discretion bullet 4 confirms recommendation: daily.
   - What's unclear: Where exactly to wire the contract-test job. Two options:
     - (a) Append as a final step in `supabase-dataset-updater/.github/workflows/update-dataset.yml` (after the export step). Pro: tightest coupling to the data refresh. Con: lives in a different sub-package than the test code.
     - (b) New file `.github/workflows/contract-tests.yml` with `schedule: cron: "30 12 * * *"` (30 min after the daily ETL). Pro: isolation. Con: timing brittleness if ETL slows.
   - Recommendation: **(a) — append to update-dataset.yml.** Time-aligned with the data, single workflow to debug.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | export + json_repo + tests | ✓ | 3.12.x (CI pin from Phase 1 D-16) | — |
| `supabase` (Python) | export script | ✓ | 2.28.3 verified locally | install via pip in workflow |
| `requests` | json_repo + smoke_test_exe | ✓ | 2.33.1 verified locally | — |
| `platformdirs` | resources.user_cache_dir() | ✓ | 4.9.6 verified locally | — |
| GitHub Actions `windows-latest` | build-smoke.yml | ✓ | (unchanged from Phase 1) | — |
| GitHub Actions `ubuntu-latest` | update-dataset.yml | ✓ | (unchanged from existing ETL workflow) | — |
| `peaceiris/actions-gh-pages@v4` | publish step | ✓ | v4 (Marketplace) | inline `git push --force` documented in `DATA-PIPELINE.md` |
| GitHub Pages enablement | CDN URL serving | ✗ | — | **Manual one-time step** — operator runbook in `DATA-PIPELINE.md`. Cannot be automated without admin token. |
| `gh-pages` orphan branch (initial) | First force-push target | ✗ | — | **Manual one-time bootstrap** — runbook in `DATA-PIPELINE.md`. After first push, CI maintains it. |
| Live Supabase credentials in CI | export step + contract tests | ✓ | (already used by existing ETL workflow per `update-dataset.yml`) | — |
| `responses` (test-only) | test_json_repo_cache.py mocks | ✗ | — | Use `unittest.mock.patch('requests.get', ...)` shim instead — already in stdlib. **Recommendation: skip `responses`, use `unittest.mock`** to avoid adding a test dep. |

**Missing dependencies with no fallback:** none that block code execution. Two operator actions are required:

- **GitHub Pages enablement** — must be done by repo owner via Settings → Pages → Source: `gh-pages` branch / Path: `/ (root)`. Documented in `DATA-PIPELINE.md`. Phase 2 plan must include a "human-action" task gating the merge.
- **`gh-pages` orphan branch bootstrap** — must be done once before the first CI run (else `peaceiris/actions-gh-pages@v4` creates it implicitly with `force_orphan: true`, but the GitHub Pages Settings still need to be flipped). Documented in `DATA-PIPELINE.md`.

**Missing dependencies with fallback:**

- **`responses` library** — fall back to `unittest.mock.patch`. The only loss is slightly more verbose mock setup; functionality is equivalent.

## Validation Architecture

`workflow.nyquist_validation` is `false` in `.planning/config.json` — section omitted per template instructions.

## Sources

### Primary (HIGH confidence)

- `.planning/phases/02-cdn-data-plane/02-CONTEXT.md` — 30 locked decisions; the source of truth for this phase. [CITED]
- `.planning/research/SUMMARY.md` — Phase 2 section, open questions 2/3/5/6 resolved by CONTEXT. [CITED]
- `.planning/research/STACK.md` — manual ETag cache pattern; explicit "do not use requests-cache"; GitHub Pages ETag/Last-Modified verification. [CITED]
- `.planning/research/ARCHITECTURE.md` — `json_repo` 9-function surface; cache topology; Flow C/D/F (cold fetch / cache hit / crash recovery); section verified against `supabase_repo.py` source. [CITED]
- `.planning/research/PITFALLS.md` — pitfalls #12 (signature drift), #13 (cache corruption), #15 (CDN edge cache), #16 (ETL/export race), #17 (gh-pages bloat); anti-pattern 6 (data on main); anti-pattern 7 (sync per-table fetch). [CITED]
- `.planning/phases/01-sidecar-foundation/01-CONTEXT.md` — D-13 (`resources.py`), D-14 (no `__file__` runtime path), N-03 (supabase import retained for Phase 1). [CITED]
- `.planning/phases/01-sidecar-foundation/01-02-SUMMARY.md` — confirms `backend.py` `main()` shipped with CLI args + ready-file + atomic-write pattern (template for Phase 2 `_atomic_write_json`). [CITED]
- `counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` (lines 1–444) — the canonical 9-function contract. [VERIFIED: read 2026-04-14]
- `counterpick-app/apps/backend/backend.py` (lines 1–60 read) — confirms current import block at lines 11–21 matches CONTEXT D-22 expectation. [VERIFIED: read 2026-04-14]
- `counterpick-app/apps/backend/backend.spec` — confirms current excludes block (lines 64–82) is commented with the Phase 2 restore note. [VERIFIED: read 2026-04-14]
- `counterpick-app/apps/backend/requirements.txt` — confirms `supabase>=2.4.0` is line 10. [VERIFIED: read 2026-04-14]
- `.github/workflows/build-smoke.yml` — confirms "Verify supabase NOT in bundle" guard is commented at lines 66–82 with Phase 2 re-enable note. [VERIFIED: read 2026-04-14]
- `supabase-dataset-updater/src/supabase-etl.ts` — confirms existing TS ETL uses service-role key; lists tables (matches CONTEXT D-04 minus `champions`+`patches`). [VERIFIED: read 2026-04-14]
- `supabase-dataset-updater/.github/workflows/update-dataset.yml` — confirms current workflow shape; appendable per CONTEXT D-02. [VERIFIED: read 2026-04-14]
- Commit `451e8f7` (`fix(01-sidecar-foundation): reconcile D-09 supabase excludes with N-03 import retention`) — confirms the cutover-ordering hazard, message contains the resolution rationale. [VERIFIED: `git show` 2026-04-14]

### Secondary (MEDIUM confidence — verified across multiple sources)

- [GitHub - peaceiris/actions-gh-pages](https://github.com/peaceiris/actions-gh-pages) — `force_orphan: true` documentation; `permissions: contents: write` requirement; `publish_dir`/`publish_branch` defaults. [WebFetch verified 2026-04-14]
- [Supabase Python `.range()` docs](https://supabase.com/docs/reference/python/range) — pagination semantics; inclusive bounds; end-of-table detection. [WebFetch verified 2026-04-14]
- [Python json module — custom encoder pattern for Decimal/UUID/datetime](https://thelinuxcode.com/encoding-and-decoding-custom-objects-in-python-json-patterns-pitfalls-and-production-practices/) — `default=` callable pattern. [WebSearch verified 2026-04-14, multiple sources]
- [RFC 7232 — HTTP/1.1 Conditional Requests](https://tools.ietf.org/html/rfc7232) — 304 Not Modified contract; required headers in 304 response. [WebSearch verified 2026-04-14]
- [MDN HTTP Conditional Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests) — `If-None-Match`/`If-Modified-Since` semantics, browser/client interaction. [WebSearch verified 2026-04-14]

### Tertiary (LOW confidence — flagged for validation)

- Exact CDN edge-cache TTL on GitHub Pages in 2026 (STACK.md cites `Cache-Control: max-age=600` as default; community-sourced, not verified directly in this session). Impact: stale-data tolerance is bounded somewhere between 5 min and 1 hour; either way Pitfall #4 mitigation stands.
- Whether `peaceiris/actions-gh-pages@v4` creates the `gh-pages` orphan branch implicitly on first run with `force_orphan: true`, or requires the branch to exist first. The README implies "yes, creates implicitly" but a safe operator runbook bootstraps it manually before the first CI push.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all libraries already installed and version-verified locally; no new runtime deps; CONTEXT locks every choice.
- Architecture: HIGH — 9-function contract verified against source; cache topology verified against ARCHITECTURE.md research; cutover ordering grounded in actual Phase 1 commit history (`451e8f7`).
- Pitfalls: HIGH — five identified pitfalls are concrete, two have known mitigations from existing research, one (Assumption A8 / Open Question #2) is a newly-discovered hazard not in the prior research that the planner MUST address.
- Code examples: MEDIUM — skeletons are derived from CONTEXT + reading `supabase_repo.py`; exact line-by-line equivalence of the 9 public functions still requires the planner to copy-modify each in turn. The skeletons are correct in shape and should be ~95 % accurate by content.

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (30 days for stable infra; GitHub Pages behavior, peaceiris action, and supabase-py API are all stable on this horizon).

---

*Phase: 02-cdn-data-plane*
*Researched: 2026-04-14*
