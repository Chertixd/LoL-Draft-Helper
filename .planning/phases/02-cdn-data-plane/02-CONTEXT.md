# Phase 2: CDN Data Plane — Context

**Gathered:** 2026-04-14
**Status:** Ready for planning
**Mode:** `--auto` (recommended defaults applied; each choice logged inline)

<domain>
## Phase Boundary

Phase 2 replaces the client's Supabase read path with a public GitHub Pages CDN. Two workstreams inside the phase:

1. **Server-side export** — a new `supabase-dataset-updater/scripts/export_to_json.py` runs after each nightly ETL and publishes the relevant tables as JSON to an orphan `gh-pages` branch; GitHub Pages serves them.
2. **Client-side read path** — a new `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` mirrors the public API of `supabase_repo.py` exactly, fetches from the CDN with conditional-GET caching in `user_cache_dir()/cdn/`, and replaces `supabase_repo` in `backend.py` so the bundled `.exe` no longer needs Supabase credentials.

After Phase 2 the installed client never talks to Supabase; `supabase-py` is removed from the runtime bundle; and the Phase 1 deferred AV guards (excludes + strings-grep in CI) are re-armed.

**In scope:**
- `export_to_json.py` + integration into the existing daily `update-dataset.yml` workflow
- Orphan `gh-pages` branch + GitHub Pages configuration (manual one-time setup, documented)
- `json_repo.py` with full 9-function public API, conditional-GET cache, atomic writes, corrupt-cache recovery
- Contract tests against live CDN
- `backend.py` import swap (`supabase_repo` → `json_repo`)
- `requirements.txt` supabase removal
- `backend.spec` re-adds the supabase excludes deferred from Phase 1
- `.github/workflows/build-smoke.yml` re-enables the "Verify supabase NOT in bundle" guard

**Out of scope for this phase:**
- Tauri host / frontend URL discovery / error-state UX (→ Phase 3)
- Hover-detection fix (→ Phase 3)
- Release pipeline, signed updater, `.msi` (→ Phase 4)
- Offline-first-run seed dataset (→ v1.1)
- Rearranging `gh-pages` layout beyond the spec §6.2 `data/<table>.json` scheme

</domain>

<decisions>
## Implementation Decisions

### Server-Side Export

