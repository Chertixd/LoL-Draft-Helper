# External Integrations

**Analysis Date:** 2026-04-14

## APIs & External Services

**Riot Data Dragon (Static Assets):**
- Service: Riot Games static asset CDN for champion, item, rune, and summoner spell data
  - SDK/Client: Native fetch (TypeScript) and requests (Python)
  - Endpoints: 
    - `https://ddragon.leagueoflegends.com/api/versions.json` - Current game patch versions
    - `https://ddragon.leagueoflegends.com/cdn/{version}/data/{locale}/champion.json` - Champion metadata
    - `https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json` - Rune data
    - `https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json` - Item data
    - `https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/summoner.json` - Summoner spell data
  - Used in: `supabase-dataset-updater/src/riot.ts` for ETL pipeline

**Lolalytics (Scraped Analytics):**
- Service: Unofficial League of Legends statistics and matchup data via web scraping
  - Method: HTML/JSON scraping with requests + lxml (Python) or native fetch (TypeScript)
  - Endpoints scraped:
    - Champion statistics by role and patch
    - Enemy matchup win rates (lane opponent data)
    - Team synergy data (ally win rate by role)
    - Damage profiles and stats-by-time windows
  - Used in:
    - `supabase-dataset-updater/src/lolalytics/` - ETL pipeline scraping
    - `counterpick-app/apps/backend/src/lolalytics_api/` - Backend API layer
  - Note: Unofficial API, subject to breaking changes if Lolalytics UI changes

**League Client LCU API (Live Client):**
- Service: Local League of Legends client HTTP API on Windows
  - Auth: Process argument parsing from LeagueClientUx.exe (port + credentials)
  - Protocol: HTTPS with self-signed certificate (SSL verification disabled)
  - Port: Dynamic, extracted from client process arguments
  - Endpoints accessed:
    - `/lol-draft-pick/v1/picks-bans` - Current draft picks/bans
    - `/lol-gameflow/v1/gameflow-phase` - Game state
  - Used in: 
    - `counterpick-app/apps/backend/league_client_api.py` - HTTP REST wrapper
    - `counterpick-app/apps/backend/league_client_auth.py` - Authentication via process inspection
    - `counterpick-app/apps/backend/league_client_websocket.py` - WebSocket connection (optional)
  - Timeout: 2 seconds per request
  - Platform: Windows only (PowerShell integration in `league_client_auth.py`)

## Data Storage

**Databases:**
- Supabase (PostgreSQL-backed)
  - Connection: Via `@supabase/supabase-js` (TypeScript) and `supabase-py` (Python)
  - Environment variables: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (ETL), `SUPABASE_ANON_KEY` (frontend)
  - Tables:
    - `champions` - Champion metadata with i18n (zh_CN translations)
    - `items` - Item data per patch
    - `runes` - Rune data per patch
    - `summoner_spells` - Summoner spell data per patch
    - `patches` - Patch version tracking
    - `champion_stats` - Champion win rates, games, damage profiles by role/patch
    - `matchups` - Enemy matchup data (win rates vs. each opponent)
    - `synergies` - Team synergy data (win rates with allies)
  - Client implementations:
    - `supabase-dataset-updater/src/supabase-etl.ts` - ETL upsert operations
    - `counterpick-app/apps/backend/src/lolalytics_api/supabase_client.py` - Python client wrapper
    - `counterpick-app/apps/backend/src/lolalytics_api/supabase_repo.py` - Repository pattern for queries

**File Storage:**
- Local filesystem only
  - Game assets: `dragontail-15.24.1/` - Riot Data Dragon CDN mirror (static files)
  - Cache: `counterpick-app/apps/backend/cache_data.json` - Persistent JSON cache (24-hour TTL)

**Caching:**
- JSON file cache (Python backend) - 24-hour duration for API responses
- In-memory LRU cache (Python) - `@lru_cache` decorator for Supabase client singleton

## Authentication & Identity

**Auth Provider:**
- Supabase (OAuth + API keys)
  - Service role key: For ETL pipeline (full database access) - `SUPABASE_SERVICE_ROLE_KEY`
  - Anon key: For frontend and client-side queries (limited RLS policies)
  - Environment-based: Loaded via `.env` files and GitHub Actions secrets

**League Client Auth:**
- Custom authentication via process inspection
  - Method: PowerShell script queries Win32_Process for LeagueClientUx.exe command-line arguments
  - Credentials extracted: Port, authentication token (base64 encoded)
  - No user login required - uses local client's built-in auth
  - Implementation: `counterpick-app/apps/backend/league_client_auth.py`

## Monitoring & Observability

**Error Tracking:**
- None detected - Application logs errors to stdout/stderr

**Logs:**
- Console logging (Python print/logging, JavaScript console)
- No centralized logging service

## CI/CD & Deployment

**Hosting:**
- Desktop application (no cloud hosting detected)
- GitHub Actions triggers (ETL pipeline automation only)

**CI Pipeline:**
- GitHub Actions: Automated ETL pipeline execution
  - Workflow file: `.github/workflows/update-dataset.yml`
  - Schedule: Daily at 12:00 UTC (`0 12 * * *` cron)
  - Manual trigger: Workflow dispatch available
  - Actions:
    1. Checkout code
    2. Setup Node.js (LTS) with pnpm cache
    3. Install dependencies
    4. Run `pnpm update` command (executes `supabase-dataset-updater/src/supabase-etl.ts`)
  - Secrets injected: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`

## Environment Configuration

**Required env vars (Backend):**
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Full database access key for ETL
- `SUPABASE_ANON_KEY` - Limited client-side key (optional, for frontend RLS)
- `RIOT_API_KEY` - (if Riot official API integration added later)

**Secrets location:**
- GitHub Actions: Repository secrets (injected into workflow via `${{ secrets.X }}`)
- Local development: `.env` files in respective app directories (not committed)
- Backend: `.env` at `counterpick-app/apps/backend/.env` (loaded via python-dotenv)
- ETL: Environment variables injected by GitHub Actions workflow

## Webhooks & Callbacks

**Incoming:**
- None detected - Application is pull-based

**Outgoing:**
- None detected - No external service webhooks

## Third-Party Libraries

**Notable Node packages:**
- `axios` - HTTP client for frontend API calls
- `socket.io-client` - WebSocket client for real-time updates from backend
- `vue-router` - Client-side routing
- `tsx` - TypeScript executor for Node scripts

**Notable Python packages:**
- `requests` - HTTP client for web scraping and API calls
- `lxml` - HTML/XML parsing for Lolalytics scraping
- `websocket-client` - WebSocket client (optional, for LCU WebSocket fallback)
- `python-socketio` - SocketIO server for WebSocket support in Flask

---

*Integration audit: 2026-04-14*
