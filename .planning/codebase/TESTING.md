# Testing Patterns

**Analysis Date:** 2026-04-14

## Test Framework

**Python:**
- Framework: `pytest` (listed in `pyproject.toml` lines 29-32 as optional dependency)
- Config: No `pytest.ini` or `[tool.pytest]` section found in `pyproject.toml` — uses defaults
- Requirements: pytest listed in `counterpick-app/apps/backend/requirements.txt`

**TypeScript:**
- Framework: **None detected** — no vitest, jest, or mocha config files found
- No test runner configured in `package.json` scripts
- No `.spec.ts` or `.test.ts` files in source directories (only in `node_modules/entities/`)
- No test configuration files (no `vitest.config.ts`, `jest.config.js`)

**Run Commands:**

Python testing (if configured):
```bash
pytest                    # Run all tests in backend/
pytest -v                 # Verbose output
pytest --cov             # With coverage (requires pytest-cov)
```

TypeScript testing:
```
Not configured — no test runner available
```

## Test File Organization

**Location:**
- Python: Would be in `counterpick-app/apps/backend/` directory (same level as source)
- TypeScript: No test files present in frontend, supabase-dataset-updater, or core packages

**Naming Convention (if tests existed):**
- Python: `test_*.py` or `*_test.py` pattern (pytest default)
- TypeScript: `*.test.ts` or `*.spec.ts` pattern (not used here)

**Actual Status:**
- **No test files exist in the codebase** (except in node_modules dependencies)
- Testing is **not implemented** for this project

## Test Structure

No existing test suites to document. If pytest were used, typical structure would be:

```python
# Hypothetical test_backend.py structure
import pytest
from backend import normalize_champion_name, normalize_patch
from lolalytics_api import get_tierlist

def test_normalize_champion_name():
    assert normalize_champion_name("Kog'Maw") == "kogmaw"
    assert normalize_champion_name("Miss Fortune") == "missfortune"

def test_normalize_patch():
    assert normalize_patch("16.1.1") == "16.1"
    assert normalize_patch("16.1") == "16.1"
```

## Mocking

**No mocking framework detected** in either Python or TypeScript.

If mocking were implemented:

**Python (would use `unittest.mock`):**
```python
from unittest.mock import patch, MagicMock

@patch('requests.get')
def test_get_tierlist(mock_get):
    mock_response = MagicMock()
    mock_response.content = b"<html>...</html>"
    mock_get.return_value = mock_response
    # Test assertion
```

**TypeScript (would use `vitest` or `jest`):**
```typescript
vi.mock('@/api/backend', () => ({
  getChampionsList: vi.fn().mockResolvedValue({ 
    success: true, 
    champions: ['Aatrox', 'Ahri'] 
  })
}));
```

## Fixtures and Factories

**Not implemented** — no test fixtures, factories, or test data builders found.

If implemented, would likely be:

**Python location:** `counterpick-app/apps/backend/tests/fixtures.py`

```python
# Hypothetical fixture structure
import pytest

@pytest.fixture
def mock_champion_data():
    return {
        'Aatrox': {'tier': 'S', 'winrate': '52.3%'},
        'Ahri': {'tier': 'A', 'winrate': '49.8%'}
    }
```

**TypeScript location:** `counterpick-app/apps/frontend/tests/fixtures.ts` or `src/tests/mocks/`

## Coverage

**Requirements:** Not enforced — no coverage configuration found

**Hypothetical Coverage View:**
```bash
pytest --cov=src --cov-report=html    # Generate HTML report
pytest --cov=src --cov-report=term    # Print to terminal
```

**Current State:** 0% coverage (no tests exist)

## Test Types

### Unit Tests
- **Scope:** Individual functions like `normalize_champion_name()`, `wilson_score()`, `_normalize_slug()`
- **Approach (if implemented):** Would test pure functions with various inputs/edge cases
- **Status:** Not implemented

### Integration Tests
- **Scope:** Flask API endpoints (`/api/health`, `/api/recommendations`, `/api/champion/matchups`)
- **Approach (if implemented):** Would mock Supabase client and test full request/response cycle
- **Status:** Not implemented

### E2E Tests
- **Framework:** Not used
- **Would test:** Full draft tracking flow through League Client API + WebSocket + backend + frontend
- **Status:** No E2E framework configured

## Common Patterns

If tests were written, these patterns would likely be used:

**Async Testing (Python + Flask):**
```python
@pytest.mark.asyncio
async def test_get_recommendations():
    response = await getRecommendations({
        'champion': 'Aatrox',
        'role': 'top'
    })
    assert response['success'] == True
```

**Async Testing (TypeScript):**
```typescript
it('should load champion data', async () => {
    const championStore = useChampionStore();
    await championStore.loadChampionData();
    expect(championStore.championsLoaded).toBe(true);
});
```

**Error Testing (Python):**
```python
def test_invalid_lane_raises_error():
    with pytest.raises(InvalidLane):
        _sort_by_lane('https://lolalytics.com/', 'invalid_lane')
```

**Error Testing (TypeScript):**
```typescript
it('should handle API errors gracefully', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('Network error'));
    try {
        await checkBackendHealth();
    } catch (e) {
        expect(e.message).toContain('Network error');
    }
});
```

## Testing Status Summary

| Aspect | Status |
|--------|--------|
| Python Framework | pytest (dependency available, not configured) |
| TypeScript Framework | None |
| Test Files | 0 (none in source) |
| Coverage | 0% |
| CI/CD Testing | Not detected (no test runs in GitHub workflows) |
| E2E Testing | Not implemented |

**Assessment:** This is a hobby/personal project without test coverage. The codebase has testable pure functions (`wilson_score()`, `normalize_*()`, Flask endpoints) but no tests are written. The project prioritizes rapid feature development over testing infrastructure.

**Recommendation for Future:** 
- Start with unit tests for pure functions in `src/lolalytics_api/` (no dependencies)
- Add integration tests for Flask endpoints with Supabase mocking
- Consider adding E2E tests for critical draft-tracking flow once project stabilizes

---

*Testing analysis: 2026-04-14*
