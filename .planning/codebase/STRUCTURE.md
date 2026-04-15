# Codebase Structure

**Analysis Date:** 2026-04-14

## Directory Layout

```
F:\Dokumente\Archiv\Riot Api/
├── counterpick-app/                    # pnpm monorepo with Turbo
│   ├── apps/
│   │   ├── backend/                    # Python Flask API server
│   │   │   ├── backend.py              # Flask app entry, endpoints
│   │   │   ├── recommendation_*.py     # Scoring engine and config
│   │   │   ├── league_client_*.py      # LCU integration (auth, HTTP, WebSocket)
│   │   │   ├── live_client_api.py      # Live game state queries
│   │   │   ├── src/lolalytics_api/     # Data access layer
│   │   │   │   ├── supabase_*.py       # Repository pattern for DB queries
│   │   │   │   ├── main.py             # Lolalytics scraper integration
│   │   │   │   ├── config.py           # Env config loading
│   │   │   │   └── errors.py           # Custom exceptions
│   │   │   ├── cache_data.json         # 24hr champion metadata cache
│   │   │   ├── package.json            # Node.js metadata (for workspace)
│   │   │   └── pyrightconfig.json      # TypeScript-like type checking
│   │   │
│   │   └── frontend/                   # Vue 3 + Vite + Pinia app
│   │       ├── src/
│   │       │   ├── main.ts             # Vue app entry, router, Pinia setup
│   │       │   ├── App.vue             # Root component, header, router outlet
│   │       │   ├── api/
│   │       │   │   └── backend.ts      # Fetch client for Flask endpoints
│   │       │   ├── stores/             # Pinia state management
│   │       │   │   ├── draft.ts        # Draft state, WebSocket, recommendations
│   │       │   │   ├── champion.ts     # Champion metadata cache
│   │       │   │   └── settings.ts     # User preferences, patch selection
│   │       │   ├── components/
│   │       │   │   ├── common/         # Reusable: PatchSelector, RankSelector
│   │       │   │   └── draft/          # Draft-specific: DraftTeam, DraftSummary, RoleSelector, RecommendationsList
│   │       │   ├── views/              # Page-level components
│   │       │   │   ├── DraftTrackerView.vue      # Main draft analysis UI
│   │       │   │   └── ChampionLookupView.vue    # Matchup/synergy explorer
│   │       │   └── assets/styles.css
│   │       ├── public/                 # Static assets
│   │       ├── vite.config.ts          # Vite bundler config
│   │       └── tsconfig.json           # TypeScript config
│   │
│   ├── packages/
│   │   └── core/                       # Shared TypeScript types package
│   │       ├── src/
│   │       │   ├── index.ts            # Export barrel
│   │       │   ├── types/
│   │       │   │   ├── champion.ts     # Champion, ChampionRoleProbabilities
│   │       │   │   ├── recommendation.ts   # RecommendationRequest, RecommendationResponse
│   │       │   │   └── draft.ts        # DraftPick, DraftBan, etc.
│   │       │   ├── constants/
│   │       │   │   └── roles.ts        # Role constants (top, jungle, etc.)
│   │       │   └── utils/
│   │       │       └── role-utils.ts   # Role string normalization
│   │       └── package.json            # Published as @counterpick/core
│   │
│   ├── pnpm-workspace.yaml             # Declares apps/ and packages/
│   ├── turbo.json                      # Turbo build orchestration
│   ├── package.json                    # Root workspace dependencies
│   ├── tsconfig.json                   # Root TypeScript config
│   └── README.md
│
├── supabase-dataset-updater/           # Node.js ETL package (separate from monorepo)
│   ├── src/
│   │   ├── supabase-etl.ts             # Main ETL orchestration, upsert logic
│   │   ├── riot.ts                     # Riot API client (champions, items, runes)
│   │   ├── utils.ts                    # Helper functions
│   │   ├── lolalytics/
│   │   │   └── index.ts                # Lolalytics scraper
│   │   └── models/
│   │       └── Role.ts                 # Role type definitions
│   ├── .github/workflows/              # GitHub Actions CI/CD
│   ├── package.json
│   └── tsconfig.json
│
├── dragontail-15.24.1/                 # Static Riot game data (assets, images)
│   ├── img/
│   │   ├── champion/
│   │   ├── item/
│   │   └── spell/
│   ├── data/                           # Localized champion JSON definitions
│   │   ├── en_US/
│   │   ├── de_DE/
│   │   └── [other locales]
│   └── css/, js/
│
└── docs/                               # Project documentation
    └── superpowers/specs/              # Design specs
```

