# Lolalytics Counter-Pick Tool - Projekt-Dokumentation

## Projekt-Übersicht

Dieses Projekt bietet ein Tool zur Analyse von League of Legends Champion-Counter-Picks basierend auf Daten von Lolalytics.com. Es besteht aus einem Flask-Backend und einem HTML/JavaScript-Frontend.

**Hauptfunktionen:**
- Counter-Picks für Champions finden
- Score-basierte Sortierung (kombiniert Winrate-Differenz und Pickrate)
- Sortierbare Tabellen im Frontend
- Persistenter Cache für bessere Performance
- Auto-Complete für Champion-Namen

---

## Installation & Setup

### Voraussetzungen

- **Anaconda** installiert (Pfad: `D:\Programme\anaconda3`)
- **Python 3.11** (wird automatisch mit Anaconda-Umgebung installiert)

### Schritt 1: Anaconda-Umgebung erstellen

```bash
# Öffne Anaconda Prompt
conda create -n lolalytics-env python=3.11
conda activate lolalytics-env
```

### Schritt 2: Projekt-Verzeichnis

```bash
cd "D:\Python\Riot Api\lolalytics-api-master"
```

### Schritt 3: lolalytics-api installieren

```bash
# Als editierbares Paket installieren (wichtig für Anpassungen!)
pip install -e .
```

### Schritt 4: Backend-Abhängigkeiten installieren

```bash
pip install Flask flask-cors urllib3
```

**Oder alle Dependencies auf einmal:**
```bash
pip install -r requirements.txt
```

**Hinweis:** `urllib3` wird für die Live Client API Integration benötigt (SSL-Warnungs-Unterdrückung).

---

## Backend-Setup

### Backend starten

**Option A: Mit Batch-Datei (Windows)**
```
Doppelklick auf: START_BACKEND.bat
```

**Option B: Manuell**
```bash
# Umgebung aktivieren
conda activate lolalytics-env

# Ins Verzeichnis wechseln
cd "D:\Python\Riot Api\lolalytics-api-master"

# Backend starten
python backend.py
```

Das Backend läuft dann auf: **http://localhost:5000**

### Backend-Konfiguration

**Cache-Dauer ändern** (`backend.py`, Zeile 22):
```python
CACHE_DURATION = 86400  # 24 Stunden in Sekunden
```

**Port ändern** (`backend.py`, letzte Zeile):
```python
app.run(debug=True, host='0.0.0.0', port=5000)
```

---

## Frontend-Integration

### HTML öffnen

Öffne im Browser:
```
D:\Python\Riot Api\Counterpick\index_backend.html
```

### Backend-URL ändern

In `index_backend.html`, Zeile 330:
```javascript
const BACKEND_URL = 'http://localhost:5000';
```

---

## API-Endpunkte

### Health Check
```
GET http://localhost:5000/api/health
```

### Counter für Champion (mit Score-Berechnung)
```
GET http://localhost:5000/api/counter-by-role/<champion>?rank=emerald&n=10&patch=15.23

Beispiel:
http://localhost:5000/api/counter-by-role/caitlyn?rank=emerald&n=10
http://localhost:5000/api/counter-by-role/caitlyn?rank=emerald&n=10&patch=15.22
```

**Response:**
```json
{
  "success": true,
  "champion": "caitlyn",
  "rank": "emerald",
  "patch": "15.23",
  "counters": {
    "0": {
      "champion": "Vel'Koz",
      "winrate": "44.24",
      "pickrate": "3.25%",
      "score": 4.32
    },
    ...
  },
  "note": "Top 10 Counter sortiert nach Score..."
}
```

**Query-Parameter:**
- `rank`: Rang (default: emerald)
- `n`: Anzahl der Counter (default: 10)
- `patch`: Patch-Version (z.B. '15.23', '15.22', optional - default: aktueller Patch)

### Synergien für Champion (mit Score-Berechnung)
```
GET http://localhost:5000/api/synergy/<champion>?rank=emerald&n=10&patch=15.23

Beispiel:
http://localhost:5000/api/synergy/caitlyn?rank=emerald&n=10
http://localhost:5000/api/synergy/leona?rank=emerald&n=10&patch=15.22
```

