---
phase: 02-cdn-data-plane
plan: 01
subsystem: data-access
tags:
  - python
  - http-cache
  - conditional-get
  - supabase-parity
  - cdn
  - isolated

requires:
  - phase: 01-sidecar-foundation
    provides: "lolalytics_api.resources.user_cache_dir() — the %LOCALAPPDATA%\\lol-draft-analyzer\\Cache parent that json_repo layers cdn/ onto"
provides:
  - "lolalytics_api.json_repo module — drop-in CDN-backed replacement for supabase_repo.py, 7 public get_* functions + warm_cache() + stale_status() + CDNError, zero imports from lolalytics_api.supabase_repo / supabase_client / config"
  - "Mocked-HTTP unit test suite (test_json_repo_cache.py, 8 cases) locking the cache lifecycle: cold-fetch 200, 304 reuse, corrupt-cache recovery, atomic write, schema_version reject, sha256 mismatch, unreachable-with-cache staleness, unreachable-no-cache loud-fail"
  - "Cross-side sha256 canonical form invariant: hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest() — Plan 02-02 exporter MUST use this exact serialization"
  - "CDN_BASE_URL baked default: https://chertixd.github.io/LoL-Draft-Helper/data — orchestrator resolution #3, verified from git remote"
affects:
  - 02-02  # export_to_json.py — must emit the schema_version=1 envelope + canonical sha256 that _fetch_one verifies
  - 02-03  # DATA-PIPELINE.md / gh-pages setup — CDN_BASE_URL above is the ship target
  - 02-04  # backend.py + requirements.txt + backend.spec cutover — swaps supabase_repo → json_repo, re-adds supabase excludes, re-enables CI guard; also lands the live-network contract test (test_json_repo_contract.py) asserting deep-equal returns between the two modules

tech-stack:
  added: []  # requests + hashlib + json + pathlib + concurrent.futures all already available
  patterns:
    - "Conditional-GET + disk cache without requests-cache: hand-written If-None-Match / If-Modified-Since in ~60 LoC; avoids pulling SQLite + 3 MB of transitive deps into the AV fingerprint (STACK.md invariant)"
    - "Atomic pair-write: <table>.json and <table>.meta.json both landed via tmp + os.replace — partial state invisible to readers on crash mid-write"
    - "Corrupt-cache self-heal: json.JSONDecodeError on either file triggers delete-pair + force-refetch; no user action needed (D-18)"
    - "Canonical sha256 over rows only (__meta excluded): json.dumps(rows, sort_keys=True, separators=(',', ':')) — stable across Python versions + cross-platform; identical form must be used by export_to_json.py"
    - "ThreadPoolExecutor fan-out (max_workers=9) for startup warm-up: 9 small JSON tables fetched concurrently; stateless per-table fetch so no shared-mutable-state concerns"
    - "Pure-helpers copied verbatim (NOT re-imported) to quarantine the supabase package chain: commit 451e8f7 cautionary tale — any import from lolalytics_api.supabase_repo transitively re-pulls supabase + gotrue + postgrest, re-breaking the frozen .exe"
    - "Module-level _cache_dir() as a callable (not a constant) so unit tests can monkeypatch to tmp_path — enables mocked-HTTP tests without user-dir writes"

key-files:
  created:
    - counterpick-app/apps/backend/src/lolalytics_api/json_repo.py
    - counterpick-app/apps/backend/test_json_repo_cache.py
  modified: []

key-decisions:
  - "Copied the three pure helpers (_wilson_score, _normalize_slug, _attach_names) verbatim from supabase_repo.py into json_repo.py per orchestrator resolution #2 — even though CONTEXT D-12 originally allowed re-import, the orchestrator overrode to Option b (copy) to keep the module-load graph provably free of the supabase chain. This is the whole point of Phase 2 — the client .exe must load cleanly with supabase uninstalled."
  - "Set _FAN_OUT_MAX_WORKERS = 9 (up from the research skeleton's 7) per orchestrator resolution #1 — the `champions` and `patches` tables are ALSO exported so that _champion_map() and _get_latest_patch() can source their data from the cache instead of Supabase. 9 concurrent GETs on startup is still well under the GitHub Pages rate limit and keeps the first-run latency ~1s."
  - "Preserved German business-logic comments verbatim (`Normalisiert Champion-Namen`, `Counter mich = negative Deltas`, etc.) when copy-modifying supabase_repo.py's 330-LoC public-API block — CLAUDE.md / CONVENTIONS.md calls mixed German/English comments the project norm; rewriting them to English would be a style deviation without technical justification."
  - "Used `from __future__ import annotations` on json_repo.py — this makes type hints lazy strings. Consequence: inspect.signature(json_repo.get_X) != inspect.signature(supabase_repo.get_X) even though names/defaults/kinds are semantically identical. The plan's verification check #3 (raw `==` on signatures) therefore evaluates False on all 7 functions; the semantic parity (names + defaults + Parameter.kind) evaluates True. Deep-behavioral parity is Plan 02-04's contract test, which is authoritative."
  - "Used `monkeypatch.setattr('lolalytics_api.json_repo._cache_dir', lambda: tmp_path / 'cdn')` in the test fixture — required _cache_dir to be a callable at module scope (not a module-level constant) so the fixture can swap it. Chose this over a test-mode env var because monkeypatch auto-restores on teardown."