## Directory Purposes

**counterpick-app/apps/backend/**
- Purpose: REST API server with League Client integration
- Contains: Flask endpoints, recommendation scoring, LCU bridge, data repositories
- Key files: `backend.py` (entry), `recommendation_engine.py` (scoring), `league_client_websocket.py` (real-time)

**counterpick-app/apps/backend/src/lolalytics_api/**
- Purpose: Reusable data access and config layer
- Contains: Supabase repository functions, Supabase client setup, error classes
- Key files: `supabase_repo.py` (query functions), `supabase_client.py` (connection), `main.py` (Lolalytics scraper)

**counterpick-app/apps/frontend/src/stores/**
- Purpose: Pinia state management for frontend
- Contains: Draft state (picks/bans/role), champion metadata cache, user settings, recommendation results
- Key files: `draft.ts` (core state + WebSocket), `champion.ts` (metadata), `settings.ts` (patch/rank filters)

**counterpick-app/apps/frontend/src/components/draft/**
- Purpose: Vue components specific to draft analysis UI
- Contains: Team display, role selectors, recommendations list, pick/ban cards
- Key files: `DraftTeam.vue` (renders picks/bans grid), `RecommendationsList.vue` (scored champions), `RoleSelector.vue` (manual role override)

**counterpick-app/packages/core/src/types/**
- Purpose: TypeScript type definitions (single source of truth)
- Contains: Interfaces for API requests/responses, draft data structures, champion data
- Key files: `recommendation.ts` (scoring types), `draft.ts` (pick/ban structure), `champion.ts` (metadata types)

**supabase-dataset-updater/src/**
- Purpose: Nightly ETL pipeline
- Contains: Riot API scraper, Lolalytics HTML parser, Supabase upsert orchestration
- Key files: `supabase-etl.ts` (main), `riot.ts` (API client), `lolalytics/index.ts` (scraper)

## Key File Locations

**Entry Points:**
- Frontend app: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/main.ts`
- Backend app: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/backend.py`
- ETL pipeline: `F:\Dokumente\Archiv\Riot Api/supabase-dataset-updater/src/supabase-etl.ts`

**Configuration:**
- Frontend Vite: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/vite.config.ts`
- Backend Flask: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/backend.py` (app initialization)
- Recommendation weights: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/recommendation_config.py`
- Supabase connection: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/src/lolalytics_api/supabase_client.py` and `config.py`
- Workspace config: `F:\Dokumente\Archiv\Riot Api/counterpick-app/pnpm-workspace.yaml`, `turbo.json`

**Core Logic:**
- Recommendation scoring: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/recommendation_engine.py`
- Wilson Score calculation: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/recommendation_engine.py` function `wilson_score()` and `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` function `_wilson_score()`
- League Client API bridge: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/league_client_api.py`
- League Client WebSocket: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/league_client_websocket.py`
- LCU auth extraction: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/league_client_auth.py`

**Data Access:**
- Supabase repository (champions, stats, matchups, synergies): `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py`
- Supabase client initialization: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/src/lolalytics_api/supabase_client.py`
- Flask endpoint handlers: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/backend.py` (contains /api/recommendations, /api/champion/*, /api/champions/list, etc.)

**Testing:**
- No test files found in codebase; testing not yet implemented

**Frontend State Management:**
- Draft store: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/stores/draft.ts`
- Champion store: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/stores/champion.ts`
- Settings store: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/stores/settings.ts`

**Frontend API Client:**
- Backend HTTP client: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/api/backend.ts` (all fetchApi calls to Flask)

## Naming Conventions

**Files:**
- Python modules: `snake_case` (e.g., `league_client_websocket.py`, `supabase_repo.py`)
- Vue components: `PascalCase.vue` (e.g., `DraftTeam.vue`, `RecommendationsList.vue`)
- TypeScript/JavaScript: `camelCase.ts` or `PascalCase.ts` for classes/interfaces (e.g., `backend.ts`, `vite.config.ts`)
- Directories: `kebab-case` for packages, `snake_case` for Python modules, `lowercase` for assets (e.g., `lolalytics_api/`, `common/`, `components/`)

**Functions:**
- Python: `snake_case` (e.g., `get_recommendations()`, `normalize_champion_name()`, `wilson_score()`)
- TypeScript: `camelCase` (e.g., `getRecommendations()`, `getChampionStats()`, `fetchApi()`)
- Vue methods/computed: `camelCase` (e.g., `loadAnalysisData()`, `effectiveRole`)

**Variables:**
- Python: `snake_case` (e.g., `my_team`, `enemy_team`, `is_blind_pick`)
- TypeScript/Vue: `camelCase` (e.g., `myTeam`, `enemyTeam`, `isBlindPick`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MANUAL_ROLE_OVERRIDE`, `CACHE_DURATION`, `CONFIDENCE_Z`)

**Types:**
- TypeScript interfaces: `PascalCase` (e.g., `RecommendationRequest`, `DraftPick`, `PickScore`)
- TypeScript enums/unions: `PascalCase` (e.g., `Role`, `RoleLockType`)

## Where to Add New Code

**New Frontend Component:**
- Placement: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/components/{category}/{ComponentName}.vue`
- Categories: `common/` for reusable, `draft/` for draft-specific
- Follow: Setup `<script setup lang="ts">`, import types from `@counterpick/core`, use stores via `useStore()`
- Example: New "MatchupMatrix" component → `components/draft/MatchupMatrix.vue`

**New Backend Endpoint:**
- Placement: Add route in `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/backend.py`
- Pattern: `@app.route('/api/path', methods=['GET/POST'])` with CORS support
- Data access: Call functions from `lolalytics_api.supabase_repo`
- Response: Return `jsonify({'success': True, 'data': result})`
- Example: `/api/patch-notes` → fetch from Supabase `patches` table via supabase_repo

**New Recommendation Feature:**
- Scoring logic: Modify `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/recommendation_engine.py` function `get_recommendations()`
- Configuration: Add weights/thresholds to `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/recommendation_config.py`
- Type signature: Update `RecommendationRequest` and `RecommendationItem` in `F:\Dokumente\Archiv\Riot Api/counterpick-app/packages/core/src/types/recommendation.ts`
- Frontend: Update `frontend/src/stores/draft.ts` to consume new fields

**New Pinia Store:**
- Placement: `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/stores/{storeName}.ts`
- Pattern: Export named `defineStore('storeName', () => { ... })`
- Import in views: `import { useStoreName } from '@/stores/{storeName}'`
- Example: `useGameState` → `stores/game.ts`

**Database Schema Change:**
- Supabase: Create/modify table via Supabase dashboard
- ETL sync: Update `F:\Dokumente\Archiv\Riot Api/supabase-dataset-updater/src/supabase-etl.ts` to include new table in upsert logic
- Data access: Add query function to `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py`
- Backend endpoint: Add Flask route to expose data
- Frontend: Call new endpoint from `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/api/backend.ts`

**New Shared Type:**
- Placement: `F:\Dokumente\Archiv\Riot Api/counterpick-app/packages/core/src/types/{category}.ts`
- Export: Add to `F:\Dokumente\Archiv\Riot Api/counterpick-app/packages/core/src/index.ts` barrel
- Usage: Import as `import type { TypeName } from '@counterpick/core'` in frontend/backend TypeScript files
- Example: New `MatchupFilter` type → `types/champion.ts`, re-export from `index.ts`

**New Utility Function:**
- Shared (TS): `F:\Dokumente\Archiv\Riot Api/counterpick-app/packages/core/src/utils/{utilName}.ts`
- Frontend-only (TS): `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/src/utils/{utilName}.ts`
- Backend-only (Py): `F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/{moduleName}.py` or `src/lolalytics_api/{moduleName}.py`

## Special Directories

**F:\Dokumente\Archiv\Riot Api/counterpick-app/node_modules/**
- Purpose: pnpm monorepo dependencies (root-level shared deps)
- Generated: Yes (run `pnpm install`)
- Committed: No (git-ignored)

**F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/frontend/node_modules/**
- Purpose: Frontend-specific dependencies (Vite, Vue, TypeScript)
- Generated: Yes (run `pnpm install` from root)
- Committed: No (git-ignored)

**F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/__pycache__/**
- Purpose: Python compiled bytecode cache
- Generated: Yes (created when Python modules imported)
- Committed: No (git-ignored)

**F:\Dokumente\Archiv\Riot Api/counterpick-app/apps/backend/cache_data.json**
- Purpose: Local 24-hour cache of champion metadata to reduce Supabase queries
- Generated: Yes (created by backend at runtime)
- Committed: No (ephemeral, regenerated daily)
- Format: JSON mapping champion names to keys and metadata

**F:\Dokumente\Archiv\Riot Api/dragontail-15.24.1/**
- Purpose: Static Riot game data (champion images, item icons, localized data)
- Generated: No (downloaded from Riot CDN as archive)
- Committed: Yes (included in repo for offline reference)
- Usage: Frontend may reference image paths; mostly documentation

---

*Structure analysis: 2026-04-14*
