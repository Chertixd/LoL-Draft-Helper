# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - YYYY-MM-DD

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
