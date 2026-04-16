# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.4] - 2026-04-16

### Fixed
- **Critical:** `/api/recommendations` was completely broken in installed production builds. The recommendation engine still imported `supabase_client` and made 11 direct Supabase queries per request, but `supabase-py` was excluded from the PyInstaller bundle in Phase 2. Every draft recommendation would have raised `ImportError: No module named 'supabase'` in the installed app. This was invisible in v1.0.0-1.0.3 because earlier bugs prevented the app from ever reaching a champion-select flow. Refactored `recommendation_engine.py` to read from the in-memory `json_repo` cache (the same source everything else already uses since Plan 02-04)

### Performance
- Recommendation latency reduced 4-5x: ~4 s → ~800 ms. Root cause was the 11 supabase.co network round-trips per request; all now served from the preloaded in-memory CDN cache. Further optimisation (hash-map indexes over matchup rows, target ~100 ms) is tracked for v1.1

## [1.0.3] - 2026-04-16

### Fixed
- League Client was not detected in the Lobby phase: `is_league_client_running()` checked for a game-session (HTTP 200 on `/lol-gameflow/v1/session`) but returned 404 in the lobby. Switched to `/lol-gameflow/v1/gameflow-phase` which returns 200 whenever the client is reachable, regardless of game state

### Performance
- First-pick recommendation now served from memory (~30 ms) instead of a cold CDN fetch (~1.8 s for matchups + ~0.7 s for synergies). The backend now preloads the latest patch's matchups and synergies shards in a background thread immediately after ready-signal, while the user is still navigating to champion select. Non-blocking: if the user picks before preload finishes, the normal lazy fetch kicks in

## [1.0.1] - 2026-04-16

### Fixed
- "Backend stopped unexpectedly" banner incorrectly shown on first app start due to a race between the webview mount and the Python sidecar's warm-cache phase
- Patch dropdown stuck on the hardcoded fallback (e.g. "16.1") instead of showing the live latest patch; same root cause as above
- Frontend API calls now retry up to ~15s with exponential backoff while the sidecar warms its CDN cache, and re-resolve the backend URL via Tauri IPC on each retry to handle IPC-not-ready edge cases

## [1.0.0] - 2026-04-16

### Added
- Desktop installer (MSI + portable setup) for Windows 10/11
- Auto-update via Tauri updater with signed releases
- CDN data pipeline replacing direct Supabase access
- Centralized logging to %APPDATA%\dev.till.lol-draft-analyzer\logs\
- Per-user installation (no admin rights required)
- Automatic League Client detection and reconnection
- Mid-draft update deferral (updates wait until champion select ends)

### Fixed
- Hover detection now correctly applies reduced weight to hovered picks in recommendations

### Changed
- Data source switched from Supabase to GitHub Pages CDN (faster, no credentials needed)
- Backend runs as a managed sidecar process (automatic start/stop with the app)
