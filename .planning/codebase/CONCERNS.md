# Codebase Concerns

**Analysis Date:** 2026-04-14

## Security Issues

### Supabase Service Role Key Bypass (CRITICAL)

**Issue:** `counterpick-app/apps/backend/src/lolalytics_api/supabase_client.py` uses `prefer_service=True` by default, which attempts to load `SUPABASE_SERVICE_ROLE_KEY` before falling back to `SUPABASE_ANON_KEY`. Service role keys bypass all row-level security (RLS) policies.

**Files:**
- `counterpick-app/apps/backend/src/lolalytics_api/supabase_client.py` (line 7)
- `counterpick-app/apps/backend/src/lolalytics_api/config.py` (lines 15-30)

**Impact:**
- If service role key is configured, all RLS policies on Supabase tables are completely bypassed
- If backend is ever distributed to clients (as a desktop app or cloud deployment), anyone with access to the codebase can read/write entire database without restrictions
- Current safeguard relies solely on environment variable configuration discipline
- No runtime enforcement preventing service role usage

**Recommendation:**
- Change default to `prefer_service=False` in `supabase_client.py:get_supabase_client()`
- Update `config.py:get_supabase_key()` to prioritize ANON key
- For any operations requiring elevated permissions, explicitly pass `prefer_service=True` with documented justification
- Implement RLS policies on all data tables assuming anon key access only
- Add runtime warning if service role key is detected in use

**Severity:** CRITICAL

---

### Hardcoded API Endpoint (HIGH)

**Issue:** Frontend hardcodes `http://localhost:5000` for backend connection, making the application non-portable and exposing localhost assumption.

**Files:**
- `counterpick-app/apps/frontend/src/stores/draft.ts` (line 41)

**Impact:**
- Application only works when backend runs on localhost port 5000
- No environment-based configuration for API URL
- Cannot be deployed to different servers, containers, or cloud environments
- Makes it impossible to separate frontend and backend infrastructure

**Current State:** Backend binds to all interfaces (`0.0.0.0:5000`) but frontend forces localhost connection.

**Recommendation:**
- Move API base URL to environment variables (e.g., `VITE_API_BASE_URL`)
- Use runtime configuration or build-time injection via `.env`
- Provide sensible default but allow override for deployments

**Severity:** HIGH

---

## Dependency & Version Management

### Unpinned Python Dependencies (MEDIUM)

**Issue:** `counterpick-app/apps/backend/requirements.txt` has inconsistent version pinning strategy.

**Files:**
- `counterpick-app/apps/backend/requirements.txt`

**Current State:**
```
requests          # No version
lxml              # No version
pytest            # No version
urllib3           # No version
flask             # No version
flask-cors        # No version
flask-socketio>=5.3.0    # Minimum version
python-socketio>=5.9.0   # Minimum version
websocket-client>=1.6.0  # Minimum version
supabase>=2.4.0          # Minimum version
python-dotenv     # No version
```

**Impact:**
- `pip install` may pull different versions on different machines (environment inconsistency)
- No reproducible builds without `pip freeze` documentation
- Risk of compatibility issues when upgrading Flask/dependencies
- Minimum version pins (`>=`) allow breaking changes in patch versions

**Missing Artifact:**
- No `pip freeze` output documented or `requirements-lock.txt`
- No Python version specified (`.python-version` or `pyproject.toml`)

**Recommendation:**
- Pin all direct dependencies to specific versions (e.g., `flask==2.3.5`)
- Use `pip freeze` to lock transitive dependencies in separate `requirements-lock.txt`
- Document Python version requirement (3.9+, 3.10+, etc.)
- Consider migrating to `pyproject.toml` with Poetry or Pipenv for better management

**Severity:** MEDIUM

---

## Architecture & Design Issues

### Backend Monolith (MEDIUM)

**Issue:** `counterpick-app/apps/backend/backend.py` is a large monolithic Flask application handling multiple concerns.