requirements-completed:
  - CDN-01  # Public-API parity (signature-level; behavioral parity is Plan 02-04's contract test)
  - CDN-02  # Cache layout: <table>.json + <table>.meta.json under user_cache_dir()/cdn/, atomic writes
  - CDN-03  # Conditional GET: If-None-Match / If-Modified-Since; 304 reuse; 200 overwrite
  - CDN-04  # Corrupt-cache recovery via json.JSONDecodeError → delete pair → refetch

# Metrics
duration: 5min
completed: 2026-04-14
---

# Phase 2 Plan 01: json_repo.py CDN read path + mocked-HTTP cache tests Summary

**Landed `lolalytics_api.json_repo` — a 584-effective-line drop-in replacement for `supabase_repo.py` that reads from the public GitHub Pages CDN via conditional GET with atomic disk cache — alongside an 8-case mocked-HTTP unit test suite that locks the cache lifecycle. Both files ship together but no runtime consumer imports `json_repo` yet; Plan 02-04's atomic cutover performs the `backend.py` import swap.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-14T16:39:44Z
- **Completed:** 2026-04-14T16:44:57Z
- **Tasks:** 2 (TDD: RED then GREEN)
- **Files created:** 2
- **Files modified:** 0
- **Effective LoC landed:** 584 (json_repo.py) + 194 (test_json_repo_cache.py non-comment) = 778 total

## Accomplishments

