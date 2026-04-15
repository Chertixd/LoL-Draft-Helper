# Technology Stack

**Analysis Date:** 2026-04-14

## Languages

**Primary:**
- Python 3.10+ - Backend (Flask application, lolalytics-api package)
- TypeScript 5.3+ - Frontend (Vue 3) and ETL pipeline
- Vue 3 4.x - UI framework and reactive components

**Secondary:**
- JavaScript (Node.js environment for pnpm/Turbo)
- Shell/PowerShell - Windows process interaction for League Client auth

## Runtime

**Environment:**
- Node.js 18.0.0+ - Required by monorepo and ETL pipeline
- Python 3.10+ - Backend runtime
- pnpm 9.2.0 - Node package manager (monorepo orchestration)

**Package Manager:**
- pnpm 9.2.0 - Primary (enforced via packageManager field)
- pip - Python package manager
- setuptools - Python package build system

## Frameworks

**Core:**
- Flask - Python web framework for REST API backend (`counterpick-app/apps/backend/backend.py`)
- Flask-CORS - Cross-Origin Resource Sharing support
- Flask-SocketIO 5.3.0+ - WebSocket support for real-time updates
- Vue 3 3.4.0+ - Frontend framework (`counterpick-app/apps/frontend/`)
- Pinia 2.1.7 - Vue state management store
- Vue Router 4.2.5 - Client-side routing

**Build/Dev:**
- Vite 5.0.10+ - Frontend build tool and dev server
- Turbo 2.5.3+ - Monorepo build orchestration
- TypeScript 5.3.2 - Type checking and transpilation
- tsx 4.6.1+ - TypeScript executor for Node scripts
- vue-tsc 1.8.25 - Vue template type checking
- Vitejs/plugin-vue 4.5.2 - Vite Vue 3 integration

**Testing:**
- pytest - Python test framework (specified in `pyproject.toml` optional dependencies)

## Key Dependencies

**Critical:**
- supabase 2.4.0+ - PostgreSQL database client via supabase-js and supabase-py SDK
- socket.io-client 4.7.2 - WebSocket client for real-time frontend updates
- python-socketio 5.9.0+ - WebSocket support for Flask backend
- requests - HTTP client for external API calls (Lolalytics, Data Dragon)
- lxml - HTML/XML parsing for Lolalytics scraping

**Infrastructure:**
- axios 1.6.2+ - HTTP client for Vue frontend API calls
- websocket-client 1.6.0+ - Standalone WebSocket client
- python-dotenv - Environment variable loading for configuration
- dotenv - Node environment variable loading

**API/HTTP:**
- urllib3 - HTTP client with SSL support (League Client API)
- httpcore, httpx - Optional HTTP libraries for error handling (backend.py)

## Configuration

**Environment:**
- `.env` files per workspace (root, backend) - Supabase credentials (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
- pnpm-workspace.yaml - Defines monorepo structure with frontend, backend, core packages
- tsconfig.json files - TypeScript compilation targets at root, frontend, and core package levels

**Build:**
- `vite.config.ts` (inferred) - Frontend build configuration
- `pyproject.toml` - Python package build configuration and dependencies
- `requirements.txt` - Python pip dependencies snapshot

## Platform Requirements

**Development:**
- Windows OS (PowerShell integration for League Client authentication in `league_client_auth.py`)
- Python 3.10+ installed and in PATH
- Node.js 18.0.0+ installed
- League of Legends client running locally for LCU API access

**Production:**
- Deployment target: Desktop application (no explicit server deployment)
- Supabase cloud database (PostgreSQL)
- GitHub Actions for automated ETL pipeline (`supabase-dataset-updater/.github/workflows/update-dataset.yml`)

## Architecture Pattern

**Monorepo Structure:**
- pnpm workspaces at `counterpick-app/` with three sub-packages:
  - `apps/frontend` - Vue 3 SPA
  - `apps/backend` - Flask REST + WebSocket server
  - `packages/core` - Shared TypeScript types
- Separate ETL project at `supabase-dataset-updater/` with GitHub Actions automation
- Game assets stored locally at `dragontail-15.24.1/` (Riot Data Dragon CDN mirror)

---

*Stack analysis: 2026-04-14*