**Files:**
- `counterpick-app/apps/backend/backend.py` (1,751 lines)
- `counterpick-app/apps/backend/recommendation_engine.py` (751 lines)
- `counterpick-app/apps/backend/league_client_api.py` (461 lines)
- `counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` (444 lines)

**Current Responsibilities in backend.py:**
- HTTP API endpoints (health, champions, recommendations, draft, etc.)
- League Client WebSocket/HTTP polling and event handling
- Caching logic with JSON file persistence
- Role detection and validation
- Manual role override management
- Request/response formatting and error handling

**Impact:**
- Single point of failure for all backend functionality
- Difficult to test individual components
- Recommendation engine (separate module) is tightly coupled to main backend
- Adding new features requires modifying large file
- No clear separation between API layer, business logic, and external integrations

**Current Mitigation:** Some logic is extracted to separate modules (`recommendation_engine.py`, `league_client_api.py`, `league_client_websocket.py`) but orchestration remains in main file.

**Recommendation:**
- Extract API routes into separate module/blueprint structure
- Create service/business logic layer separate from HTTP handling
- Consider Flask Blueprints for organizing endpoints (e.g., `routes/league_client.py`, `routes/recommendations.py`)
- Extract WebSocket event handling and polling into dedicated service

**Severity:** MEDIUM (not immediately breaking, but impacts maintainability)

---

### Data Pipeline Coupling (MEDIUM)

**Issue:** Backend directly accesses the same Supabase database used by ETL (data pipeline), with no separation between read and write paths.

**Files:**
- `counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` (read operations)
- ETL writes to same tables

**Impact:**
- No staging/read-replica isolation
- ETL updates could impact backend during active reads
- No schema versioning between ETL output and backend expectations
- Difficult to evolve data model without coordinating both systems
- If ETL corrupts data, backend immediately serves corrupted data

**Current Mitigation:** RLS policies (if configured) could prevent cross-access, but no documented separation strategy.

**Recommendation:**
- Implement separate read replica or staging views for backend
- Document and enforce ETL -> staging table -> materialized view -> production read pattern
- Add schema versioning check (e.g., backend validates table structure at startup)
- Consider data validation layer between ETL output and backend consumption

**Severity:** MEDIUM

---

## Data & Caching Issues

### Stale Cache File (LOW-MEDIUM)

**Issue:** `counterpick-app/apps/backend/cache_data.json` (118 KB) is committed to git and auto-populated with test data.

**Files:**
- `counterpick-app/apps/backend/cache_data.json`

**Current State:**
- File exists, contains champion role probability cache data
- Generated and updated during runtime
- Not tracked in `.gitignore`
- Last modified: February 8, 2025

**Impact:**
- Cached data can become stale (dependent on data sources)
- Git history grows with cache file changes if it's regenerated
- Unclear whether this is test data or production cache
- No TTL enforcement (24-hour cache duration defined in code but not reflected in file metadata)

**Code References:**
- `backend.py` lines 55-57: Cache file loaded on startup, saved after API calls
- Cache lifecycle: loaded from disk, expired after 86400 seconds (24 hours)

**Question:** Is this cache essential for cold startup, or is it a convenience optimization?

**Recommendation:**
- If cache is essential for startup: Add to `.gitignore`, document how to generate on first run
- If cache is convenience optimization: Remove from git, rebuild on cold start
- Add cache generation script to startup sequence if data is critical
- Consider moving to in-memory cache (with optional persistence) rather than git-tracked file

**Severity:** LOW-MEDIUM

---

## Fragile Areas

### Hover Detection Logic (MEDIUM)

**Issue:** Hovered (unconfirmed) champions are included in recommendations but with reduced weight (50%). User reports this is "noch nicht richtig beachtet" (not correctly weighted).

**Files:**
- `counterpick-app/apps/frontend/src/stores/draft.ts` (line 818: sets `isHovered` flag)
- `counterpick-app/apps/backend/recommendation_engine.py` (lines 179, 470: processes `isHovered`)

**Current Implementation:**
```python
# Line 470: Reduce importance for hovered champions (50% weight)
imp = base_imp * (0.5 if mate_data.get('isHovered', False) else 1.0)
```

