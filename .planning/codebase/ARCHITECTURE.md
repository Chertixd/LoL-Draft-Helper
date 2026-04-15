# Architecture

**Analysis Date:** 2026-04-14

## Pattern Overview

**Overall:** Client-Server with League Client Bridge

The system implements a three-tier architecture: Vue 3 frontend ↔ Flask REST/WebSocket API ↔ Supabase PostgreSQL, with a specialized bridge layer that connects to the League of Legends client via HTTP API and WebSocket for real-time draft events.

**Key Characteristics:**
- Decoupled frontend and backend with REST endpoints for recommendations and data queries
- Real-time WebSocket connection from Flask backend to League Client for live draft state updates
- Recommendation engine as core scoring service with Wilson Score statistical confidence calculation
- Repository pattern for data access layer abstracting Supabase queries
- Modular Python packages (lolalytics_api) for reusable business logic

## Layers

**Presentation (Vue 3 Frontend):**
- Purpose: Interactive draft analysis UI with real-time recommendation display
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/`
- Contains: Vue components, Pinia stores, API client, assets
- Depends on: Flask REST API (`/api/*` endpoints), shared types from `@counterpick/core`
- Used by: Web browser via Vite dev server or built artifacts

**API Server (Flask Backend):**
- Purpose: HTTP REST endpoints for champion data, recommendations, matchups; WebSocket gateway for League Client events
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/`
- Contains: Flask app, league client integrations, recommendation engine, lolalytics_api module
- Depends on: Supabase client, League Client (via HTTP/WebSocket), lolalytics_api package
- Used by: Frontend Vue app, ETL pipeline

**Data Access (Supabase Repository):**
- Purpose: Abstraction layer for Supabase queries using repository pattern
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py`
- Contains: Query functions for champions, stats, matchups, synergies, items, runes
- Depends on: Supabase Python client
- Used by: Recommendation engine, Flask endpoints

**Shared Types (TypeScript Package):**
- Purpose: Single source of truth for request/response interfaces
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/packages/core/src/`
- Contains: TypeScript types for recommendations, drafts, champions, roles
- Depends on: None (zero-dependency package)
- Used by: Frontend app, API documentation

**ETL Pipeline (Node.js):**
- Purpose: Nightly data synchronization from Riot API and Lolalytics to Supabase
- Location: `F:\Dokumente\Archiv\Riot Api/supabase-dataset-updater/src/`
- Contains: Riot API client, Lolalytics scraper, Supabase upsert logic
- Depends on: Supabase client, Riot API, HTML scraper
- Used by: GitHub Actions scheduled workflow

## Data Flow

**Draft Analysis Flow:**

1. User opens DraftTrackerView (`frontend/src/views/DraftTrackerView.vue`)
2. Draft store (`frontend/src/stores/draft.ts`) initiates WebSocket to Flask backend
3. Flask backend connects to League Client WebSocket via `league_client_websocket.py`
4. League Client emits champion select events → Flask relays via Socket.io to frontend
5. Frontend receives picks/bans, triggers recommendation request
6. Recommendation engine (`backend/recommendation_engine.py`) fetches stats via `supabase_repo.py`
7. Wilson Score applied to matchups and synergies; scores aggregated with configurable weights
8. Frontend renders recommendations sorted by combined score

**Champion Lookup Flow:**

1. User searches champion in ChampionLookupView (`frontend/src/views/ChampionLookupView.vue`)
2. Frontend calls `getChampionMatchups()` and `getChampionSynergies()` from `api/backend.ts`
3. Flask endpoints (`/champion/{name}/matchups`, `/champion/{name}/synergies`) delegate to `supabase_repo.py`
4. Results transformed with champion name lookups and returned as JSON
5. Frontend renders matchup grid and synergy pairings

**Data Sync Flow (Nightly):**

1. GitHub Actions trigger ETL at scheduled time
2. `supabase-dataset-updater/src/supabase-etl.ts` runs:
   - Fetch Riot API for champion/item/rune definitions
   - Scrape Lolalytics for patch statistics (stats_by_time, matchups, synergies)
   - Upsert to Supabase tables: `champions`, `patches`, `champion_stats`, `matchups`, `synergies`, `items`, `runes`
3. Flask backend queries latest patch on next API call

**State Management:**

Frontend uses Pinia stores for:
- `draft.ts`: Draft state (team picks/bans, my role, recommendations, socket connection)
- `champion.ts`: Champion metadata cache
- `settings.ts`: Patch selection, rank filters

Backend uses:
- JSON cache file (`cache_data.json`) for champion metadata (24hr TTL)
- In-memory WebSocket/Socket.io connection state
- Manual role overrides (`MANUAL_ROLE_OVERRIDE`) per session

## Key Abstractions

**Recommendation Scoring (Wilson Score):**
- Purpose: Statistically confident ranking of champions considering low sample sizes
- File: `backend/recommendation_engine.py` function `wilson_score()`
- Pattern: Lower confidence bound of win rate binomial proportion at z=1.44 (85% confidence)
- Applied to: Base winrate, matchups, synergies to filter unreliable (<50 games) stats
- Example: Champion with 10 wins/20 games gets lower score than 100 wins/200 games even if raw % is same

**Recommendation Engine Scoring:**
- Purpose: Combine base, counter, and synergy scores with dynamic weights per role
- File: `backend/recommendation_engine.py` function `get_recommendations()`
- Pattern: Weighted average of three dimensions:
  - Base (30%): champion winrate + meta strength
  - Counter (45%): matchup wins vs enemy team
  - Synergy (25%): teammate combo strength
  - Weights configurable per role in `recommendation_config.py`
- Normalization: All subscores mapped to 0-100 range before weighting

**Repository Pattern (Supabase Data Access):**
- Purpose: Single point of champion data resolution and stat queries
- File: `backend/src/lolalytics_api/supabase_repo.py`
- Pattern: Public functions like `get_champion_stats()`, `get_matchups()`, `get_synergies()` that:
  1. Resolve champion name/key via `_champion_map()`
  2. Determine role via `_determine_role()` if not provided
  3. Query Supabase table with filters
  4. Attach human-readable names to results via `_attach_names()`
- Abstraction benefit: Centralized champion name normalization, consistent Wilson Score application

**League Client Integration Bridge:**
- Purpose: Convert League Client process args and APIs into real-time draft state
- Files: `league_client_auth.py`, `league_client_api.py`, `league_client_websocket.py`
- Pattern: 
  - `league_client_auth.py`: Parse process args to extract port, password, username
  - `league_client_api.py`: Synchronous HTTP requests to get current draft session state
  - `league_client_websocket.py`: Async WebSocket subscriber to `/lol-champ-select/v1/session` URI
  - Flask endpoint bridges WebSocket events to Socket.io for frontend

## Entry Points

**Frontend Entry:**
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/main.ts`
- Triggers: User runs `pnpm dev` or accesses built app
- Responsibilities: Create Vue app, register Pinia stores, set up router (Draft Tracker at `/draft`, Lookup at `/lookup`)

**Backend Entry:**
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/backend.py`
- Triggers: User runs Python backend (typically `python backend.py` or via start script)
- Responsibilities: 
  - Initialize Flask app with CORS and Socket.io
  - Register `/api/*` endpoints for recommendations, champions, patches, League Client status
  - Listen for League Client WebSocket events
  - Load cache from `cache_data.json`
  - Start Socket.io server for real-time frontend communication

**ETL Entry:**
- Location: `F:\Dokumente\Archiv\Riot Api/supabase-dataset-updater/src/supabase-etl.ts`
- Triggers: GitHub Actions scheduled workflow (`.github/workflows/*.yml`)
- Responsibilities: 
  - Fetch latest patch from Riot API
  - Scrape Lolalytics for champion stats by patch
  - Upsert champion definitions, stats, matchups, synergies to Supabase

## Error Handling

**Strategy:** Defensive with graceful degradation and retry logic

**Patterns:**

*Frontend API calls:*
- Exponential backoff retry on 5xx errors (up to 3 retries per endpoint)
- Timeout handling with fallback error messages
- Network failure tolerance: app degrades to offline mode if backend unreachable
- File: `frontend/src/api/backend.ts` function `fetchApi()`

*Backend Supabase queries:*
- Try/catch wrapping with informative error messages
- Returns 500 or error object in response body for API failures
- Fallback patch detection: uses provided patch or queries latest from DB
- File: `backend/src/lolalytics_api/supabase_repo.py` and endpoint handlers

*League Client integration:*
- Silent failure on client not running (no error thrown, returns `client_running: false`)
- WebSocket auto-reconnect every 5 seconds if connection lost
- Cache invalidation on auth failure (401) to force fresh client info fetch
- File: `league_client_websocket.py`, `league_client_api.py`

*Recommendation engine:*
- Safe integer conversion with fallback to None for non-numeric stats
- Empty team handling (supports solo analysis without teammates)
- Patch fallback to latest if not provided
- File: `recommendation_engine.py` function `get_recommendations()`

## Cross-Cutting Concerns

**Logging:**
- Python: Print statements with `[MODULE_NAME]` prefix (e.g., `[RECOMMENDATIONS]`, `[LEAGUE CLIENT]`)
- TypeScript: Console logs prefixed with `[API]` or component name for frontend events
- No structured logging framework; suitable for development/debugging

**Validation:**
- Frontend: Type safety via TypeScript types from `@counterpick/core`
- Backend: Schema validation via Supabase table definitions; Python type hints (unvalidated at runtime)
- League Client: Enum normalization for roles (`top`, `jungle`, `middle`, `bottom`, `support`) and ranks

**Authentication:**
- Frontend: No auth required (local development; intended for single user)
- Backend: Basic Auth to League Client using riot/password from process args
- Supabase: API key in environment variable `SUPABASE_KEY` (no RLS policies for local use)
- League Client: Self-signed certificate bypassed with `verify=False` in requests library

**Patch Management:**
- Supabase stores multiple patches; frontend can select via PatchSelector component
- Backend `/patches` endpoint returns available patches sorted by date
- Recommendation engine defaults to latest patch if none specified
- ETL upserts new patch data nightly; old patches remain queryable

---

*Architecture analysis: 2026-04-14*
