# Supabase Dataset Updater

Automatisches Update-Script für LoL Champion-Daten in Supabase. Aktualisiert täglich Champion-Statistiken, Matchups, Synergien und weitere Daten aus der Riot API und Lolalytics.

## Features

- Automatische Aktualisierung von Champion-Daten
- Matchup-Statistiken für alle Rollen
- Synergie-Daten zwischen Champions
- Items, Runen und Beschwörerzauber
- Tägliche Ausführung via GitHub Actions

## Setup

### Lokale Ausführung

1. **Dependencies installieren:**
   ```bash
   pnpm install
   ```

2. **Umgebungsvariablen konfigurieren:**
   ```bash
   cp .env.example .env
   ```
   
   Bearbeite `.env` und füge deine Supabase-Credentials ein:
   - `SUPABASE_URL`: Deine Supabase Projekt-URL
   - `SUPABASE_SERVICE_ROLE_KEY`: Dein Supabase Service Role Key

3. **Script ausführen:**
   ```bash
   pnpm run update
   ```

### GitHub Actions Setup

1. **Repository Secrets konfigurieren:**
   
   Gehe zu deinem GitHub Repository → Settings → Secrets and variables → Actions
   
   Füge folgende Secrets hinzu:
   - `SUPABASE_URL`: Deine Supabase Projekt-URL
   - `SUPABASE_SERVICE_ROLE_KEY`: Dein Supabase Service Role Key

2. **Workflow aktivieren:**
   
   Der Workflow läuft automatisch täglich um 12:00 UTC. Du kannst ihn auch manuell auslösen:
   - Gehe zu Actions → "Update Supabase Dataset" → "Run workflow"

## Datenbank-Schema

Das Script erwartet folgende Tabellen in Supabase:

- `champions` - Champion-Grunddaten
- `items` - Item-Daten
- `runes` - Rune-Daten
- `summoner_spells` - Beschwörerzauber
- `champion_stats` - Champion-Statistiken pro Rolle
- `matchups` - Matchup-Daten zwischen Champions
- `synergies` - Synergie-Daten zwischen Champions
- `patches` - Patch-Versionen

## Test-Modus

Um nur bestimmte Champions zu testen, setze die Umgebungsvariable:

```bash
TEST_CHAMPIONS=Aatrox,Ahri,Akali pnpm update
```

## Projektstruktur

```
supabase-dataset-updater/
├── src/
│   ├── supabase-etl.ts          # Haupt-ETL-Script
│   ├── riot.ts                   # Riot API Client
│   ├── utils.ts                  # Utility-Funktionen
│   ├── models/                   # Type-Definitionen
│   └── lolalytics/               # Lolalytics API Integration
├── .github/workflows/            # GitHub Actions Workflows
└── package.json
```

## Dependencies

- `@supabase/supabase-js` - Supabase Client
- `dotenv` - Umgebungsvariablen
- `tsx` - TypeScript Execution
- `typescript` - TypeScript Compiler

## Lizenz

Dieses Projekt wurde aus dem draftgap-main Projekt extrahiert.