**Problems:**
- Hovered champions included in team composition analysis but with penalty
- Not validated whether this weighting correctly handles hovering in different game phases
- No user-facing distinction between "definitely picking this" vs "might pick this"
- Synergy/counter calculations assume partial commitment, but user expectations unclear

**Risk:**
- Recommendations may be misleading if user hovers but doesn't pick
- 50% weight may not reflect actual game impact (depends on draft phase)
- No A/B testing or user feedback validation on weighting factor

**Safe Modification:**
- Before changing weight: Log recommendation scores with/without hovered champions
- Test with real draft scenarios
- Consider separate recommendation path for "confirmed picks only"
- Document weighting decision with game theory reasoning

**Severity:** MEDIUM (functional but potentially misaligned with user intent)

---

### League Client API Integration (LOW-MEDIUM)

**Issue:** Multiple integration points between backend and League Client API with fallback logic but unclear failure modes.

**Files:**
- `counterpick-app/apps/backend/league_client_api.py` (461 lines)
- `counterpick-app/apps/backend/league_client_websocket.py` (303 lines)
- `counterpick-app/apps/backend/live_client_api.py` (153 lines)
- `counterpick-app/apps/backend/backend.py` (WebSocket event handling, polling fallback)

**Current Architecture:**
1. Primary: WebSocket connection to League Client (`league_client_websocket.py`)
2. Fallback: HTTP polling if WebSocket fails (`backend.py` `poll_draft_data()`)
3. Live game data: Separate Live Client API module (`live_client_api.py`)

**Fragility Points:**
- WebSocket reconnection interval hardcoded (5 seconds, line 22 in `league_client_websocket.py`)
- No maximum retry limit documented
- Event parsing is brittle (multiple format variations handled in `on_message()`)
- HTTP polling active indefinitely if WebSocket fails (no circuit breaker)

**Risk:**
- If League Client API format changes, parsing may silently fail
- Fallback polling may become permanent if one WebSocket connection fails
- No metrics or alerting for integration health

**Safe Modification:**
- Add unit tests for event parsing with real League Client examples
- Document expected message formats with examples
- Implement circuit breaker pattern for WebSocket reconnection
- Add health check endpoint that validates League Client connectivity

**Severity:** LOW-MEDIUM

---

### Recommendation Engine Complexity (LOW-MEDIUM)

**Issue:** Recommendation engine has complex pacing analysis and synergy weighting with multiple conditional branches and debug logging.

**Files:**
- `counterpick-app/apps/backend/recommendation_engine.py` (751 lines)

**Code Characteristics:**
- Multiple nested conditions for pacing scenarios (lines 500-510)
- Wilson score calculations with configurable Z-values based on sample size (lines 56-129)
- Extensive debug logging with `[SYNERGY DEBUG]` prefixes (lines 478-483, 490-493)
- State management across multiple synergy lookups

**Fragility:**
- Many print statements for debugging left in production code
- Complex statistical calculations (Wilson score) lack validation layer
- Pacing thresholds hardcoded in `recommendation_config.py`
- No caching of expensive DB queries

**Risk:**
- Debug output could leak sensitive game data in logs
- Changes to thresholds in `recommendation_config.py` have non-obvious effects
- Hard to trace recommendation scores without reading full execution flow

**Safe Modification:**
- Extract debug logging to proper logging framework (with levels: DEBUG, INFO, WARNING)
- Add data validation after DB queries (assert expected fields present)
- Document all threshold values and their game theory justification
- Consider caching team composition analysis results

**Severity:** LOW-MEDIUM

---

## Startup & Deployment

### Two-Step Manual Startup (LOW)

**Issue:** Application requires manual execution of two separate commands with no single entry point.

**Files:**
- `counterpick-app/apps/backend/START_BACKEND_ADMIN.bat` (workaround script)
- `counterpick-app/START_FRONTEND.bat` (workaround script)

**Current Process:**
1. User must start backend: `python backend.py` (or via .bat file)
2. User must start frontend: `pnpm dev` (or via .bat file)
3. Frontend hard-depends on backend on localhost:5000

