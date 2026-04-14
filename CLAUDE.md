<!-- GSD:project-start source:PROJECT.md -->
## Project

**LoL Draft Analyzer**

A desktop tool that reads the live champion-select state from the League of Legends client and produces per-role pick recommendations scored against current meta data. The product currently exists as a manually-started Flask + Vue web app with a Supabase backend; this milestone packages it into a one-click Windows installer so non-technical LoL players can download, run, and auto-update it like any normal desktop app.

**Core Value:** Zero-friction delivery: a non-technical LoL player downloads one installer and has working draft recommendations — no Python, no Node, no credentials, no command line.

### Constraints

- **Platform:** Windows 10 and Windows 11 only for v1 — macOS/Linux deferred.
- **Tech stack (locked):** Flask + Flask-SocketIO backend, Vue 3 + Vite frontend, Tauri (Rust) desktop host, PyInstaller for sidecar packaging, Supabase remains source of truth for the ETL, GitHub Pages as CDN.
- **No code signing in v1:** AV false-positive mitigation is procedural (UPX disabled, hashes published, README guidance, Microsoft submissions) — an EV certificate is out of scope.
- **Non-commercial release:** No budget for paid signing, telemetry, or crash-reporting SaaS.
- **Installer size:** ≤ 100 MB as a success criterion.
- **Installation model:** Installer must complete on a clean Windows machine without admin rights.
- **Privacy:** No telemetry, no network calls beyond CDN reads and Riot's own LCU; log files stay local.
- **Data path:** Installed clients never talk to Supabase; all read data flows through the public GitHub Pages CDN.
- **Minimum-invasive change:** The Flask/Socket.IO code path stays structurally unchanged — the sidecar is the same backend, reached over localhost.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.10+ - Backend (Flask application, lolalytics-api package)
- TypeScript 5.3+ - Frontend (Vue 3) and ETL pipeline
- Vue 3 4.x - UI framework and reactive components
- JavaScript (Node.js environment for pnpm/Turbo)
- Shell/PowerShell - Windows process interaction for League Client auth
## Runtime
- Node.js 18.0.0+ - Required by monorepo and ETL pipeline
- Python 3.10+ - Backend runtime
- pnpm 9.2.0 - Node package manager (monorepo orchestration)
- pnpm 9.2.0 - Primary (enforced via packageManager field)
- pip - Python package manager
- setuptools - Python package build system
## Frameworks
- Flask - Python web framework for REST API backend (`counterpick-app/apps/backend/backend.py`)
- Flask-CORS - Cross-Origin Resource Sharing support
- Flask-SocketIO 5.3.0+ - WebSocket support for real-time updates
- Vue 3 3.4.0+ - Frontend framework (`counterpick-app/apps/frontend/`)
- Pinia 2.1.7 - Vue state management store
- Vue Router 4.2.5 - Client-side routing
- Vite 5.0.10+ - Frontend build tool and dev server
- Turbo 2.5.3+ - Monorepo build orchestration
- TypeScript 5.3.2 - Type checking and transpilation
- tsx 4.6.1+ - TypeScript executor for Node scripts
- vue-tsc 1.8.25 - Vue template type checking
- Vitejs/plugin-vue 4.5.2 - Vite Vue 3 integration
- pytest - Python test framework (specified in `pyproject.toml` optional dependencies)
## Key Dependencies
- supabase 2.4.0+ - PostgreSQL database client via supabase-js and supabase-py SDK
- socket.io-client 4.7.2 - WebSocket client for real-time frontend updates
- python-socketio 5.9.0+ - WebSocket support for Flask backend
- requests - HTTP client for external API calls (Lolalytics, Data Dragon)
- lxml - HTML/XML parsing for Lolalytics scraping
- axios 1.6.2+ - HTTP client for Vue frontend API calls
- websocket-client 1.6.0+ - Standalone WebSocket client
- python-dotenv - Environment variable loading for configuration
- dotenv - Node environment variable loading
- urllib3 - HTTP client with SSL support (League Client API)
- httpcore, httpx - Optional HTTP libraries for error handling (backend.py)
## Configuration
- `.env` files per workspace (root, backend) - Supabase credentials (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
- pnpm-workspace.yaml - Defines monorepo structure with frontend, backend, core packages
- tsconfig.json files - TypeScript compilation targets at root, frontend, and core package levels
- `vite.config.ts` (inferred) - Frontend build configuration
- `pyproject.toml` - Python package build configuration and dependencies
- `requirements.txt` - Python pip dependencies snapshot
## Platform Requirements
- Windows OS (PowerShell integration for League Client authentication in `league_client_auth.py`)
- Python 3.10+ installed and in PATH
- Node.js 18.0.0+ installed
- League of Legends client running locally for LCU API access
- Deployment target: Desktop application (no explicit server deployment)
- Supabase cloud database (PostgreSQL)
- GitHub Actions for automated ETL pipeline (`supabase-dataset-updater/.github/workflows/update-dataset.yml`)
## Architecture Pattern
- pnpm workspaces at `counterpick-app/` with three sub-packages:
- Separate ETL project at `supabase-dataset-updater/` with GitHub Actions automation
- Game assets stored locally at `dragontail-15.24.1/` (Riot Data Dragon CDN mirror)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case` for module/file names: `backend.py`, `recommendation_engine.py`, `league_client_api.py`
- `snake_case` for function names: `display_ranks()`, `normalize_champion_name()`, `_get_lcu_response()`
- `UPPER_SNAKE_CASE` for module-level constants: `CACHE_FILE`, `CACHE_DURATION`, `LEAGUE_CLIENT_TIMEOUT`
- Private functions prefixed with `_`: `_sort_by_rank()`, `_sort_by_lane()`, `_wilson_score()`
- `camelCase` for function/variable names: `getChampionsList()`, `checkBackendHealth()`, `championStore`
- `PascalCase` for Vue components: `DraftTrackerView.vue`, `DraftTeam.vue`, `PatchSelector.vue`, `RecommendationsList.vue`
- `camelCase` for store composables: `useChampionStore`, `useDraftStore`, `useSettingsStore`
- `camelCase` for API functions: `getChampionMatchups()`, `getChampionSynergies()`, `setRoleOverride()`
- `UPPER_SNAKE_CASE` for constants: `CACHE_TTL`, `API_BASE_URL`, `LEAGUE_CLIENT_TIMEOUT`
- `kebab-case` for CSS classes: `.app-container`, `.header-left`, `.status-badge`, `.nav-link`
- Scoped styles with `<style scoped>` pattern (file: `/f/Dokumente/Archiv/Riot Api/counterpick-app/apps/frontend/src/App.vue`)
## Code Style
- 4-space indentation (standard Python)
- Docstrings use double quotes with parameter documentation in `:param name:` format
- Mixed language comments: German (`Normalisiert Patch-Version`, `Löst das "Low Sample Size"-Problem`) and English in same file
- Example from `backend.py` lines 1-4: German comment `"""Flask-Backend für lolalytics-api Integration"""`
- Example from `src/lolalytics_api/main.py` lines 8-12: English docstring format with `:param:` and `:return:`
- 4-space indentation via vite/tsconfig (inferred from project)
- Strict mode enabled: `compilerOptions.strict: true` in `tsconfig.json`
- JSDoc comments with `/**` blocks: see `src/api/backend.ts` lines 1-4, 13-17
- Comments in German describing business logic: `// Manuelle Rollen-Überschreibung` (line 33, draft.ts)
- Uses `<script setup lang="ts">` pattern exclusively (files: `App.vue`, `DraftTrackerView.vue`, `champion.ts` store)
- Reactive state declared with `ref<Type>()` for single values and `computed()` for derived state
- Store pattern using Pinia with `defineStore()` → composition function pattern, not options API
- Example from `champion.ts` lines 15-22: State refs, computed properties, and action functions returned in single object
## Import Organization
- `@/*` → `./src/*` (TypeScript files can use `@/api`, `@/components`, `@/stores`)
- `@counterpick/core` → `../../packages/core/src` (shared type definitions)
## Error Handling
- Custom exception classes in `errors.py`: `InvalidLane(Exception)` and `InvalidRank(Exception)` take parameters and format messages
- Try/except with specific error types: `except KeyError:` raises custom `InvalidRank(rank)` (lines 125-128, `main.py`)
- Try/except in Flask endpoints for catching `requests.exceptions.ConnectionError` and generic `Exception`
- Cache invalidation on auth errors: `_client_info_cache = None` when 401 received (lines 59-61, `league_client_api.py`)
- Safe conversion functions: `safe_int()` function returns `None` on error rather than raising (line 29, `recommendation_engine.py`)
- Async/await with try/catch blocks in API calls
- Retry logic with exponential backoff: `fetchApi()` function accepts `retries` and `retryDelay` parameters (lines 23-66, `backend.ts`)
- Error coercion: `error instanceof Error ? error : new Error(String(error))` (line 54)
- Console warnings for recoverable errors: `console.warn()` used for failed API calls, not logged to backend
## Logging
- `print()` statements for debug output: `print("[LEAGUE CLIENT] Authentifizierungsfehler (401) - Cache invalidiert")`
- Conditional logging with `if __debug__:` guard (line 76, `league_client_api.py`)
- Prefixed messages with brackets: `[LEAGUE CLIENT]`, `[API]`
- No structured logging framework (print-based only)
- `console.warn()` for non-critical issues: `console.warn('[API] Server-Fehler...')`
- `console.error()` for exceptions in stores
- Prefixed messages: `[API]` for backend calls
## Comments
- Complex algorithms: Wilson Score calculation has multi-line comment explaining statistical concept (lines 55-65, `recommendation_engine.py`)
- Business logic intent: German comments explain role mappings and synergy decisions
- Parsing logic: XPath explanations and section references (lines 200-212, `main.py`)
- German preferred for business logic and UI concerns: `Normalisiert Champion-Namen`, `Löst das "Low Sample Size"-Problem`
- English for technical/code explanations: `:param:`, `:return:` in docstrings
- Mixed in same files is standard practice
- Multiline JSDoc blocks with `/**` for public functions (lines 1-4, `backend.ts`: Backend API Client)
- Parameter types documented: `:Promise<T>`, return types via TypeScript signature
- Simple single-line comments for inline explanations
## Function Design
- Python functions: 10-80 lines typical (web scraping functions with xPath loops are longer)
- TypeScript helpers: 5-40 lines (short async utilities preferred)
- Store actions: 20-50 lines (API calls + state updates)
- Python: positional args with defaults: `display_ranks(display: bool = True)` (line 7, `main.py`)
- TypeScript: destructuring for objects in stores, positional for simple API calls
- Type hints used throughout Python: `def wilson_score(wins: int, n: int, z: float = 1.44) -> float:`
- Python: return JSON strings: `return json.dumps(result, indent=4)` (lines 217, 263, `main.py`)
- TypeScript: return typed promises: `Promise<{ status: string }>` with full response object shape
- Stores return plain state objects, not wrapped in additional layers
## Module Design
- Single responsibility: `recommendation_engine.py` handles scoring, `league_client_api.py` handles LCU calls
- Helper functions prefixed with `_`: `_sort_by_rank()`, `_sort_by_lane()` are private to `main.py`
- No barrel files (Python uses direct imports)
- Barrel exports in stores: `src/stores/index.ts` exists (likely re-exports all stores)
- No barrel files in `src/components/` or `src/api/` (direct imports used)
- API functions grouped by feature: `getChampionsList()`, `getPrimaryRoles()`, `getChampionMatchups()` all in `src/api/backend.ts`
- `defineStore(name, () => { ... })` composition pattern: defines state with `ref()`, computed properties, and action functions
- Single object returned with all exports: state refs, computed getters, and action functions mixed
- Example from `champion.ts` lines 224-246: returns object with `championsList`, `championsLoaded`, `loadChampionData()`, etc.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Decoupled frontend and backend with REST endpoints for recommendations and data queries
- Real-time WebSocket connection from Flask backend to League Client for live draft state updates
- Recommendation engine as core scoring service with Wilson Score statistical confidence calculation
- Repository pattern for data access layer abstracting Supabase queries
- Modular Python packages (lolalytics_api) for reusable business logic
## Layers
- Purpose: Interactive draft analysis UI with real-time recommendation display
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/`
- Contains: Vue components, Pinia stores, API client, assets
- Depends on: Flask REST API (`/api/*` endpoints), shared types from `@counterpick/core`
- Used by: Web browser via Vite dev server or built artifacts
- Purpose: HTTP REST endpoints for champion data, recommendations, matchups; WebSocket gateway for League Client events
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/`
- Contains: Flask app, league client integrations, recommendation engine, lolalytics_api module
- Depends on: Supabase client, League Client (via HTTP/WebSocket), lolalytics_api package
- Used by: Frontend Vue app, ETL pipeline
- Purpose: Abstraction layer for Supabase queries using repository pattern
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py`
- Contains: Query functions for champions, stats, matchups, synergies, items, runes
- Depends on: Supabase Python client
- Used by: Recommendation engine, Flask endpoints
- Purpose: Single source of truth for request/response interfaces
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/packages/core/src/`
- Contains: TypeScript types for recommendations, drafts, champions, roles
- Depends on: None (zero-dependency package)
- Used by: Frontend app, API documentation
- Purpose: Nightly data synchronization from Riot API and Lolalytics to Supabase
- Location: `F:\Dokumente\Archiv\Riot Api/supabase-dataset-updater/src/`
- Contains: Riot API client, Lolalytics scraper, Supabase upsert logic
- Depends on: Supabase client, Riot API, HTML scraper
- Used by: GitHub Actions scheduled workflow
## Data Flow
- `draft.ts`: Draft state (team picks/bans, my role, recommendations, socket connection)
- `champion.ts`: Champion metadata cache
- `settings.ts`: Patch selection, rank filters
- JSON cache file (`cache_data.json`) for champion metadata (24hr TTL)
- In-memory WebSocket/Socket.io connection state
- Manual role overrides (`MANUAL_ROLE_OVERRIDE`) per session
## Key Abstractions
- Purpose: Statistically confident ranking of champions considering low sample sizes
- File: `backend/recommendation_engine.py` function `wilson_score()`
- Pattern: Lower confidence bound of win rate binomial proportion at z=1.44 (85% confidence)
- Applied to: Base winrate, matchups, synergies to filter unreliable (<50 games) stats
- Example: Champion with 10 wins/20 games gets lower score than 100 wins/200 games even if raw % is same
- Purpose: Combine base, counter, and synergy scores with dynamic weights per role
- File: `backend/recommendation_engine.py` function `get_recommendations()`
- Pattern: Weighted average of three dimensions:
- Normalization: All subscores mapped to 0-100 range before weighting
- Purpose: Single point of champion data resolution and stat queries
- File: `backend/src/lolalytics_api/supabase_repo.py`
- Pattern: Public functions like `get_champion_stats()`, `get_matchups()`, `get_synergies()` that:
- Abstraction benefit: Centralized champion name normalization, consistent Wilson Score application
- Purpose: Convert League Client process args and APIs into real-time draft state
- Files: `league_client_auth.py`, `league_client_api.py`, `league_client_websocket.py`
- Pattern: 
## Entry Points
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/main.ts`
- Triggers: User runs `pnpm dev` or accesses built app
- Responsibilities: Create Vue app, register Pinia stores, set up router (Draft Tracker at `/draft`, Lookup at `/lookup`)
- Location: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/backend.py`
- Triggers: User runs Python backend (typically `python backend.py` or via start script)
- Responsibilities: 
- Location: `F:\Dokumente\Archiv\Riot Api/supabase-dataset-updater/src/supabase-etl.ts`
- Triggers: GitHub Actions scheduled workflow (`.github/workflows/*.yml`)
- Responsibilities: 
## Error Handling
- Exponential backoff retry on 5xx errors (up to 3 retries per endpoint)
- Timeout handling with fallback error messages
- Network failure tolerance: app degrades to offline mode if backend unreachable
- File: `frontend/src/api/backend.ts` function `fetchApi()`
- Try/catch wrapping with informative error messages
- Returns 500 or error object in response body for API failures
- Fallback patch detection: uses provided patch or queries latest from DB
- File: `backend/src/lolalytics_api/supabase_repo.py` and endpoint handlers
- Silent failure on client not running (no error thrown, returns `client_running: false`)
- WebSocket auto-reconnect every 5 seconds if connection lost
- Cache invalidation on auth failure (401) to force fresh client info fetch
- File: `league_client_websocket.py`, `league_client_api.py`
- Safe integer conversion with fallback to None for non-numeric stats
- Empty team handling (supports solo analysis without teammates)
- Patch fallback to latest if not provided
- File: `recommendation_engine.py` function `get_recommendations()`
## Cross-Cutting Concerns
- Python: Print statements with `[MODULE_NAME]` prefix (e.g., `[RECOMMENDATIONS]`, `[LEAGUE CLIENT]`)
- TypeScript: Console logs prefixed with `[API]` or component name for frontend events
- No structured logging framework; suitable for development/debugging
- Frontend: Type safety via TypeScript types from `@counterpick/core`
- Backend: Schema validation via Supabase table definitions; Python type hints (unvalidated at runtime)
- League Client: Enum normalization for roles (`top`, `jungle`, `middle`, `bottom`, `support`) and ranks
- Frontend: No auth required (local development; intended for single user)
- Backend: Basic Auth to League Client using riot/password from process args
- Supabase: API key in environment variable `SUPABASE_KEY` (no RLS policies for local use)
- League Client: Self-signed certificate bypassed with `verify=False` in requests library
- Supabase stores multiple patches; frontend can select via PatchSelector component
- Backend `/patches` endpoint returns available patches sorted by date
- Recommendation engine defaults to latest patch if none specified
- ETL upserts new patch data nightly; old patches remain queryable
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
