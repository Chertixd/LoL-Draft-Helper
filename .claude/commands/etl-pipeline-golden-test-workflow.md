---
name: etl-pipeline-golden-test-workflow
description: Workflow command scaffold for etl-pipeline-golden-test-workflow in LoL-Draft-Helper.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /etl-pipeline-golden-test-workflow

Use this workflow when working on **etl-pipeline-golden-test-workflow** in `LoL-Draft-Helper`.

## Goal

Adds or updates golden tests for the ETL pipeline, capturing fixtures and verifying output against committed snapshots.

## Common Files

- `supabase-dataset-updater/tests/fixtures/*`
- `supabase-dataset-updater/tests/golden.test.ts`
- `supabase-dataset-updater/package.json`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Capture or update fixtures in tests/fixtures/
- Update or add expected output files in tests/fixtures/expected-pipeline-output/
- Update or add a golden test in tests/golden.test.ts
- Update package.json if new scripts or dependencies are needed

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.