- **D-01:** New script at `supabase-dataset-updater/scripts/export_to_json.py`. Python (not Node), same language as `backend.py` — shared mental model and easier contract parity with `json_repo.py`. Runtime depends on `supabase-py`, `python-dotenv`, stdlib `json`, stdlib `hashlib`. _[auto: Python parity with the consumer side is worth one more dependency in the ETL runner]_
- **D-02:** Export step is **appended to the existing** `supabase-dataset-updater/.github/workflows/update-dataset.yml` daily workflow — NOT a separate workflow. A single CI run does ETL → JSON export, which guarantees the CDN never lags the DB by more than a few minutes. _[auto: spec §6.2 intent; single failure mode is easier to reason about]_
- **D-03:** Target branch: orphan `gh-pages`. Each export rewrites the branch history via force-push (the branch is a content snapshot, not source code). `gh-pages` is independent of `main` so rollback is `git push --force origin <old-sha>:gh-pages`. _[auto: standard GitHub Pages pattern; preserves clean `main` history]_
- **D-04:** Tables to export: seed list from spec §6.2 = `champion_stats`, `champion_stats_by_role`, `matchups`, `synergies`, `items`, `runes`, `summoner_spells`. Actual list verified at implementation time by querying Supabase information_schema; any additions are logged in PLAN.md. _[auto: exact table list from spec §6.2]_
- **D-05:** JSON envelope per file (single top-level object):
  ```json
  {
    "__meta": {
      "exported_at": "2026-04-14T03:15:42.000Z",
      "sha256": "<hex-digest-of-rows-json>",
      "row_count": 172,
      "schema_version": 1
    },
    "rows": [ { ... }, { ... }, ... ]
  }
  ```
  `rows` field holds the array; downstream `json_repo.py` returns `body["rows"]` (matching `supabase_repo`'s return shape). `__meta.sha256` is computed over the canonical JSON serialization of the rows array, without the `__meta` field, so the client can verify integrity. _[auto: fixed schema avoids ambiguity; `schema_version` lets future migrations be explicit]_
- **D-06:** Authentication: `export_to_json.py` uses `SUPABASE_SERVICE_ROLE_KEY` from a GitHub Actions secret. The key never leaves CI; it is not logged. _[auto: standard service-role pattern; already used by the existing ETL]_
- **D-07:** Publish mechanism: the workflow step uses `peaceiris/actions-gh-pages@v4` (or a raw `git` commit + `push --force` flow) to publish `data/<table>.json` to the `gh-pages` branch. The action is well-maintained and widely used; the manual-git fallback is documented for when the action is unavailable. _[auto: action is simpler than inline git]_
- **D-08:** Export script layout: single file, one function per table (`export_champion_stats(client, out_dir)` etc.) orchestrated by a `main()`. ~150 LoC total. Error handling: a single table's failure aborts the entire run — partial CDN updates are not allowed. _[auto: atomic-or-nothing semantics match spec §6]_
- **D-09:** Local testing: the script accepts a `--out-dir` CLI flag (defaults to `./public` relative to repo root) so a developer can run it locally without pushing. Integration test checks the schema of each generated file. _[auto: testability]_

### Client-Side Read Path (`json_repo.py`)

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

### Backend Cutover (`backend.py` and `backend.spec`)

- **D-22:** Import swap in `backend.py` (one block, lines 11–21): `from lolalytics_api.supabase_repo import ...` → `from lolalytics_api.json_repo import ...`. All `sb_*` aliases renamed to `json_*` (or kept if semantic). The two lines importing `supabase_client` and `config.get_supabase_url` are removed. _[auto: spec §6.3]_
- **D-23:** Remove `supabase>=2.4.0` from `apps/backend/requirements.txt`. Phase 1 left it intact per N-03; Phase 2's cutover removes it because `json_repo.py` doesn't need it. `supabase_repo.py` stays in source (unused at runtime) for reference + for the contract tests that compare shapes. _[auto: spec §6.5]_
- **D-24:** Re-add to `backend.spec` excludes: `supabase`, `gotrue`, `postgrest`, `realtime`, `storage3`, `supabase_functions`, `supabase_auth`. These were dropped in Phase 1's late fix (`451e8f7`); Phase 2 restores them now that the import is gone. Bundle size shrinks ~5 MB. _[auto: completes the Phase 1 deferred resolution]_
- **D-25:** Re-enable the "Verify supabase NOT in bundle" CI guard in `.github/workflows/build-smoke.yml` (uncomment the block commented out in Phase 1). _[auto: completes the Phase 1 deferred resolution]_

### GitHub Pages Setup (one-time, documented)

- **D-26:** Concrete CDN URL: **must be finalized before Phase 2 ships**. Placeholder used during planning: `https://{GITHUB_USER}.github.io/{REPO_NAME}/data/`. Implementation plan MUST ask the user for the actual `GITHUB_USER` and `REPO_NAME` (or detect from `git remote -v`) before hardcoding. _[auto: flagged as open question for planner]_
- **D-27:** Branch setup: a new `docs/DATA-PIPELINE.md` documents the one-time `gh-pages` branch bootstrap (`git checkout --orphan gh-pages; git rm -rf .; ...`). After Phase 2 ships, the branch is maintained entirely by CI. _[auto: operator runbook]_
- **D-28:** GitHub Pages configuration: enable Pages with source = `gh-pages` branch, path = `/ (root)`. The `data/<table>.json` files live under `data/` per spec §6.2. This is a manual one-time action — not automatable via CLI without admin token. Documented in `DATA-PIPELINE.md`. _[auto: standard setup]_

### Contract Testing

- **D-29:** New test file `counterpick-app/apps/backend/test_json_repo_contract.py`: one test per public function, each running BOTH `supabase_repo.get_X(...)` and `json_repo.get_X(...)` with the same args and asserting deep-equal on the result (modulo ordering for list-of-dicts). Tests require live CDN + live Supabase access, so they run in the daily CI (after the export step lands new data) rather than per-commit. _[auto: spec §9 testing strategy; contract-equivalence is the whole point of the phase]_
- **D-30:** New unit test `test_json_repo_cache.py`: mocked HTTP, covering cache-hit (304), cache-cold (200), corrupt-cache recovery (`json.JSONDecodeError` path), atomic-write (tmp file exists during rename window), concurrent startup fan-out. _[auto: unit-level coverage, no network]_

### Scope Boundaries / Anti-Decisions

- **N-01:** No Tauri/Rust (Phase 3).
- **N-02:** No frontend changes — `apps/frontend/src/api/*` stays hardcoded to `http://localhost:5000`. Phase 3's `getBackendURL()` handles that.
- **N-03:** No hover-detection work (Phase 3).
- **N-04:** No Tauri updater, `.msi`, release workflow (Phase 4).
- **N-05:** No offline-first-run seed dataset (v1.1). Phase 2 has no first-run-offline UX — if the cache is empty and the CDN is unreachable, the backend fails loud. Phase 3 adds the retry UX.
- **N-06:** No manifest.json or `?v=<ts>` cache-busting (deferred; conditional GET is sufficient).

### Claude's Discretion

- Exact `concurrent.futures.ThreadPoolExecutor` max_workers value (5 vs 7 vs 10).
- Exact column ordering in `peaceiris/actions-gh-pages@v4` parameters.
- Whether to use `requests.Session()` pooling in `json_repo.py` vs. one-off `requests.get`.
- Whether contract tests run every PR or only daily (recommendation: daily due to network dependence).
- Whether `test_json_repo_cache.py` uses `responses` library for HTTP mocking vs. a custom `monkeypatch` shim (planner picks).
- Logging verbosity of cache hit/miss in `json_repo.py` (info-level on cold fetch, debug-level on 304).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Primary spec (source of truth)
- `docs/superpowers/specs/2026-04-14-delivery-form-design.md` §6 (Data Backend — Supabase → CDN Hybrid, Pattern C), §3 (Architecture diagram — data flow)

### Phase 1 outputs (direct upstream)
- `.planning/phases/01-sidecar-foundation/01-CONTEXT.md` — decisions D-14 (no `__file__` in runtime), D-15 (`LOL_DRAFT_APP_NAME`), N-03 (supabase import kept) — Phase 2 now removes the import, honoring the deferred cleanup
- `.planning/phases/01-sidecar-foundation/01-01-SUMMARY.md` — shipped `resources.py` with `user_cache_dir()` helper
- `.planning/phases/01-sidecar-foundation/01-02-SUMMARY.md` — shipped `backend.py` `main()` with CLI args
- Commit `451e8f7` (fix deferring supabase excludes) — restore the excludes in this phase

### Project-level
- `.planning/PROJECT.md` — Core Value, Constraints (Windows-only, no code signing)
- `.planning/REQUIREMENTS.md` — CDN-01 through CDN-08 mapped to this phase

### Research outputs
- `.planning/research/STACK.md` — `requests` + manual ETag cache (NOT `requests-cache`)
- `.planning/research/ARCHITECTURE.md` — `json_repo` function surface (verified against `supabase_repo.py`), cache topology
- `.planning/research/PITFALLS.md` — cache corruption (#18), schema drift (#19), stale CDN edge cache (#15), repo bloat on `gh-pages` (#17), ETL/export race (#16)
- `.planning/research/SUMMARY.md` — Phase 2 section, open questions 2/3/5/6 resolved inline in this CONTEXT

### Existing codebase (authoritative)
- `counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` — 9-function public API to mirror (the contract)
- `counterpick-app/apps/backend/src/lolalytics_api/supabase_client.py` — connection factory (to be unused after cutover)
- `counterpick-app/apps/backend/backend.py` lines 11–21 — import block to rewrite
- `counterpick-app/apps/backend/backend.spec` lines ~64–82 — excludes block to update
- `counterpick-app/apps/backend/requirements.txt` — remove `supabase>=2.4.0`
- `supabase-dataset-updater/.github/workflows/update-dataset.yml` — existing daily ETL workflow to extend with the export step
- `supabase-dataset-updater/src/supabase-etl.ts` — reference for how the ETL talks to Supabase (patch detection, table listings)
- `.github/workflows/build-smoke.yml` — re-enable the commented-out "Verify supabase NOT in bundle" step

### External
- GitHub Pages docs: <https://docs.github.com/en/pages/getting-started-with-github-pages>
- `peaceiris/actions-gh-pages@v4`: <https://github.com/peaceiris/actions-gh-pages>
- Supabase Python client: <https://supabase.com/docs/reference/python>
- PyPI `requests` conditional GET pattern: standard `If-None-Match` / `If-Modified-Since` headers

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (Phase 2 depends on)
- `counterpick-app/apps/backend/src/lolalytics_api/resources.py` — provides `user_cache_dir()` for `cdn/` subfolder
- `counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` — canonical public-API shape; helpers `_wilson_score`, `_normalize_slug`, `_determine_role`, `_attach_names` re-imported by `json_repo`
- `counterpick-app/apps/backend/backend.py` — import block at lines 11–21 is the swap target

### Established Patterns
- Python package via editable install (`pip install -e .` from `apps/backend/`) — new module auto-imports
- Pytest config in `pyproject.toml` — new test files picked up automatically
- CI workflows live under `.github/workflows/` in the repo root (not in sub-packages)

### Integration Points
- `.github/workflows/build-smoke.yml` line ~69 — the block commented out in Phase 1 commit `451e8f7`, re-enabled here
- `supabase-dataset-updater/.github/workflows/update-dataset.yml` — append a new `export_to_json` step after the existing ETL step
- GitHub Pages: must be enabled manually by the repo owner; document in `DATA-PIPELINE.md`

</code_context>

<specifics>
## Specific Ideas

- Force-push to `gh-pages` is deliberate — the branch is a CDN snapshot, not code history. History rewrites are a feature, not a bug.
- The `__meta.sha256` is belt-and-suspenders: GitHub Pages already serves over HTTPS, so TLS provides integrity. The sha256 protects against accidental cache corruption (disk error, interrupted download) and makes end-to-end tamper-detection possible if we ever sign the manifests.
- `schema_version: 1` in `__meta` is not purely cosmetic — Phase 2 clients reject `schema_version > 1`, so future breaking changes to the envelope can land without bricking old installs.
- The `concurrent.futures.ThreadPoolExecutor` fan-out is safe because `json_repo` functions are stateless — no shared mutable state across table fetches.
- `test_json_repo_contract.py` is the single test that actually proves `supabase_repo` and `json_repo` return the same data. Keep it maintained as the source-of-truth for API compatibility.

</specifics>

<deferred>
## Deferred Ideas

- **Seed dataset for offline-first-run** — v1.1.
- **Manifest-based cache-busting** (`manifest.json` with content hashes) — deferred. Conditional GET is sufficient for 7 small files.
- **Query-string cache-busting** (`?v=<exported_at>`) — deferred; same rationale.
- **CDN response signing** — Ed25519 signatures on the JSON envelope so a compromised GitHub account couldn't ship malicious data. Backlog. Currently we trust GitHub + TLS.
- **Moving `supabase_repo.py` out of source** — could be deleted in a later milestone once `json_repo` has been battle-tested. Phase 2 keeps it in source for reference + contract tests.
- **Rearranging `gh-pages` layout to drop the `data/` subfolder** — spec §6.2 pins `data/<table>.json`; not changing without a design discussion.
- **Parallel daily runs of ETL + export on different schedules** — single workflow is simpler for v1.

### Reviewed Todos (not folded)
None.

</deferred>

---

*Phase: 02-cdn-data-plane*
*Context gathered: 2026-04-14 (auto mode)*