**Response:**
```json
{
  "success": true,
  "champion": "caitlyn",
  "rank": "emerald",
  "patch": "15.23",
  "synergies": {
    "0": {
      "champion": "Lulu",
      "winrate": "54.32",
      "pickrate": "8.15%",
      "score": 2.87
    },
    ...
  },
  "note": "Top 10 Synergien sortiert nach Score..."
}
```

**Query-Parameter:**
- `rank`: Rang (default: emerald)
- `n`: Anzahl der Synergien (default: 10)
- `patch`: Patch-Version (z.B. '15.23', '15.22', optional - default: aktueller Patch)

**Hinweis:** Die Synergy-Daten zeigen die besten Teammates für einen Champion. Die Score-Berechnung ist identisch mit der Counter-Analyse, aber ein positiver Score bedeutet eine gute Synergie (höhere Winrate mit dem Teammate).

### Champion-Statistiken
```
GET http://localhost:5000/api/champion/<champion>?lane=&rank=emerald&patch=15.23

Beispiel:
http://localhost:5000/api/champion/caitlyn?lane=&rank=emerald
http://localhost:5000/api/champion/caitlyn?lane=&rank=emerald&patch=15.22
```

**Query-Parameter:**
- `lane`: Lane (optional)
- `rank`: Rang (default: emerald)
- `patch`: Patch-Version (z.B. '15.23', '15.22', optional - default: aktueller Patch)

### Champions-Liste (für Auto-Complete)
```
GET http://localhost:5000/api/champions/list
```

### Cache-Verwaltung
```
GET  http://localhost:5000/api/cache/stats   # Cache-Statistiken
POST http://localhost:5000/api/cache/clear   # Cache leeren
```

### Live Client API (Draft Tracker)
```
GET http://localhost:5000/api/live-client/status   # Prüft ob Live Client erreichbar ist
GET http://localhost:5000/api/live-client/draft     # Holt aktuelle Draft-Daten (Picks, Bans)
GET http://localhost:5000/api/live-client/players  # Holt alle Spieler-Daten (für Debugging)
```

**Hinweis:** Die Live Client API funktioniert nur, wenn der League of Legends Client läuft und du dich in einer Draft-Phase oder im Spiel befindest.

---

## Score-Formel

### Die wissenschaftliche Formel

```
Finaler Score = -1 × ((Matchup_WR - Overall_WR) × (Pickrate / Durchschnitts_Pickrate)^k)
```

