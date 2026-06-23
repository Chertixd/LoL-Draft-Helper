```markdown
# LoL-Draft-Helper Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you how to contribute to the LoL-Draft-Helper project, a TypeScript-based codebase (no framework detected) for managing League of Legends draft data and helper utilities. You'll learn the project's coding conventions, how to add or update ETL modules, maintain golden tests, fix frontend state/UI bugs, remove backend APIs, and update development scripts and documentation. The guide also covers the project's testing patterns and provides handy commands for common workflows.

## Coding Conventions

- **File Naming:**  
  Use kebab-case for all file names.  
  _Example:_  
  ```
  supabase-dataset-updater/src/data-transformer.ts
  counterpick-app/apps/frontend/src/champion-picker.vue
  ```

- **Import Style:**  
  Use relative imports for all modules.  
  _Example:_  
  ```typescript
  import { transformData } from './data-transformer';
  ```

- **Export Style:**  
  Use named exports only.  
  _Example:_  
  ```typescript
  // Good
  export function processChampionData() { ... }

  // Avoid
  export default function processChampionData() { ... }
  ```

- **Commit Messages:**  
  Follow [Conventional Commits](https://www.conventionalcommits.org/), using prefixes like `feat`, `fix`, `chore`, `test`, `ci`.  
  _Example:_  
  ```
  feat(etl): add champion stats transformer with tests
  fix(frontend): correct state update on role change
  ```

## Workflows

### Add or Update ETL Module with Tests
**Trigger:** When adding a new ETL pipeline step or utility function  
**Command:** `/new-etl-module`

1. Create or update a `.ts` module in `supabase-dataset-updater/src/`.
2. Create or update a matching test file in `supabase-dataset-updater/tests/` (e.g., `module.test.ts`).
3. Commit both files together.

_Example:_
```typescript
// supabase-dataset-updater/src/champion-stats.ts
export function calculateWinRate(wins: number, games: number): number {
  return games === 0 ? 0 : wins / games;
}
```
```typescript
// supabase-dataset-updater/tests/champion-stats.test.ts
import { calculateWinRate } from '../src/champion-stats';

test('calculates win rate correctly', () => {
  expect(calculateWinRate(5, 10)).toBe(0.5);
});
```

---

### ETL Pipeline Golden Test Workflow
**Trigger:** When ensuring ETL output is reproducible and matches expected results  
**Command:** `/golden-test`

1. Capture or update fixtures in `supabase-dataset-updater/tests/fixtures/`.
2. Update or add expected output files in `supabase-dataset-updater/tests/fixtures/expected-pipeline-output/`.
3. Update or add a golden test in `supabase-dataset-updater/tests/golden.test.ts`.
4. Update `package.json` if new scripts or dependencies are needed.

_Example:_
```typescript
// supabase-dataset-updater/tests/golden.test.ts
import { runPipeline } from '../src/pipeline';
import expected from './fixtures/expected-pipeline-output/result.json';

test('pipeline output matches golden file', () => {
  const output = runPipeline();
  expect(output).toEqual(expected);
});
```

---

### Frontend State or UI Bugfix
**Trigger:** When fixing a bug in frontend state handling or UI feedback  
**Command:** `/fix-frontend-state`

1. Identify the problematic store or component file in `counterpick-app/apps/frontend/src/`.
2. Update the file to fix state logic or UI behavior.
3. Commit the change with a detailed message explaining the bug and fix.

_Example:_
```typescript
// counterpick-app/apps/frontend/src/role-selector.vue
methods: {
  selectRole(role) {
    this.selectedRole = role; // Ensure reactivity is preserved
  }
}
```

---

### Backend API or Data Contract Removal
**Trigger:** When deprecating or fully removing unused backend code or APIs  
**Command:** `/remove-backend-api`

1. Delete unused route handlers or modules in `apps/backend/`.
2. Remove related imports from `backend.py` or other entrypoints.
3. Update `requirements.txt` or `pyproject.toml` to drop dependencies.
4. Update or rewrite `__init__.py` if submodule structure changes.

---

### Dev Environment Scripts and Docs Update
**Trigger:** When changing how the app is run locally (e.g., switching to Tauri, removing old launchers)  
**Command:** `/update-dev-scripts`

1. Add or update scripts in `package.json` or `scripts/` directories.
2. Remove obsolete `.bat`, `.ps1`, or Python scripts.
3. Update documentation files (e.g., `TROUBLESHOOTING.md`) to match the new workflow.
4. Update test docstrings if they reference old scripts.

---

## Testing Patterns

- **Framework:** [Vitest](https://vitest.dev/)
- **Test File Pattern:** All test files are named `*.test.ts` and placed alongside or near the modules they test.
- **Test Example:**
  ```typescript
  // supabase-dataset-updater/tests/data-transformer.test.ts
  import { transformData } from '../src/data-transformer';

  test('transforms data as expected', () => {
    const input = { ... };
    const output = transformData(input);
    expect(output).toMatchSnapshot();
  });
  ```

## Commands

| Command               | Purpose                                                          |
|-----------------------|------------------------------------------------------------------|
| /new-etl-module       | Add or update an ETL module with a matching test                 |
| /golden-test          | Add or update golden tests and fixtures for the ETL pipeline     |
| /fix-frontend-state   | Fix a frontend state management or UI reactivity bug             |
| /remove-backend-api   | Remove legacy or unused backend endpoints or modules             |
| /update-dev-scripts   | Update local development scripts and related documentation       |
```