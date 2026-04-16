# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