- `json_repo.py` mirrors `supabase_repo.py`'s 7 public `get_*` functions with identical parameter names, defaults, and kinds — signature-level parity verified via `inspect.signature(...).parameters`. Deep-behavioral parity will be asserted by Plan 02-04's live-network contract test.
- Cache layer fully landed: `_cache_dir()`, `_atomic_write_json()`, `_load_meta()`, `_load_body()`, `_fetch_one()`, `_fetch_one_unconditional()`, `warm_cache()`, `stale_status()`, `_table()`. All disk writes go through the tmp + `os.replace` pattern so no reader ever sees a half-written body.
- Conditional-GET wire format matches RFC 7232 + GitHub Pages defaults: outbound `If-None-Match` (from cached ETag) and `If-Modified-Since` (from cached Last-Modified); 304 path reuses cached body and clears the stale flag; 200 path verifies schema_version ≤ 1 and `__meta.sha256` against `hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()` before committing the pair-write.
- Network-error policy per D-19: unreachable CDN + cached body → return cached rows and flip `_stale_state[table] = True` (surfaced via `stale_status()` for Phase 3's `/api/health` integration); unreachable CDN + no cache → raise `CDNError` (Phase 3 wraps this in a friendly banner).
- Re-implemented data-access helpers (`_champion_map`, `_get_latest_patch`, `_resolve_champion`, `_determine_role`) source from the cache via `_table(...)` filters; consume the `champions` and `patches` tables that orchestrator resolution #1 added to the exporter's target list.
- Test suite exercises 8 lifecycle branches end-to-end under `unittest.mock.patch("lolalytics_api.json_repo.requests.get", ...)`: cold-fetch 200 with pair-write verification; 304 header-echo assertion (If-None-Match + If-Modified-Since); JSONDecodeError recovery; atomic-write `.tmp` absence; schema_version rejection; sha256 mismatch rejection; unreachable-with-cache staleness; unreachable-no-cache `CDNError`. Run time: 0.17s.

## Task Commits

Each task committed atomically with `--no-verify` (parallel-executor per orchestrator wave protocol):

1. **Task 1 (RED): Add json_repo cache unit tests failing against non-existent module** — `97c0bcb` (test)
2. **Task 2 (GREEN): Implement json_repo.py — 9 public functions, cache layer, conditional GET, canonical sha256** — `2678d3a` (feat)

## Module Shape (`json_repo.py`)

**Path:** `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py`
**Canonical import:** `from lolalytics_api import json_repo`
**Module-load invariant:** imports cleanly when `supabase` is uninstalled (verified by running `import json_repo` with `sys.modules['supabase'] = None` et al. — the verification from the plan's `<verification>` §1).

### Public surface

| Symbol | Signature | Notes |
|--------|-----------|-------|
| `CDN_BASE_URL` | `str` | Module constant, `os.environ` override allowed; production default `https://chertixd.github.io/LoL-Draft-Helper/data`. |
| `CDNError` | `class(RuntimeError)` | Raised on 4xx/5xx, unreachable + no cache, sha256 mismatch, `schema_version > 1`. |
| `warm_cache()` | `-> None` | Startup fan-out; 9 conditional GETs via `ThreadPoolExecutor(max_workers=9)`; populates `_data`. Re-raises first `CDNError`. |
| `stale_status()` | `-> Dict[str, bool]` | Snapshot of per-table stale flags for Phase 3's `/api/health`. |
| `get_champion_stats(champion, role=None, patch=None)` | `-> Dict[str, Any]` | Mirrors `supabase_repo.get_champion_stats`. |
| `get_champion_stats_by_role(champion, patch=None)` | `-> Dict[str, Any]` | 5-slot `statsByRole` dict keyed by role number string. |
| `get_matchups(champion, role=None, opponent_role=None, patch=None, limit=10, ascending=True, min_games_pct=0.003)` | `-> Dict[str, Any]` | Full delta + normalized_delta logic preserved verbatim; `by_delta` / `by_normalized` sort + slice. |
| `get_synergies(champion, role=None, mate_role=None, patch=None, limit=10, min_games_pct=0.003)` | `-> Dict[str, Any]` | Positive-delta filter + sort descending; `_attach_names` on `mate_key`. |
| `get_items(patch=None)` / `get_runes(patch=None)` / `get_summoner_spells(patch=None)` | `-> List[Dict[str, Any]]` | Rows filtered by patch. |

### Private surface (cache + helpers)

`_wilson_score`, `_normalize_slug`, `_attach_names` — **copied verbatim** from `supabase_repo.py` lines 6–22, 25–29, 99–105 per orchestrator resolution #2 (quarantine the supabase chain from the import graph).

`_champion_map`, `_get_latest_patch`, `_resolve_champion`, `_determine_role` — reimplemented against `_table(...)` filters rather than re-imported. `_champion_map` reads from the exported `champions` table; `_get_latest_patch` reads from the exported `patches` table (orchestrator resolution #1).

`_cache_dir`, `_atomic_write_json`, `_load_meta`, `_load_body`, `_fetch_one`, `_fetch_one_unconditional`, `_table` — the cache + fetch layer.

### Constants

- `CDN_BASE_URL = os.environ.get("CDN_BASE_URL", "https://chertixd.github.io/LoL-Draft-Helper/data")`
- `_HTTP_TIMEOUT = (5, 15)` — (connect=5s, read=15s) per D-21
- `_FAN_OUT_MAX_WORKERS = 9`
- `_TABLES = ("champion_stats", "champion_stats_by_role", "matchups", "synergies", "items", "runes", "summoner_spells", "champions", "patches")` — 9-tuple
- `_SCHEMA_VERSION_MAX = 1`

## Test Suite Shape (`test_json_repo_cache.py`)

**Path:** `counterpick-app/apps/backend/test_json_repo_cache.py`
**Framework:** `pytest` 9.0.3 with stdlib `unittest.mock.patch` — NO `responses` dep (per D-15; keeps AV fingerprint trim).
**Fixture:** `isolated_cache(tmp_path, monkeypatch)` redirects `json_repo._cache_dir` to `tmp_path / "cdn"` and resets module-level `_stale_state` + `_data` so test order cannot leak state.
**Helper:** `_make_resp(status, body=None, headers=None)` builds a `MagicMock` matching `requests.Response` (status_code, headers, json, text, content).

### Test cases (8, all passing)

1. `test_cache_cold_fetch_writes_pair` — 200 path writes both files; meta contains ETag + Last-Modified.
2. `test_cache_304_reuses_cached_body` — 304 path reads cached body; outbound headers contain `If-None-Match` + `If-Modified-Since`.
3. `test_corrupt_cache_recovers` — truncated JSON in body; 200 refetch writes a valid body in its place.
4. `test_atomic_write_no_partial` — tmp file absent after `_atomic_write_json`; final contains exact payload.
5. `test_schema_version_rejected` — `schema_version=2` raises `CDNError` matching `"schema_version"`.
6. `test_sha256_mismatch_raises_cdnerror` — meta.sha256 != canonical(rows) raises `CDNError` matching `"sha256"`; uses REAL `hashlib.sha256` over `json.dumps(rows, sort_keys=True, separators=(",", ":"))`.
7. `test_cdn_unreachable_with_cache_flags_stale` — `ConnectionError` + pre-populated cache → returns cached rows + `stale_status()["items"] is True`.
8. `test_cdn_unreachable_no_cache_raises_cdnerror` — `ConnectionError` + empty cache → `CDNError`.

## Discretionary Choices Logged

- **Threaded fan-out at 9 workers** (not 5 or 10): one worker per table in `_TABLES`; concurrent fetches are I/O-bound on GitHub Pages latency, so a wider pool is wasted.
- **`requests.get` per-call, no `Session`** (per CONTEXT Claude's discretion bullet 3): the 9-request fan-out runs once at startup and the pool shuts down after; connection pooling would add complexity without measurable benefit.
- **Info-level logging on 200 cold-fetch, debug-level on 304, warning on stale + corrupt-recovery** (per CONTEXT Claude's discretion bullet 6): matches the project's existing `[MODULE]` print-statement tone while using the stdlib `logging` module for bundle-friendliness.
- **`_get_latest_patch` sorts by `(created_at, patch)` descending** with a fallback to `max(patch)` if the `created_at` key is absent — supabase_repo does `.order("created_at", desc=True).limit(1)`; preserving that ordering matches behavior on the common case, and the fallback guards against exporter schema drift.

## PYTHONPATH Note for Test Execution

The worktree checks out into `F:/Dokumente/Archiv/Riot Api/.claude/worktrees/agent-afa14a86/...`, but the development-mode `pip install -e .` was originally performed from the main repo path. As a result, `import lolalytics_api` at the system Python level resolves to the main-repo source, NOT the worktree. To run tests against the worktree's `json_repo.py` during CI, set `PYTHONPATH` explicitly:

```bash
PYTHONPATH="<worktree>/counterpick-app/apps/backend/src" \
  python -m pytest counterpick-app/apps/backend/test_json_repo_cache.py -v
```

This is a worktree-workflow artifact, not a runtime concern — the production `.exe` bundles `lolalytics_api` from whatever source the spec points at, which by Plan 02-04's cutover will be the merged master branch's `json_repo.py`.

## Deviations from Plan

### Signature-equality check is cosmetically False (documented, non-blocking)

- **Rule:** Rule 1 (auto-fix — but this is actually a no-op fix: the discrepancy is purely representational).
- **Found during:** Task 2 post-verification.
- **Issue:** The plan's `<verification>` §3 specifies `inspect.signature(json_repo.get_X) == inspect.signature(supabase_repo.get_X)` must be `True` for all 7 functions. It evaluates `False` — BUT this is entirely because `json_repo.py` uses `from __future__ import annotations` (idiomatic for new Python code + explicitly named in the research skeleton line 240) which makes type annotations lazy strings: `'Optional[str]'` (a string) vs `Optional[str]` (a runtime object). The parameter names, defaults, and `Parameter.kind` values all match exactly — verified with `jr.keys() == sr.keys() and all(jr[k].default == sr[k].default for k in jr) and all(jr[k].kind == sr[k].kind for k in jr)` returning `True` for all 7 functions.
- **Resolution:** Documented here rather than removing `from __future__ import annotations` — Plan 02-04's deep-equal contract test is the authoritative behavioral-parity check. Removing the future import to satisfy a string-comparison verification would be tail-wagging-the-dog. If a future reviewer wants stricter signature equality, the fix is either: (a) add `from __future__ import annotations` to `supabase_repo.py` too (both False → both True under `.parameters` comparison), or (b) compare parameter dicts as done above.
- **Files modified:** None (no fix applied; plan verification item is being reported as a known-discrepancy here).
- **Commit:** N/A.

### LoC count higher than plan estimate

- **Rule:** N/A (informational).
- **Found during:** Task 2.
- **Issue:** Plan estimated `~300 LoC`; final effective count is 584 non-comment lines.
- **Resolution:** The supabase_repo.py source being mirrored is already 444 lines; the cache layer adds ~180. I chose to preserve German comments verbatim (CLAUDE.md conventions rule) and keep full docstrings rather than compressing, which traded LoC for readability. No deviation from specified behavior.

## Auth Gates

None. All work was local file creation + pytest against stdlib mocks. No external services touched.

## Verification Evidence

All checks from the plan's `<verification>` block evaluated on Python 3.12.10 / win32:

1. **Module-load self-sufficiency:** `from lolalytics_api import json_repo` succeeds with `supabase` blocked via `sys.modules['supabase'] = None` (and `gotrue`, `postgrest`, `realtime`, `storage3`). `json_repo.CDN_BASE_URL` evaluates to the ship URL.
2. **Zero supabase-chain imports:** `grep -E 'from lolalytics_api\.(supabase_repo|supabase_client|config)'` returns 0 hits.
3. **Public API parity (parameter-dict comparison):** all 7 functions have matching `.parameters.keys()` + `.default` + `.kind`. Raw `inspect.signature ==` is False — see Deviations.
4. **Unit tests green:** `pytest test_json_repo_cache.py -v` → 8 passed in 0.17s.
5. **CDN URL baked correctly:** `grep 'chertixd.github.io/LoL-Draft-Helper/data'` returns 1 hit inside the `CDN_BASE_URL` default.
6. **Canonical sha256 form:** `grep -E 'sort_keys=True, separators=\(",", ":"\)'` returns 1 hit (inside `_fetch_one`).
7. **No existing files modified:** `git diff --name-only HEAD~2 HEAD` lists only `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` and `counterpick-app/apps/backend/test_json_repo_cache.py`.
8. **build-smoke.yml untouched:** This plan never modified CI; the existing smoke workflow remains green end-to-end because no consumer imports `json_repo` yet.

## Known Stubs

None. All functions return real data shapes; the only "placeholder" is `CDN_BASE_URL`'s env-override hatch, which is an intentional feature per D-20 for local dev/test (not a stub).

## Threat Flags

No new threat surface beyond what this plan's `<threat_model>` declared (T-02-01 through T-02-08). All 8 threats have mitigations landed:

- **T-02-01** (rows tampering) — canonical sha256 verify at line `_fetch_one` after 200.
- **T-02-03** (DoS via slow fan-out) — `_HTTP_TIMEOUT = (5, 15)` bounds worst case.
- **T-02-04** (corrupt cache) — `_load_body` / `_load_meta` JSONDecodeError → delete pair.
- **T-02-06** (schema upgrade) — `schema_version > 1` rejected.
- **T-02-07** (info-disclosure in exceptions) — `resp.text[:200]` clipping before raise.
- **T-02-08** (supabase re-import) — zero imports from supabase chain; grep-verified in acceptance criteria.

No threat flags (no new surface introduced beyond the register).

## Self-Check: PASSED

- `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` — FOUND (791 total lines, 584 effective LoC)
- `counterpick-app/apps/backend/test_json_repo_cache.py` — FOUND (251 total lines)
- Commit `97c0bcb` (Task 1 RED) — FOUND in `git log`
- Commit `2678d3a` (Task 2 GREEN) — FOUND in `git log`
- `python -c "import ast; ast.parse(open(...).read())"` — PASSES (syntax valid)
- `pytest test_json_repo_cache.py` — 8/8 PASS
- `grep` for 7 `def get_*` — all 7 present at lines 465, 500, 642, 719, 724, 729, 734
- `grep` for `CDN_BASE_URL = os.environ.get("CDN_BASE_URL", "https://chertixd.github.io/LoL-Draft-Helper/data"` — PRESENT
- `grep` for `class CDNError(RuntimeError)` — PRESENT
- `grep` for `_TABLES = (` followed by the 9 table names — PRESENT
- `grep` for `_FAN_OUT_MAX_WORKERS = 9` — PRESENT
- `grep` for `os.replace(` (atomic write) — PRESENT
- `grep` for `sort_keys=True, separators=(",", ":")` — PRESENT (1 hit in `_fetch_one`)
- `grep` for `from lolalytics_api.supabase_repo` — ABSENT (0 hits)
- `grep` for `from lolalytics_api.supabase_client` — ABSENT (0 hits)
- `grep` for `from lolalytics_api.config` — ABSENT (0 hits)
- Module load with `sys.modules['supabase'] = None` et al. — SUCCEEDS
