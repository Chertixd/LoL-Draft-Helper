# Counterpick Draft Tracker Backend

Python Flask Backend für den Draft Tracker mit Recommendation Engine.

## Features

- **Recommendation Engine**: Intelligente Champion-Empfehlungen basierend auf Wilson Score
- **League Client Integration**: Echtzeit-Draft-Tracking via WebSocket
- **Champion Stats**: Winrates, Pickrates, Primary Roles

## Installation

```bash
# Python Virtual Environment erstellen (empfohlen)
python -m venv venv

# Aktivieren
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# lolalytics_api Package installieren (editable mode)
pip install -e .
```

## Konfiguration

1. Kopiere `.env.example` nach `.env`:
   ```bash
   cp .env.example .env
   ```

2. Füge deine Supabase-Credentials ein:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-anon-key
   ```

## Starten

```bash
python backend.py
```

Server läuft auf http://localhost:5000

## API Endpoints

### Health Check
- `GET /api/health` - Backend-Status prüfen

### Champions
- `GET /api/champions/list` - Liste aller Champions
- `GET /api/champion/{name}` - Champion-Stats
- `GET /api/champion/{name}/stats-by-role` - Stats nach Rolle
- `GET /api/primary-roles` - Primary Roles Mapping

### Recommendations (Herzstück)
- `POST /api/recommendations` - Champion-Empfehlungen
  ```json
  {
    "myRole": "bottom",
    "myTeam": [{"championKey": "Jinx", "role": "bottom"}],
    "enemyTeam": [{"championKey": "Caitlyn", "role": "bottom"}],
    "patch": "15.24",
    "isBlindPick": false
  }
  ```

### League Client
- `GET /api/league-client/status` - Client-Verbindungsstatus
- `GET /api/league-client/draft` - Aktuelle Draft-Daten
- `POST /api/set-role` - Manuelle Rollen-Überschreibung

### WebSocket Events
- `draft_update` - Echtzeit-Draft-Updates

## Dokumentation

- `SCORE_CALCULATION.md` - Detaillierte Dokumentation der Score-Berechnung (aktuell)
- `TROUBLESHOOTING.md` - Problemlösungen

## Projektstruktur

```
apps/backend/
├── backend.py                 # Flask Server (Haupt-Entry)
├── recommendation_engine.py   # ⭐ Recommendation Logic
├── recommendation_config.py   # Score Weights & Matrices
├── league_client_*.py         # League Client Integration
├── requirements.txt           # Python Dependencies
├── .env                       # Umgebungsvariablen (nicht committen!)
└── src/
    └── lolalytics_api/        # Core API Package
        ├── supabase_client.py # Supabase Connection
        ├── supabase_repo.py   # Data Repository
        ├── main.py            # Legacy API
        └── config.py          # Konfiguration
```

## Lizenz

Private Nutzung
