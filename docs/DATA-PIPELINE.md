# CDN Data Pipeline — Operator Runbook

**Last updated:** 2026-04-14 (Phase 2 shipped)
**Canonical repo:** Chertixd/LoL-Draft-Helper
**CDN base URL:** https://chertixd.github.io/LoL-Draft-Helper/data
**Schema version (current):** 1

This document is the single operator reference for the CDN data plane. Its target reader is the solo developer (you) returning six months from now and needing to bootstrap a fresh fork, rotate the `gh-pages` branch, roll back a bad export, or debug a GitHub Pages edge-cache miss.

## Contents

1. [Overview](#1-overview)
2. [One-time `gh-pages` bootstrap (D-27)](#2-one-time-gh-pages-bootstrap-d-27)
3. [GitHub Pages enablement (D-28) — **MANUAL OPERATOR ACTION**](#3-github-pages-enablement-d-28--manual-operator-action)
4. [Triggering the workflow](#4-triggering-the-workflow)
5. [Canonical sha256 form (pin this)](#5-canonical-sha256-form-pin-this)
6. [Rollback](#6-rollback)
7. [Schema version upgrade coordination (Pitfall #6)](#7-schema-version-upgrade-coordination-pitfall-6)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Overview

Supabase is the source of truth. The existing TypeScript ETL (`supabase-dataset-updater/src/supabase-etl.ts`) writes Supabase nightly. A new Python step (`supabase-dataset-updater/scripts/export_to_json.py`) then exports **8 Supabase tables to 16 JSON files** (per-patch sharding — see below) under `supabase-dataset-updater/public/data/`. `peaceiris/actions-gh-pages@v4` with `force_orphan: true` publishes that directory as the entire contents of the `gh-pages` branch. GitHub Pages serves it at `https://chertixd.github.io/LoL-Draft-Helper/data/<table>.json`. On the client, `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` issues conditional GETs (ETag / Last-Modified), verifies the `__meta.sha256` against a canonical serialization of the `rows`, and mirrors the payload into a local cache.

**Sharding note.** Six of the eight exported tables (`champion_stats`, `items`, `runes`, `summoner_spells`, `champions`, `patches`) ship as single `<table>.json` files. Two tables — `matchups` and `synergies` — exceed GitHub's push limits when shipped whole, so the exporter shards them per-patch as `matchups_<patch>.json` and `synergies_<patch>.json`, one file per patch in the `patches` table. The authoritative per-patch table list is the `PER_PATCH_TABLES` constant, declared identically in both `supabase-dataset-updater/scripts/export_to_json.py` (producer) and `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` (consumer). A mismatch on either side produces 404s on every fetch of the affected table.

With 5 active patches in production, the exporter currently produces 16 files: 6 single-file tables + (5 patches × 2 per-patch tables) = 16.

---

## 2. One-time `gh-pages` bootstrap (D-27)

Run these exact commands on a fresh clone of the repo (adjust `master` below if your default branch is `main`):

```sh
git checkout --orphan gh-pages
git rm -rf .
echo "# LoL Draft Analyzer CDN — auto-generated, do not edit" > README.md
git add README.md
git commit -m "chore: bootstrap gh-pages orphan branch"
git push -u origin gh-pages
git checkout master
```

**Why bootstrap at all?** `peaceiris/actions-gh-pages@v4` with `force_orphan: true` *will* create the branch on first push if it is absent. But having the branch exist before the first CI run lets GitHub Pages be enabled in Settings *ahead of* data arrival — otherwise there is a 5–10 minute window where the CDN 404s because Pages was never configured. Bootstrap first, enable Pages second, run the workflow third.

After the push, confirm on the remote:

```sh
git ls-remote --heads origin gh-pages
```

Expected: one line showing a SHA followed by `refs/heads/gh-pages`.

---

## 3. GitHub Pages enablement (D-28) — **MANUAL OPERATOR ACTION**

This step **cannot be automated** from a standard Claude session — it requires repo-admin UI interaction. The Phase 2 orchestrator gates Wave 3 (Plan 02-04 — the atomic cutover) on an operator confirmation that this step completed.

1. Open https://github.com/Chertixd/LoL-Draft-Helper/settings/pages while logged in as a repo admin.
2. Under **Build and deployment**:
   - **Source:** *Deploy from a branch*.
   - **Branch:** `gh-pages` / `/ (root)`.
3. Click **Save**.
4. Wait 30–60 seconds. The Pages panel will display the published URL: `https://chertixd.github.io/LoL-Draft-Helper/`.
5. Verify from the command line:

   ```sh
   curl -sI https://chertixd.github.io/LoL-Draft-Helper/
   ```

   Expected: `HTTP/2 200`. A transient `HTTP/2 404` on a brand-new Pages site is tolerable — it resolves once the first successful workflow run publishes real content.

---

## 4. Triggering the workflow

The workflow is `supabase-dataset-updater/.github/workflows/update-dataset.yml`, named **Update Supabase Dataset**.

- **Scheduled:** the cron `0 12 * * *` runs daily at 12:00 UTC.
- **Manual:**

  ```sh
  gh workflow run "Update Supabase Dataset" -R Chertixd/LoL-Draft-Helper
  ```

  Or via the GitHub UI: **Actions** → **Update Supabase Dataset** → **Run workflow**.

After a successful run, verify the envelope shape for the single-file `champion_stats` table:

```sh
curl -s https://chertixd.github.io/LoL-Draft-Helper/data/champion_stats.json | \
  python -c "import json, sys; b = json.load(sys.stdin); print('schema_version=%d row_count=%d exported_at=%s' % (b['__meta']['schema_version'], b['__meta']['row_count'], b['__meta']['exported_at']))"
```

Then verify a per-patch shard exists and carries its own envelope (replace `16.7` with any patch in the live `patches` table):

```sh
curl -s https://chertixd.github.io/LoL-Draft-Helper/data/matchups_16.7.json | \
  python -c "import json, sys; b = json.load(sys.stdin); print('schema_version=%d row_count=%d source_patch=%s' % (b['__meta']['schema_version'], b['__meta']['row_count'], b['__meta'].get('source_patch', '<missing>')))"
```

Expected: one line each, showing `schema_version=1`, a positive `row_count`, and (for the shard) a `source_patch` matching the patch in the URL.

---

## 5. Canonical sha256 form (pin this)

The `__meta.sha256` on each file is computed over the canonical JSON of the `rows` array (the `__meta` block itself is **not** covered). Both sides — the exporter that writes the hash and the client that verifies it — MUST serialize with byte-identical kwargs. The exact form:

```python
json.dumps(rows, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
```

(The client side, `json_repo._fetch_one`, omits the `default=` kwarg because at read time all values are already JSON-native primitives; but the byte output is byte-identical because no `Decimal`/`UUID`/`datetime` objects survive the roundtrip. The *producer* side in `export_to_json._canonical_rows_sha256` needs `default=_json_default` because supabase-py can return those types.)

**Per-patch shards each carry their own envelope** computed over their own row subset (not over the full union of all patches). A `matchups_16.7.json` envelope's sha256 verifies only the rows inside `matchups_16.7.json`.

### Pitfall #2 failure mode

If these kwargs drift between the exporter and the client, every fetch raises `CDNError: sha256 mismatch for <table>: expected <hex>, got <hex>` and the app refuses to start.

**Rule:** any PR touching `supabase-dataset-updater/scripts/export_to_json.py` OR `counterpick-app/apps/backend/src/lolalytics_api/json_repo.py` MUST keep the serialization forms byte-identical. Plan 02-02 landed a test (`test_sha256_canonical_form_matches_json_repo`) that enforces this; if that test ever starts failing, do not `# noqa` around it — fix the drift.

---

## 6. Rollback

`force_orphan: true` rewrites `gh-pages` history every push, so there is no `gh-pages^` to reach for. The only way back is to force-push a previous-good SHA.

1. Find the previous-good SHA from the GitHub Actions run list — each workflow run's publish step logs the commit SHA created on `gh-pages`. Alternatively, use the GitHub UI's **Actions → Update Supabase Dataset** run history.
2. Fetch and force-push:

   ```sh
   git fetch origin gh-pages
   git push --force origin <prev-good-sha>:gh-pages
   ```

3. Wait up to 10 minutes for the Fastly edge cache to propagate (see [Troubleshooting](#8-troubleshooting) on stale caches).
4. Verify the rolled-back version is serving:

   ```sh
   curl -s https://chertixd.github.io/LoL-Draft-Helper/data/champion_stats.json | \
     python -c "import json, sys; print(json.load(sys.stdin)['__meta']['exported_at'])"
   ```

   The `exported_at` should match the previous-good run, not the bad one.

---

## 7. Schema version upgrade coordination (Pitfall #6)

`__meta.schema_version` is a **one-way door**. The client (`json_repo.py`) hard-rejects any envelope with `schema_version > 1` (the constant `_SCHEMA_VERSION_MAX = 1`). Bumping `SCHEMA_VERSION` in `export_to_json.py` therefore **instantly breaks every shipped client** the next time the workflow runs.

**Rule.** Do not bump `SCHEMA_VERSION` in `export_to_json.py` until:

1. A client release supporting `schema_version = 2` exists in `latest.json` (the Tauri updater manifest shipped by Phase 4), AND
2. The `latest.json` `minimum_version` gate has forced the old v1 client to auto-update — i.e., v1 clients are deprecated, not just outdated.

The safer intermediate step is additive: add new **fields** to existing `rows` (v1 clients that don't know about them will ignore them) rather than bumping the envelope version. Only bump `schema_version` when the shape of the response is genuinely incompatible.

---

## 8. Troubleshooting

Each entry below is formatted as `symptom → diagnosis → fix`.

### 8.1 Edge cache serving stale data (Pitfall #4)

**Symptom:** A successful workflow run published at `T+0` but the CDN is still serving the pre-run payload 2 minutes later.

**Diagnosis:**

```sh
curl -sI https://chertixd.github.io/LoL-Draft-Helper/data/champion_stats.json | grep -iE '^(age|cache-control|x-cache):'
```

Look at `Age: <seconds>` and `Cache-Control: max-age=600`. GitHub Pages sits behind Fastly, which caps staleness at the Fastly default of ~10 minutes.

**Fix:** wait. There is no cache-purge endpoint exposed for Pages. If you need immediate propagation for debugging, append a cache-buster to the URL (`?v=<timestamp>`); the client production path does not do this — it relies on conditional GETs and accepts the up-to-10-minute staleness window.

### 8.2 `peaceiris` step fails with permission error

**Symptom:** The workflow's "Publish to gh-pages branch" step fails with `remote: Permission to <repo>.git denied to github-actions[bot]` or a similar 403 during `git push`.

**Diagnosis:** the workflow lacks `contents: write` scope.

**Fix:** confirm `permissions: contents: write` exists at the top of `supabase-dataset-updater/.github/workflows/update-dataset.yml` (above `jobs:`). If missing, add it — it is the documented minimum for `peaceiris/actions-gh-pages@v4` to push to a branch.

### 8.3 Client logs `CDNError: sha256 mismatch`

**Symptom:** On client startup the backend logs `CDNError: sha256 mismatch for <table>: expected <hex>, got <hex>` and refuses to serve traffic.

**Diagnosis:** canonical-form drift between `export_to_json._canonical_rows_sha256` and `json_repo._fetch_one`'s verification path. One side was edited without the other. The form is pinned in [Section 5](#5-canonical-sha256-form-pin-this).

**Fix:** revert the offending change; rerun the workflow to re-publish with the old canonical form. Do NOT disable the check on the client side — the sha256 mismatch is a real data-integrity signal, not false positive.

### 8.4 Per-patch shard 404s (`matchups_<patch>.json` not found)

**Symptom:** The client fetches `https://chertixd.github.io/LoL-Draft-Helper/data/matchups_16.7.json` and receives `404`. The single-file tables (e.g., `items.json`) fetch fine.

**Diagnosis:** either (a) `PER_PATCH_TABLES` drifted between `export_to_json.py` and `json_repo.py` (producer thinks the table is single-file, client thinks it's sharded — or vice versa), or (b) the requested patch is not in the `patches` table, so no shard was produced for it.

**Fix:** grep both files for `PER_PATCH_TABLES` — the two `frozenset({...})` literals must contain the same table names. For case (b), confirm the patch exists in Supabase's `patches` table; the client should only request shards for patches it read out of the canonical `patches.json`.

### 8.5 Workflow fails at the export step with `missing required env var`

**Symptom:** Workflow log shows `[export] FATAL: missing required env var: 'SUPABASE_URL'` or `'SUPABASE_SERVICE_ROLE_KEY'`.

**Diagnosis:** the new export step is not picking up the Actions secrets. GitHub scopes secrets per repository, not per workflow file; but a workflow in a subdirectory (`supabase-dataset-updater/.github/workflows/`) must still reference `${{ secrets.SUPABASE_URL }}` explicitly in an `env:` block on the step — they are not auto-injected.

**Fix:** verify the `env:` block on the "Export Supabase tables to JSON" step lists both secrets. Confirm the secrets are set at https://github.com/Chertixd/LoL-Draft-Helper/settings/secrets/actions.
