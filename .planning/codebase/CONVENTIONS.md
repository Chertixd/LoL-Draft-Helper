# Coding Conventions

**Analysis Date:** 2026-04-14

## Naming Patterns

**Python Files:**
- `snake_case` for module/file names: `backend.py`, `recommendation_engine.py`, `league_client_api.py`
- `snake_case` for function names: `display_ranks()`, `normalize_champion_name()`, `_get_lcu_response()`
- `UPPER_SNAKE_CASE` for module-level constants: `CACHE_FILE`, `CACHE_DURATION`, `LEAGUE_CLIENT_TIMEOUT`
- Private functions prefixed with `_`: `_sort_by_rank()`, `_sort_by_lane()`, `_wilson_score()`

**TypeScript/Vue Files:**
- `camelCase` for function/variable names: `getChampionsList()`, `checkBackendHealth()`, `championStore`
- `PascalCase` for Vue components: `DraftTrackerView.vue`, `DraftTeam.vue`, `PatchSelector.vue`, `RecommendationsList.vue`
- `camelCase` for store composables: `useChampionStore`, `useDraftStore`, `useSettingsStore`
- `camelCase` for API functions: `getChampionMatchups()`, `getChampionSynergies()`, `setRoleOverride()`
- `UPPER_SNAKE_CASE` for constants: `CACHE_TTL`, `API_BASE_URL`, `LEAGUE_CLIENT_TIMEOUT`

**CSS/Styling in Vue:**
- `kebab-case` for CSS classes: `.app-container`, `.header-left`, `.status-badge`, `.nav-link`
- Scoped styles with `<style scoped>` pattern (file: `/f/Dokumente/Archiv/Riot Api/counterpick-app/apps/frontend/src/App.vue`)

## Code Style

**Python Formatting:**
- 4-space indentation (standard Python)
- Docstrings use double quotes with parameter documentation in `:param name:` format
- Mixed language comments: German (`Normalisiert Patch-Version`, `Löst das "Low Sample Size"-Problem`) and English in same file
- Example from `backend.py` lines 1-4: German comment `"""Flask-Backend für lolalytics-api Integration"""`
- Example from `src/lolalytics_api/main.py` lines 8-12: English docstring format with `:param:` and `:return:`

**TypeScript Formatting:**
- 4-space indentation via vite/tsconfig (inferred from project)
- Strict mode enabled: `compilerOptions.strict: true` in `tsconfig.json`
- JSDoc comments with `/**` blocks: see `src/api/backend.ts` lines 1-4, 13-17
- Comments in German describing business logic: `// Manuelle Rollen-Überschreibung` (line 33, draft.ts)

**Vue 3 Composition API:**
- Uses `<script setup lang="ts">` pattern exclusively (files: `App.vue`, `DraftTrackerView.vue`, `champion.ts` store)
- Reactive state declared with `ref<Type>()` for single values and `computed()` for derived state
- Store pattern using Pinia with `defineStore()` → composition function pattern, not options API
- Example from `champion.ts` lines 15-22: State refs, computed properties, and action functions returned in single object

## Import Organization

**Order (Python):**
1. Standard library imports: `import json`, `import requests`, `import os`
2. Third-party imports: `from flask import Flask`, `from lxml import html`, `from typing import ...`
3. Local imports: `from lolalytics_api import ...`, `from recommendation_config import ...`

Example from `backend.py` lines 6-31: stdlib imports first, then flask/socketio, then local modules

**Order (TypeScript):**
1. Vue core: `import { ref, onMounted } from 'vue'`
2. Vue ecosystem: `import { defineStore } from 'pinia'`, `import { io } from 'socket.io-client'`
3. Type imports: `import type { DraftPick } from '@counterpick/core'`
4. Local imports: `import { getChampionsList } from '@/api/backend'`, `import DraftTeam from '@/components/draft/DraftTeam.vue'`

**Path Aliases:**
- `@/*` → `./src/*` (TypeScript files can use `@/api`, `@/components`, `@/stores`)
- `@counterpick/core` → `../../packages/core/src` (shared type definitions)

## Error Handling