**Komponenten:**
- `Matchup_WR` = Winrate des Counter-Champions gegen den eingegebenen Gegner (z.B. Vel'Koz vs Caitlyn = 44.24%)
- `Overall_WR` = Durchschnittliche Winrate des Counter-Champions im Meta (z.B. Vel'Koz gesamt = 52.41%)
- `Pickrate` = Wie oft wird der Counter gespielt (z.B. 3.25%)
- `Durchschnitts_Pickrate` = Durchschnittliche Pickrate aller betrachteten Champions
- `k = 0.8` = Exponent zur Steuerung der Pickrate-Gewichtung
- `-1` = Invertierung, damit **höherer Score = besserer Counter**

### Beispiel-Berechnung

**Vel'Koz gegen Caitlyn:**
- Matchup WR: 44.24% (Vel'Koz WR gegen Caitlyn)
- Overall WR: 52.41% (Vel'Koz normalerweise)
- WR-Differenz: 44.24 - 52.41 = **-8.17%** (Vel'Koz spielt schlechter gegen Caitlyn)
- Pickrate: 3.25%
- Durchschnitts-PR: 3.18%
- PR-Ratio: 3.25 / 3.18 = 1.02
- PR-Weight: 1.02^0.8 = 1.02
- Score = -1 × (-8.17 × 1.02) = **+8.30** ✓ (Guter Counter!)

**Interpretation:**
- **Positiver Score** = Guter Pick gegen den Gegner (je höher, desto besser)
- **Negativer Score** = Schlechter Pick (eigentlich kein Counter)
- **Niedrige Matchup WR** = Gegner spielt schlecht gegen diesen Champion = Guter Pick für uns!

### Parameter-Tuning

Die Pickrate-Gewichtung kann in `backend.py`, Zeile 437 angepasst werden:
```python
k_exponent = 0.8  # Höher = Pickrate wichtiger (z.B. 1.0)
                  # Niedriger = WR-Differenz wichtiger (z.B. 0.5)
```

---

## Frontend-Features

### Live Draft Tracker

Der Draft Tracker zeigt Picks und Bans in Echtzeit während der Draft-Phase:

- **Aktivierung:** Klicke auf "📊 Draft Tracker anzeigen" Button
- **Live-Updates:** Automatisches Polling alle 2 Sekunden
- **Team-Anzeige:** Zwei-Spalten-Layout für Blue Side (Team 1) und Red Side (Team 2)
- **Champion-Icons:** Automatische Anzeige der Champion-Icons
- **Status-Indikator:** Grün = Client verbunden, Rot = Client nicht erreichbar
- **Bans-Section:** Zeigt gebannte Champions (wenn verfügbar)

**Voraussetzungen:**
- League of Legends Client muss laufen
- **WICHTIG:** Die Live Client API ist nur verfügbar, wenn das Spiel **WIRKLICH GESTARTET** wurde!
- Die API ist **NICHT** in der Draft-Phase/Lobby verfügbar - nur während des laufenden Spiels
- **WICHTIG:** Die Live Client API funktioniert **NICHT** im Practice Tool/Trainingsmodus!
- Backend muss laufen (`python backend.py`)

**Wann ist die API verfügbar:**
- ✅ **Während des laufenden Spiels** (nachdem das Spiel gestartet wurde)
- ❌ **NICHT in der Draft-Phase** (API wird erst aktiv wenn das Spiel beginnt)
- ❌ **NICHT in der Lobby** (API ist noch nicht aktiv)
- ❌ **NICHT im Practice Tool** (nicht unterstützt)

**Unterstützte Modi (wenn Spiel läuft):**
- ✅ Ranked Games
- ✅ Normal Games
- ✅ Custom Games
- ✅ ARAM
- ❌ Practice Tool/Trainingsmodus (nicht unterstützt)

**Hinweis:** Für Draft-Tracking während der Draft-Phase müsste eine andere Methode verwendet werden (z.B. League Client API statt Live Client API).

### Sortierbare Tabelle

Die Counter-Tabelle kann nach verschiedenen Spalten sortiert werden:
- **Champion** (alphabetisch)
- **Matchup WR** (niedriger = besserer Pick)
- **Pickrate** (häufigere Champions)
- **Score** (höher = besserer Counter)

**Verwendung:** Klicken Sie auf die Spaltenköpfe zum Sortieren.

### Auto-Complete

Champion-Namen werden automatisch vorgeschlagen beim Tippen.

### Anzeige

- **Matchup WR:** Zeigt die Winrate des Counter-Champions gegen den eingegebenen Gegner
- **Pickrate:** Wie oft der Champion gespielt wird
- **Score:** Berechneter Score (grün = gut, rot = schlecht)

### Modus-Auswahl: Counter vs. Synergien

Das Frontend bietet jetzt zwei Modi:

1. **Counter-Modus (Standard):**
   - Zeigt die besten Picks **gegen** den eingegebenen Champion
   - Niedrige Matchup-WR = Guter Counter
   - Positiver Score = Starker Counter

2. **Synergy-Modus:**
   - Zeigt die besten **Teammates** für den eingegebenen Champion
   - Hohe Synergy-WR = Gute Synergie
   - Positiver Score = Starke Synergie
   - **Ideal für ADC/Support-Spieler:** 
     - ADC eingeben → Beste Support-Synergien anzeigen
     - Support eingeben → Beste ADC-Synergien anzeigen

**Verwendung:**
- Wählen Sie den gewünschten Modus mit den Radio-Buttons vor der Analyse
- Die Tabellen-Überschrift und Legende passen sich automatisch an
- Beide Modi nutzen die gleiche Score-Berechnung für optimale Vergleichbarkeit

---

## Caching-System

Das Backend nutzt ein **persistentes JSON-basiertes Cache-System**:

- **Cache-Datei:** `cache_data.json` (im Backend-Verzeichnis)
- **Cache-Dauer:** 24 Stunden (86400 Sekunden)
- **Vorteil:** Wiederholte Anfragen sind sofort verfügbar
- **Persistent:** Cache bleibt auch nach Backend-Neustart erhalten

### Cache-Status prüfen

```bash
curl http://localhost:5000/api/cache/stats
```

### Cache leeren

```bash
curl -X POST http://localhost:5000/api/cache/clear
```

Oder einfach die Datei `cache_data.json` löschen.

---

## Wichtige Technische Details

### Champion-Namen-Normalisierung

Champions mit Sonderzeichen werden automatisch normalisiert:
- `Miss Fortune` → `missfortune`
- `Kog'Maw` → `kogmaw`
- `Kai'Sa` → `kaisa`
- `Aurelion Sol` → `aurelionsol`

**Funktion:** `normalize_champion_name()` in `backend.py`, Zeile 25-40

### Counter-Anzahl

- **Geholt:** Maximal 20 Counter pro Anfrage (Performance-Optimierung)
- **Angezeigt:** Top 10 Counter (konfigurierbar im Frontend)

### Fehlerbehandlung

- IndexError bei fehlenden Counter-Daten wird abgefangen
- Champions mit fehlenden Pickrate-Daten erhalten Score 0
- Fehlerhafte Einträge werden geloggt, aber nicht abgebrochen

---

## Troubleshooting

### Problem: "Backend Offline" im HTML

**Lösung:**
1. Prüfe ob `backend.py` läuft
2. Öffne http://localhost:5000/api/health im Browser
3. Wenn Fehler → Backend neu starten

### Problem: "Champion nicht gefunden"

**Ursachen:**
- Tippfehler im Champion-Namen
- Lolalytics hat die Website geändert (XPath-Selektoren veraltet)

**Lösung:**
```bash
# Test ob Scraper noch funktioniert
python test_scraper.py
```

### Problem: Langsame Response-Zeiten

**Erste Anfrage:** ~10-30 Sekunden (holt Pickrate-Daten für jeden Counter)
**Nachfolgende Anfragen:** < 1 Sekunde (aus Cache)

**Lösung:**
- Cache wird automatisch genutzt
- Prüfe Cache-Status: http://localhost:5000/api/cache/stats

### Problem: CORS-Fehler

**Symptom:** Browser-Console zeigt CORS-Fehler

**Lösung:**
- `flask-cors` ist installiert und aktiviert
- Falls Problem bleibt: HTML über einen Webserver statt `file://` öffnen

### Problem: IndexError beim Scrapen

**Ursache:** Lolalytics hat die Website-Struktur geändert

**Lösung:**
- Die `get_counters()` Funktion hat jetzt Fehlerbehandlung
- Wenn zu wenige Counter verfügbar sind, wird die Schleife sauber beendet

---

## Projekt-Struktur

```
lolalytics-api-master/
├── backend.py                 # Flask-Backend
├── test_scraper.py            # Validierungs-Script
├── START_BACKEND.bat          # Quick-Start Script
├── cache_data.json            # Persistenter Cache (wird automatisch erstellt)
├── src/
│   └── lolalytics_api/        # lolalytics-api Library
│       ├── main.py            # Scraping-Logik
│       └── errors.py         # Custom Exceptions
└── PROJEKT_DOKUMENTATION.md   # Diese Datei

Counterpick/
└── index_backend.html         # Frontend HTML
```

---

## Validierung & Tests

### test_scraper.py

Führt grundlegende Tests durch:
```bash
python test_scraper.py
```

**Erwartetes Ergebnis:**
- ✓ get_counters() funktioniert
- ✓ get_champion_data() funktioniert
- ✓ Keine Cloudflare-Blockierung

### Manueller Test

1. Backend starten (siehe oben)
2. HTML öffnen (`index_backend.html`)
3. Champion eingeben (z.B. "Caitlyn")
4. Rank wählen (z.B. "emerald")
5. "Analyse starten" klicken
6. Counter-Tabelle sollte angezeigt werden

---

## Patch-Version Auswahl

Alle API-Endpunkte unterstützen jetzt einen optionalen `patch`-Parameter:

### Verwendung

**Aktueller Patch (default):**
```
http://localhost:5000/api/counters/caitlyn?rank=emerald&n=10
```

**Spezifischer Patch:**
```
http://localhost:5000/api/counters/caitlyn?rank=emerald&n=10&patch=15.22
http://localhost:5000/api/champion/ahri?rank=emerald&patch=15.23
http://localhost:5000/api/tierlist?lane=mid&rank=emerald&patch=15.21
```

### Unterstützte Endpunkte

Alle folgenden Endpunkte unterstützen den `patch`-Parameter:
- `/api/counters/<champion>`
- `/api/counter-by-role/<champion>`
- `/api/synergy/<champion>`
- `/api/champion/<champion>`
- `/api/tierlist`
- `/api/matchup/<champ1>/<champ2>`

**Hinweis:** Wenn kein Patch angegeben wird, verwendet Lolalytics automatisch die Daten des aktuellen Patches.

---

## Synergy-Feature für ADC/Support

**NEU:** Das Tool unterstützt jetzt Synergy-Analysen, um die besten Teammate-Kombinationen zu finden!

### Anwendungsfall

Besonders nützlich für ADC- und Support-Spieler:
- **Blind Pick:** Wenn Sie zuerst picken und wissen möchten, welcher Teammate am besten passt
- **Nach Teammate-Pick:** Wenn Ihr Support/ADC bereits gewählt hat, finden Sie den besten Champion dazu
- **Team-Koordination:** Optimieren Sie Bot-Lane-Kombinationen basierend auf echten Statistiken

### Funktionsweise

1. **Wählen Sie "Synergien" Modus** in der Oberfläche
2. **Geben Sie einen Champion ein** (z.B. Caitlyn, Leona)
3. **Erhalten Sie die Top-Synergien** mit Score-Berechnung:
   - **Synergy WR:** Wie hoch ist die Winrate mit diesem Teammate?
   - **Overall WR:** Wie gut performt der Champion normalerweise?
   - **Score:** Kombiniert WR-Differenz + Pickrate-Gewichtung

### Score-Interpretation für Synergien

```
Score = (Synergy_WR - Overall_WR) × (Pickrate / Avg_Pickrate)^0.8
```

**Positiver Score = Gute Synergie!**

**Beispiel:** Lulu + Caitlyn
- Synergy WR: 54.3% (Winrate zusammen)
- Overall WR: 51.8% (Lulu normalerweise)
- WR-Differenz: +2.5% (Lulu spielt besser mit Caitlyn!)
- Pickrate: 8.15%
- **Score: +2.87** ✓ (Starke Synergie!)

### Warum Pickrate-Gewichtung?

Champions mit hoher Pickrate (viele Spiele) werden von mehr Spielern gespielt, einschließlich unerfahrener Spieler. Die Gewichtung verhindert, dass beliebte aber schwierige Kombinationen (z.B. Lucian + Nami) unterbewertet werden.

### Backend-Endpunkt

```bash
# Synergien für Caitlyn (Support-Teammates)
curl "http://localhost:5000/api/synergy/caitlyn?rank=emerald&n=10"

# Synergien für Leona (ADC-Teammates)
curl "http://localhost:5000/api/synergy/leona?rank=emerald&n=10&patch=15.23"
```

---

## Nächste Schritte (Optional)

### Produktions-Deployment

Für einen echten Server:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 backend:app
```

### Vue.js Integration

Das HTML kann problemlos in eine Vue.js-App umgewandelt werden:
- Komponenten für Champion-Cards
- Vuex für State-Management
- Axios für API-Calls

---

## Support

Bei Problemen:
1. Prüfe `test_scraper.py`
2. Prüfe Backend-Logs im Terminal
3. Prüfe Browser-Console (F12)
4. Prüfe `/api/health` Endpunkt

---

## Changelog

### Version 1.2 (Dezember 2025)
- ✨ **NEU:** Live Draft Tracker
  - Neue Backend-Module: `live_client_api.py` für Live Client API Integration
  - Neue API-Endpunkte: `/api/live-client/status`, `/api/live-client/draft`, `/api/live-client/players`
  - Frontend: Live Draft-Tracker mit Echtzeit-Updates (Polling alle 2 Sekunden)
  - Zeigt Picks und Bans für beide Teams während der Draft-Phase
  - Status-Indikator für Client-Verbindung
  - Toggle-Button zum Ein-/Ausblenden des Trackers
  - Benötigt: `urllib3` Dependency (für SSL-Warnungs-Unterdrückung)

### Version 1.1.4 (25.11.2025)
- 🐛 **BUGFIX:** 500 Error bei `/api/champion/` behoben
  - Lolalytics blockiert Requests ohne User-Agent (403 Forbidden)
  - `User-Agent` Header zu `get_champion_data()` und `matchup()` hinzugefügt
  - Behebt "list index out of range" Fehler bei allen Champion-Abfragen
  - `/api/champion/Milio`, `/api/champion/Miss Fortune`, etc. funktionieren wieder

### Version 1.1.3 (20.11.2025)
- 🐛 **BUGFIX:** Counter-Abfragen für Champions mit Sonderzeichen
  - Backend: `normalize_champion_name()` jetzt in **allen** API-Endpoints
  - Behebt Counter-Fehler für "Miss Fortune", "Kai'Sa", "Kog'Maw", etc.
  - Betrifft: `/api/counters/`, `/api/counter-by-role/`, `/api/matchup/`
  - Miss Fortune Counter funktionieren jetzt korrekt mit Lolalytics

### Version 1.1.2 (20.11.2025)
- 🐛 **BUGFIX:** Champion-Bilder für Namen mit Sonderzeichen
  - Frontend: `normalizeChampionName()` Funktion für einheitliche Namensvergleiche
  - Behebt Bild-Ladefehler für "Miss Fortune" (`missfortune`), "Kai'Sa" (`kaisa`), etc.
  - Entfernt Apostrophe, Leerzeichen und Punkte für Data Dragon Kompatibilität

### Version 1.1.1 (20.11.2025)
- 🐛 **BUGFIX:** Synergy-Rollen-Erkennung korrigiert
  - OP.GG verwendet `adc` statt `bottom` in URLs → XPath korrigiert
  - Externe Konfiguration: `src/lolalytics_api/champion_roles.json`
  - Support → zeigt jetzt korrekt ADCs (statt Toplaners)
  - ADC → zeigt korrekt Supports
  - Wartbar: Neue Champions können einfach zur JSON hinzugefügt werden

### Version 1.1 (20.11.2025)
- ✨ **NEU:** Synergy-Feature für ADC/Support-Kombinationen
  - Neue API-Funktion: `get_opgg_synergies()` in `opgg_synergy.py`
  - Neuer Backend-Endpunkt: `/api/synergy/<champion>`
  - Frontend-Modus-Auswahl: Counter vs. Synergien
  - Gleiche Score-Berechnung wie bei Countern für Vergleichbarkeit
- 📊 Dynamische Tabellen-Überschriften und Legenden
- 🎯 Optimiert für Bot-Lane Team-Koordination

### Version 1.0 (November 2025)
- Counter-Pick Analyse mit Score-Berechnung
- Flask-Backend mit persistentem Caching
- Patch-Version Auswahl
- Sortierbare Tabellen
- Auto-Complete für Champion-Namen

---

**Stand:** Dezember 2025  
**Version:** 1.2  
**Python:** 3.11  
**Flask:** 3.1.2