**Workaround Status:**
- `.bat` files exist as band-aids but require manual admin elevation
- No automated setup validation

**Impact:**
- High friction for new users
- No health check before frontend starts
- If backend fails to start, frontend still loads but shows connection errors
- Difficult to bundle for distribution

**Recommendation:**
- Implement single startup script that:
  - Checks Python environment
  - Validates Supabase credentials
  - Starts backend (with timeout)
  - Starts frontend
  - Waits for health checks on both services
- Consider Docker Compose for reproducible multi-service setup
- Add pre-flight checks (node version, Python version, .env configuration)

**Severity:** LOW (not a correctness issue, but impacts usability)

---

## Test Coverage Gaps

### Limited Test Visibility (MEDIUM)

**Issue:** Backend modules lack visible test files or test execution is not documented.

**Files:**
- `counterpick-app/apps/backend/requirements.txt` includes `pytest` but no test directory visible
- No `tests/` directory found in backend structure
- No test configuration file (`pytest.ini`, `setup.cfg`)

**Impact:**
- Unclear whether business logic is tested
- Recommendation engine (complex calculations) testing status unknown
- League Client integration testing status unknown
- Hard to validate changes don't break existing functionality

**Risk Areas Without Clear Tests:**
- `recommendation_engine.py`: Complex statistical calculations and synergy weighting
- `league_client_api.py`: Integration with Riot's API
- `supabase_repo.py`: Database queries and schema assumptions

**Recommendation:**
- Establish test directory structure: `tests/unit/`, `tests/integration/`, `tests/fixtures/`
- Create test fixtures for mock League Client data and Supabase responses
- Write unit tests for:
  - Recommendation scoring (with expected inputs/outputs documented)
  - Role detection from session data
  - Champion name normalization
  - Pacing analysis
- Set up test execution in CI/CD pipeline

**Severity:** MEDIUM

---

## Performance & Scalability

### Cache Strategy Incomplete (LOW)

**Issue:** JSON file-based cache is simple but not scalable and loses data on restart.

**Files:**
- `counterpick-app/apps/backend/backend.py` (lines 55-57, cache loading/saving)

**Current Behavior:**
- In-memory dict `cache` loaded from `cache_data.json` on startup
- Updated during API calls, saved back to disk
- 24-hour TTL per item
- No cleanup of expired items (memory leak over long uptime)

**Impact:**
- Cache file I/O on every API response (performance overhead)
- Expired items accumulate in memory
- No cache invalidation strategy for data updates from ETL
- Thread-safety not documented (Flask-SocketIO uses threading)

**Recommendation:**
- Implement proper cache layer (Redis, or in-memory with scheduled cleanup)
- Add background job to clean expired cache entries
- Implement cache invalidation on ETL updates (via webhook or polling)
- Document thread-safety guarantees

**Severity:** LOW (works for single-user scenario, problematic for scale)

---

## Summary by Severity

| Severity | Issues | Action Items |
|----------|--------|--------------|
| CRITICAL | Supabase service role key default | Change default, implement RLS validation |
| HIGH | Hardcoded localhost API URL | Move to environment configuration |
| MEDIUM | Unpinned dependencies | Pin versions, use lock file |
| MEDIUM | Backend monolith (1,751 lines) | Extract routes/services into modules |
| MEDIUM | Data pipeline coupling | Implement staging/read-replica separation |
| MEDIUM | Hover detection weighting unclear | Validate and document 50% weight factor |
| MEDIUM | League Client integration fragility | Add tests, implement circuit breaker |
| MEDIUM | Recommendation engine logging in production | Extract to proper logging framework |
| MEDIUM | Test coverage visibility gaps | Establish test structure and CI/CD |
| LOW-MEDIUM | Stale cache file in git | Add to .gitignore, document generation |
| LOW | Manual two-step startup | Create unified startup script |
| LOW | Cache strategy not scalable | Migrate to proper cache layer for production |

---

*Concerns audit: 2026-04-14*