**Python Patterns:**
- Custom exception classes in `errors.py`: `InvalidLane(Exception)` and `InvalidRank(Exception)` take parameters and format messages
- Try/except with specific error types: `except KeyError:` raises custom `InvalidRank(rank)` (lines 125-128, `main.py`)
- Try/except in Flask endpoints for catching `requests.exceptions.ConnectionError` and generic `Exception`
- Cache invalidation on auth errors: `_client_info_cache = None` when 401 received (lines 59-61, `league_client_api.py`)
- Safe conversion functions: `safe_int()` function returns `None` on error rather than raising (line 29, `recommendation_engine.py`)

**TypeScript Patterns:**
- Async/await with try/catch blocks in API calls
- Retry logic with exponential backoff: `fetchApi()` function accepts `retries` and `retryDelay` parameters (lines 23-66, `backend.ts`)
- Error coercion: `error instanceof Error ? error : new Error(String(error))` (line 54)
- Console warnings for recoverable errors: `console.warn()` used for failed API calls, not logged to backend

## Logging

**Python:**
- `print()` statements for debug output: `print("[LEAGUE CLIENT] Authentifizierungsfehler (401) - Cache invalidiert")`
- Conditional logging with `if __debug__:` guard (line 76, `league_client_api.py`)
- Prefixed messages with brackets: `[LEAGUE CLIENT]`, `[API]`
- No structured logging framework (print-based only)

**TypeScript:**
- `console.warn()` for non-critical issues: `console.warn('[API] Server-Fehler...')`
- `console.error()` for exceptions in stores
- Prefixed messages: `[API]` for backend calls

## Comments

**When to Comment:**
- Complex algorithms: Wilson Score calculation has multi-line comment explaining statistical concept (lines 55-65, `recommendation_engine.py`)
- Business logic intent: German comments explain role mappings and synergy decisions
- Parsing logic: XPath explanations and section references (lines 200-212, `main.py`)

**Language:**
- German preferred for business logic and UI concerns: `Normalisiert Champion-Namen`, `Löst das "Low Sample Size"-Problem`
- English for technical/code explanations: `:param:`, `:return:` in docstrings
- Mixed in same files is standard practice

**JSDoc/TSDoc:**
- Multiline JSDoc blocks with `/**` for public functions (lines 1-4, `backend.ts`: Backend API Client)
- Parameter types documented: `:Promise<T>`, return types via TypeScript signature
- Simple single-line comments for inline explanations

## Function Design

**Size Guidelines:**
- Python functions: 10-80 lines typical (web scraping functions with xPath loops are longer)
- TypeScript helpers: 5-40 lines (short async utilities preferred)
- Store actions: 20-50 lines (API calls + state updates)

**Parameters:**
- Python: positional args with defaults: `display_ranks(display: bool = True)` (line 7, `main.py`)
- TypeScript: destructuring for objects in stores, positional for simple API calls
- Type hints used throughout Python: `def wilson_score(wins: int, n: int, z: float = 1.44) -> float:`

**Return Values:**
- Python: return JSON strings: `return json.dumps(result, indent=4)` (lines 217, 263, `main.py`)
- TypeScript: return typed promises: `Promise<{ status: string }>` with full response object shape
- Stores return plain state objects, not wrapped in additional layers

## Module Design

**Python Modules:**
- Single responsibility: `recommendation_engine.py` handles scoring, `league_client_api.py` handles LCU calls
- Helper functions prefixed with `_`: `_sort_by_rank()`, `_sort_by_lane()` are private to `main.py`
- No barrel files (Python uses direct imports)

**TypeScript Modules:**
- Barrel exports in stores: `src/stores/index.ts` exists (likely re-exports all stores)
- No barrel files in `src/components/` or `src/api/` (direct imports used)
- API functions grouped by feature: `getChampionsList()`, `getPrimaryRoles()`, `getChampionMatchups()` all in `src/api/backend.ts`

**Store Organization (Pinia):**
- `defineStore(name, () => { ... })` composition pattern: defines state with `ref()`, computed properties, and action functions
- Single object returned with all exports: state refs, computed getters, and action functions mixed
- Example from `champion.ts` lines 224-246: returns object with `championsList`, `championsLoaded`, `loadChampionData()`, etc.

---

*Convention analysis: 2026-04-14*
