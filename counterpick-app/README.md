# Counterpick Draft Tracker

LoL Draft Analyzer - Desktop-Anwendung für League of Legends Draft-Analyse.

## Features

- **Draft Tracker**: Echtzeit-Draft-Tracking während der Champion Select
- **Recommendation Engine**: Intelligente Pick-Empfehlungen basierend auf Team-Komposition
- **Pick-Score-Anzeige**: Scores für alle gepickten Champions mit Counter- und Synergy-Bewertung
- **League Client Integration**: Automatische Synchronisation mit dem LoL-Client

## Projektstruktur

```
counterpick-app/
├── apps/
│   ├── frontend/       # Vue 3 + TypeScript Frontend
│   └── backend/        # Python Flask Backend
├── packages/
│   └── core/           # Shared TypeScript-Logik
├── package.json        # Root package.json (pnpm workspace)
├── pnpm-workspace.yaml # Workspace-Definition
└── turbo.json          # Build-Pipeline
```

## Voraussetzungen

- Node.js >= 18.0.0
- pnpm >= 9.2.0
- Python >= 3.10

## Installation

```bash
# Dependencies installieren
pnpm install

# Backend-Dependencies installieren
cd apps/backend
pip install -r requirements.txt
```

## Entwicklung

```bash
# Frontend starten
pnpm dev

# Backend starten (in separatem Terminal)
pnpm backend
```

## Build

```bash
# Production Build
pnpm build
```

## Technologie-Stack

### Frontend
- Vue 3 (Composition API)
- TypeScript
- Vite
- Pinia (State Management)

### Backend
- Python Flask
- Flask-SocketIO
- Supabase (Datenbank)

### Später: Desktop-App
- Tauri (Rust-basiert)

## Lizenz

Private Nutzung

