---
name: add-or-update-etl-module-with-tests
description: Workflow command scaffold for add-or-update-etl-module-with-tests in LoL-Draft-Helper.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-or-update-etl-module-with-tests

Use this workflow when working on **add-or-update-etl-module-with-tests** in `LoL-Draft-Helper`.

## Goal

Implements a new ETL (extract/transform/load) module or feature, always paired with a dedicated test file for that module.

## Common Files

- `supabase-dataset-updater/src/*.ts`
- `supabase-dataset-updater/tests/*.test.ts`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Create or update a src/<module>.ts file in supabase-dataset-updater/src/
- Create or update a matching tests/<module>.test.ts file in supabase-dataset-updater/tests/
- Commit both files together

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.