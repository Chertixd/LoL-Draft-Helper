# ETL Supabase Removal — Design

**Date:** 2026-05-03
**Status:** Approved, ready for implementation plan
**Phase:** 1 of 3 (Phase 2: CDN host migration to R2; Phase 3: tier as configurable parameter)

## Goal

Remove Supabase as the intermediate stage in the nightly ETL. The new pipeline reads Lolalytics' API directly, computes the canonical envelope in TypeScript, and publishes JSON files to GitHub Pages — exactly as the client (`apps/backend/src/lolalytics_api/json_repo.py`) consumes them today.

Supabase is currently a one-step buffer between the ETL writer and the JSON exporter. No other consumer reads from it. The Free tier (500 MB) is full, and adding a row of historical patches makes the cost grow with no functional benefit.

## Locked Decisions

- **Patch retention:** current patch + previous patch (covers the 14-day requirement; new patches release every 14 days, the new patch's first week has low Lolalytics sample size and the previous patch acts as fallback).
- **Language:** TypeScript only. The Python exporter is replaced.
- **CDN host:** GitHub Pages with `peaceiris/actions-gh-pages@v4` and `force_orphan: true`. Migration to R2 is a separate phase.
- **Lolalytics tier:** `emerald_plus` remains hardcoded. Making tier configurable is a separate phase.
- **Cutover model:** Direct cutover. Supabase data and credentials remain frozen (cold backup) for 2-3 weeks post-cutover, then deleted.
- **Atomicity:** All changes ship in a single PR on `main`. Rollback is `git revert` + push (≤5 min).

## Out of Scope

- CDN host migration (R2, Cloudflare Pages, etc.)
- Making `tier`, `region`, or `queue` configurable
- New data fields or schema changes
- Frontend or backend (Tauri app) code changes
- Renaming `supabase-dataset-updater/` (cosmetic, follow-up PR)

## Success Criteria

1. Nightly cron at 12:00 UTC runs the new pipeline successfully without `SUPABASE_*` env vars.
2. Output JSON files are byte-identical to a reference snapshot captured the day of the cutover.
3. Live `https://chertixd.github.io/lol-draft-helper-cdn/data/` continues serving the 8 logical tables (`champions`, `patches`, `items`, `runes`, `summoner_spells`, `champion_stats`, `matchups_<patch>`, `synergies_<patch>` × 2 patches).
4. The Tauri app (installed clients) reads CDN content with no `sha256 mismatch` errors.
5. CI gates (golden-test, typecheck, unit tests) prevent any future merge that would break byte-identity.

---

## Pipeline (production cron run)

```
Step 1: Patch Detection
  GET ddragon.leagueoflegends.com/api/versions.json
  current = versions[0]    (e.g. "16.8.1")
  previous = versions[1]   (e.g. "16.7.1")

Step 2: Previous-Patch Restore (CDN-roundtrip)
  GET CDN/matchups_<previous>.json
  GET CDN/synergies_<previous>.json
  Verify embedded __meta.sha256 against re-computed sha256 of rows.
  Write to ./public/data/.

  - 404 (first run, or previous already aged out) → soft-fail, continue
  - sha256 mismatch → hard-fail, abort entire run

Step 3: Current-Patch Scrape (Lolalytics API)
  For each champion × each of 5 lanes:
    getLolalyticsQwikChampion(current, championId, lane)
    getLolalyticsQwikChampion2(current, championId, lane)
  hasAnyUsableRole gate (existing): if no champion has usable role data, abort.
  In-memory rows: champion_stats, matchups, synergies.

Step 4: Global Tables (Riot Data Dragon)
  GET ddragon CDN: champions, items, runes, summoner_spells.
  Plus: patches list = [current, previous] (filtered by retention rule).

Step 5: Canonical Write
  For each output table:
    canonicalStringify(rows) → bytes
    sha256(bytes) → hash
    wrap into __meta envelope (exported_at, sha256, row_count, schema_version, source_table)
    write to ./public/data/<table>.json

Step 6: Self-Check (Safety Layer 2)
  For each ./public/data/*.json:
    re-stringify rows, recompute sha256, compare against __meta.sha256.
  Any mismatch → workflow exit 1 BEFORE the gh-pages publish step.

Step 7: gh-pages Publish (peaceiris, unchanged)
  publish_dir: ./supabase-dataset-updater/public
  external_repository: Chertixd/lol-draft-helper-cdn
  publish_branch: gh-pages
  force_orphan: true   ← orphan branch, no history bloat

Step 8: Smoke-Test (Safety Layer 3)
  After 30s sleep (edge cache propagation), 3 retries with 30s spacing:
    For each of the 8+previous_count files:
      GET https://chertixd.github.io/lol-draft-helper-cdn/data/<file>
      Verify __meta.sha256 matches what we just wrote.
  Mismatch → workflow exit 1 (CDN is now corrupted, alert the operator).
```

### Atomicity guarantees

- If any step fails before Step 7, the live CDN is unchanged (yesterday's content stays valid).
- If Step 8 fails, the CDN is in a broken state but we get a loud signal immediately. Manual remediation: revert PR, next cron run rewrites CDN with old pipeline (Supabase frozen as backup).
- `force_orphan: true` means each push fully replaces the gh-pages branch — there is no "partial" state where some files are old and others are new.

### Idempotency

Same Lolalytics inputs at the same wall-clock minute produce byte-identical outputs except `__meta.exported_at` (ISO timestamp). The `__meta.sha256` hash is computed over `rows` only, not over the envelope, so timestamp-only diffs do not invalidate signatures.

---

## Code Structure

### `supabase-dataset-updater/src/`

```
lolalytics/                  [unchanged]
├── qwik.ts
├── qwik-champion2.ts
├── roles.ts
└── index.ts                 ← cartesian-product fix preserved (commit 4b77502)

riot.ts                      [unchanged — Data Dragon client]
utils.ts                     [unchanged]
models/                      [unchanged]

canonical-stringify.ts       [NEW · ~80 LOC] ⚠ critical
└── canonicalStringify(value): Uint8Array
    Byte-identical to Python json.dumps(sort_keys=True, separators=(",",":"))
    .encode("utf-8"). Built on safe-stable-stringify with extra
    validation for floats, unicode, integer keys.

envelope.ts                  [NEW · ~50 LOC]
├── wrapWithEnvelope(table, rows, schema_version, exported_at): EnvelopedTable
└── serialize(envelope): Uint8Array      ← computes sha256, embeds in __meta

cdn-fetcher.ts               [NEW · ~80 LOC]
├── fetchPreviousPatchFiles(cdnUrl, patch): Promise<Map<file, Buffer> | null>
└── verifyEnvelopeIntegrity(buffer): boolean
    404 → null (soft-fail)
    sha256 mismatch → throw (hard-fail)

writer.ts                    [NEW · ~150 LOC]
└── writeOutputs(outDir, tables, currentPatch, previousPatch): Promise<void>

self-check.ts                [NEW · ~50 LOC]   ← Safety Layer 2
└── verifyAllOutputs(outDir): Promise<void>

smoke-test.ts                [NEW · ~50 LOC]   ← Safety Layer 3
└── verifyLiveCdn(cdnUrl, expected): Promise<void>

etl.ts                       [REWRITTEN from supabase-etl.ts · ~200 LOC]
└── main(): orchestrates Steps 1-6. No business logic — pure orchestration.
```

### `supabase-dataset-updater/tests/`

```
canonical-stringify.test.ts  ── 50+ golden cases vs Python fixtures
envelope.test.ts              ── envelope format integrity
golden.test.ts                ── full pipeline vs frozen Supabase snapshot
fixtures/
├── golden-snapshot/          ── today's CDN content, 8 files (frozen reference)
├── lolalytics-responses/     ── ~850 raw API responses captured at snapshot time
├── riot-responses/           ── ~10 Data Dragon responses
└── stringify-cases.json      ── canonical-stringify edge cases
```

### Module boundaries (data flow)

```
                ┌──────────────────────────────────────┐
                │         etl.ts (orchestrator)         │
                └──────────────────────────────────────┘
                     │            │              │
                     ▼            ▼              ▼
            ┌──────────────┐ ┌──────────┐ ┌──────────────┐
            │ lolalytics/  │ │ riot.ts  │ │ cdn-fetcher  │
            └──────────────┘ └──────────┘ └──────────────┘
                     │            │              │
                     └────────────┼──────────────┘
                                  ▼
                          in-memory rows
                                  │
                                  ▼
                         ┌──────────────┐
                         │ envelope.ts  │ ← uses canonical-stringify
                         └──────────────┘
                                  │
                                  ▼
                         ┌──────────────┐
                         │  writer.ts   │
                         └──────────────┘
                                  │
                                  ▼
                         ┌──────────────┐
                         │ self-check   │ ← Safety Layer 2
                         └──────────────┘
                                  │
                                  ▼
                            gh-pages push
                                  │
                                  ▼
                         ┌──────────────┐
                         │ smoke-test   │ ← Safety Layer 3
                         └──────────────┘
```

### Files deleted

```
supabase-dataset-updater/scripts/__init__.py
supabase-dataset-updater/scripts/export_to_json.py        (270 LOC)
supabase-dataset-updater/scripts/test_export_to_json.py   (~100 LOC)
supabase-dataset-updater/scripts/                         (empty dir)
supabase-dataset-updater/requirements-dev.txt
supabase-dataset-updater/src/supabase-etl.ts              (replaced by etl.ts)
```

### `supabase-dataset-updater/scripts/capture-golden.ts` (one-shot)

A pre-cutover script: hits live Lolalytics + Riot APIs, captures all responses to `tests/fixtures/lolalytics-responses/` and `tests/fixtures/riot-responses/`. Pulls today's CDN content into `tests/fixtures/golden-snapshot/`. Run once before the migration PR is merged. The fixtures are committed and locked — the golden test never re-captures them.

### Net code delta

- Removed: ~370 LOC Python (`scripts/*.py` + tests)
- Added: ~660 LOC TypeScript (modules + tests)
- Net: +290 LOC — but with stricter typing, more test coverage, single language, clear module boundaries.

---

## Safety Stack (4 layers, all mandatory)

### Layer 1 — CI Golden Test (pre-merge)

**Workflow:** `.github/workflows/etl-test.yml` (NEW) on PRs that touch `supabase-dataset-updater/**`.

```yaml
- run: pnpm install
- run: pnpm typecheck
- run: pnpm test                  # canonical-stringify, envelope (fast)
- run: pnpm test:golden           # full-pipeline vs frozen snapshot (slow)
```

The golden test mocks `fetch` to return the frozen Lolalytics + Riot fixtures, runs the new pipeline, and asserts byte-equality against `tests/fixtures/golden-snapshot/`.

**Failure mode:** PR red, no merge.

**What it catches:** the migration is broken from day one; canonical-stringify drifted from Python's output; envelope format changed; pipeline orchestration is wrong.

### Layer 2 — Self-Check (post-write, pre-push)

Inside the production workflow, after `etl.ts` writes files but before `peaceiris` publishes them:

```typescript
for (const file of glob('public/data/*.json')) {
  const parsed = JSON.parse(readFileSync(file));
  const claimed = parsed.__meta.sha256;
  const computed = sha256(canonicalStringify(parsed.rows));
  if (claimed !== computed) throw new Error(`sha256 mismatch in ${file}`);
}
```

**Failure mode:** workflow `exit 1`. CDN unchanged. Cron retries tomorrow.

**What it catches:** subtle drift introduced after merge (library upgrade, new edge case in production data that fixtures didn't cover).

### Layer 3 — Smoke Test (post-push)

After `peaceiris` succeeds, fetch the live CDN content and verify it matches what we just wrote. 3 retries with 30 s spacing for GitHub Pages edge propagation.

**Failure mode:** workflow exit 1. CDN is already broken — this is the alert mechanism, not prevention.

**What it catches:** push mechanics (action bug, GitHub Pages cache), concurrent manual deploys.

### Layer 4 — Atomic PR

Migration ships as one PR with one squash commit. Rollback is `git revert <commit> && git push`. Supabase data, secrets, and project remain frozen for 2-3 weeks. The next cron run re-activates the old pipeline immediately.

**What it catches:** anything Layers 1-3 missed. Cost of failure capped at ≤5 minutes of operator time.

---

## Critical Risk: canonical-stringify byte-identity

This is the single point of failure for the entire migration. If `canonicalStringify` drifts from Python's `json.dumps(sort_keys=True, separators=(",",":")).encode("utf-8")` even by one byte, every installed client reads `sha256 mismatch` and refuses to load the data.

**Mitigations** (all required):

- **Golden test against Python fixtures:** A small Python script in `tests/fixtures/` generates expected outputs for 50+ edge cases (empty array, empty object, null, true/false, integer keys requiring string-sort, floats including `0.30000000000000004`, unicode emojis and combining characters, RTL text, deeply nested structures, large strings >1 MB, large arrays >10 000 entries). The TS test asserts exact byte equality.
- **Property-based fuzzing (optional):** 100+ random inputs generated by the test, run through both Python and TS, byte-compared.
- **Schema validation at ingestion:** in `lolalytics/qwik.ts`, validate Lolalytics responses against the expected type before passing to the canonical stringifier — a malformed response should fail fast at the boundary, not silently corrupt downstream data.
- **`hasAnyUsableRole` gate preserved:** existing safeguard from commit `4b77502` ensures we don't publish a usable-but-empty pipeline output if Lolalytics is down or returning low-sample data.

---

## Workflow Changes

### `.github/workflows/update-dataset.yml` (production cron)

Removed:

- "Setup Python 3.12 for export"
- "Install Python deps for export"
- "Export Supabase tables to JSON"
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` env vars on the ETL step

Renamed and simplified:

```yaml
- name: Run ETL                            # was "Update Supabase dataset"
  working-directory: supabase-dataset-updater
  run: pnpm update                          # script name unchanged, code different
  env:
    CDN_BASE_URL: https://chertixd.github.io/lol-draft-helper-cdn/data
```

Added:

```yaml
- name: Self-check outputs (Layer 2)
  working-directory: supabase-dataset-updater
  run: pnpm self-check

# (peaceiris/actions-gh-pages step unchanged)

- name: Smoke-test live CDN (Layer 3)
  working-directory: supabase-dataset-updater
  run: pnpm smoke-test
  env:
    CDN_BASE_URL: https://chertixd.github.io/lol-draft-helper-cdn/data
```

Net step count: 9 → 7. Python setup time saved (~15 s/run).

### `.github/workflows/etl-test.yml` (NEW pre-merge gate)

Triggers on `pull_request` targeting `supabase-dataset-updater/**`. Runs typecheck + fast tests + golden test. Required to be green before merge.

### `supabase-dataset-updater/package.json`

```jsonc
{
    "version": "2.0.0",                          // major bump (architecture Δ)
    "scripts": {
        "update":       "tsx src/etl.ts",
        "self-check":   "tsx src/self-check.ts public/data",
        "smoke-test":   "tsx src/smoke-test.ts public/data",
        "test":         "vitest run --exclude tests/golden.test.ts",
        "test:golden":  "vitest run tests/golden.test.ts",
        "test:capture": "tsx scripts/capture-golden.ts",
        "typecheck":    "tsc --noEmit"
    },
    "dependencies": {
        // removed: @supabase/supabase-js, dotenv
        "safe-stable-stringify": "^2.5.0",
        "tsx": "^4.21.0"
    },
    "devDependencies": {
        "@types/node": "^22.19.3",
        "typescript": "^5.9.3",
        "vitest": "^2.1.0",
        "memfs": "^4.15.0"
    },
    "packageManager": "pnpm@9.2.0"
}
```

### Repository secrets

| Secret | Action |
|---|---|
| `CDN_DEPLOY_TOKEN` | keep (peaceiris still needs it) |
| `SUPABASE_URL` | keep for 2-3 weeks (cold backup), then delete |
| `SUPABASE_SERVICE_ROLE_KEY` | keep for 2-3 weeks (cold backup), then delete |

---

## Local Development Workflow

```bash
cd supabase-dataset-updater
pnpm install              # node deps only, no pip
pnpm test                 # ~5 s
pnpm test:golden          # ~10 s
pnpm update               # ETL against live Lolalytics, writes ./public/data
pnpm self-check           # validates ./public/data
pnpm smoke-test           # validates live CDN (read-only HTTP)
```

To run the Tauri app against a local snapshot:

```bash
# in supabase-dataset-updater (after pnpm update):
python -m http.server 8000 --directory ./public/data &

# in counterpick-app:
CDN_BASE_URL=http://localhost:8000 pnpm tauri dev
```

The Tauri app reads from local files instead of the live CDN. No Supabase, no cloud account, fully reproducible offline.

---

## Edge Cases the 4 Layers Don't Catch

Documented for future awareness, not in scope for this phase:

- **Lolalytics changes its response schema.** Mocks lock the old schema; production hits new schema; pipeline writes corrupted-but-well-formatted JSON. Mitigation: schema validation in `lolalytics/qwik.ts` (fail fast at ingestion).
- **Lolalytics returns empty/low-sample data.** Pipeline produces clean but useless output. Mitigation: existing `hasAnyUsableRole` gate.
- **GitHub Pages edge propagation > 90 s** (3 retries × 30 s). False-positive smoke-test failure. Mitigation: extend retry count or sleep duration if observed in production.

---

## Definition of Done

- [ ] PR merged to `main`, CI green (typecheck, tests, golden test).
- [ ] First nightly cron after merge runs successfully end-to-end.
- [ ] Live CDN serves the same 8 logical tables, sha256-verified by smoke-test.
- [ ] Tauri app on a developer machine reads CDN content with no errors.
- [ ] After 2-3 weeks observation: Supabase secrets removed from GitHub repo settings; Supabase project paused or deleted.

---

*This design is the input to a writing-plans skill invocation that will produce a step-by-step implementation plan with TDD tasks, file-level diffs, and validation gates.*
