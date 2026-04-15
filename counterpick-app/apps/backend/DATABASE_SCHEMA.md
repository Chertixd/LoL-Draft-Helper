# Supabase Datenbank-Schema Dokumentation

Diese Dokumentation beschreibt die Struktur aller Tabellen in der Supabase-Datenbank für das Counterpick-App Projekt.

## Übersicht

Die Datenbank enthält folgende Tabellen:

1. `champions` - Champion-Grunddaten
2. `champion_stats` - Champion-Statistiken pro Rolle und Patch
3. `matchups` - Matchup-Daten zwischen Champions
4. `synergies` - Synergie-Daten zwischen Champions
5. `items` - Item-Daten
6. `runes` - Rune-Daten
7. `summoner_spells` - Beschwörerzauber
8. `patches` - Patch-Versionen

---

## Tabellen-Details

### 1. `champions`

Champion-Grunddaten (Master-Daten).

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `key` | `text` | Champion-Schlüssel (z.B. "266" für Aatrox) |
| `name` | `text` | Champion-Name (z.B. "Aatrox") |
| `i18n` | `jsonb` | Internationalisierungsdaten (z.B. `{"zh_CN": {"name": "..."}}`) |

**Beispiel:**
```json
{
  "key": "266",
  "name": "Aatrox",
  "i18n": {
    "zh_CN": {
      "name": "亚托克斯"
    }
  }
}
```

**Verwendung:**
- Wird verwendet für Champion-zu-Name-Mappings
- Referenziert von `champion_stats`, `matchups`, `synergies`

---

### 2. `champion_stats`

Champion-Statistiken pro Rolle und Patch-Version.

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `patch` | `text` | Patch-Version (z.B. "16.1") |
| `champion_key` | `text` | Champion-Schlüssel (FK zu `champions.key`) |
| `role` | `text` | Rolle ("top", "jungle", "middle", "bottom", "support") |
| `games` | `integer` | Anzahl gespielter Spiele |
| `wins` | `integer` | Anzahl gewonnener Spiele |
| `damage_profile` | `jsonb` | Schadensprofil-Daten (JSON-Objekt) |
| `stats_by_time` | `jsonb` | Statistiken nach Zeitabschnitten (JSON-Objekt) |

**Indizes:**
- Kombinierter Index auf: `(patch, champion_key, role)` (vermutlich)

**Beispiel:**
```json
{
  "patch": "16.1",
  "champion_key": "266",
  "role": "top",
  "games": 12345,
  "wins": 6789,
  "damage_profile": { ... },
  "stats_by_time": { ... }
}
```

**Verwendung:**
- Hauptquelle für Winrate-Berechnungen
- Wird in der Recommendation Engine verwendet
- Basis für rollenbasierte Statistiken

---

### 3. `matchups`

Matchup-Daten zwischen Champions (pro Rolle und Patch).

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `patch` | `text` | Patch-Version |
| `champion_key` | `text` | Champion-Schlüssel (FK zu `champions.key`) |
| `role` | `text` | Rolle des Champions |
| `opponent_key` | `text` | Schlüssel des Gegner-Champions |
| `opponent_role` | `text` | Rolle des Gegners |
| `games` | `integer` | Anzahl der Spiele gegen diesen Gegner |
| `wins` | `integer` | Anzahl der Siege gegen diesen Gegner |

**Beispiel:**
```json
{
  "patch": "16.1",
  "champion_key": "266",
  "role": "top",
  "opponent_key": "103",
  "opponent_role": "top",
  "games": 500,
  "wins": 250
}
```

**Verwendung:**
- Wird für Counterpick-Berechnungen verwendet
- Basis für Matchup-Winrates
- Verwendet in der Recommendation Engine für Gegner-Bewertungen

---

### 4. `synergies`

Synergie-Daten zwischen Champions im selben Team (pro Rolle und Patch).

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `patch` | `text` | Patch-Version |
| `champion_key` | `text` | Champion-Schlüssel (FK zu `champions.key`) |
| `role` | `text` | Rolle des Champions |
| `mate_key` | `text` | Schlüssel des Teammate-Champions |
| `mate_role` | `text` | Rolle des Teammates |
| `games` | `integer` | Anzahl der Spiele mit diesem Teammate |
| `wins` | `integer` | Anzahl der Siege mit diesem Teammate |

**Beispiel:**
```json
{
  "patch": "16.1",
  "champion_key": "266",
  "role": "top",
  "mate_key": "21",
  "mate_role": "jungle",
  "games": 800,
  "wins": 480
}
```

**Verwendung:**
- Wird für Team-Synergie-Berechnungen verwendet
- Basis für Teammate-Winrates
- Verwendet in der Recommendation Engine für Team-Bewertungen

---

### 5. `items`

Item-Daten pro Patch-Version.

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `patch` | `text` | Patch-Version |
| `item_id` | `integer` | Item-ID (numerisch) |
| `name` | `text` | Item-Name |
| `gold` | `integer` | Gold-Kosten (total) |

**Beispiel:**
```json
{
  "patch": "16.1",
  "item_id": 1001,
  "name": "Boots of Speed",
  "gold": 300
}
```

**Verwendung:**
- Item-Referenzen und Metadaten

---

### 6. `runes`

Rune-Daten pro Patch-Version.

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `patch` | `text` | Patch-Version |
| `rune_id` | `integer` | Rune-ID |
| `data` | `jsonb` | Rune-Daten als JSON-Objekt |
| | | Enthält: `id`, `key`, `name`, `icon`, `pathId` |

**Beispiel:**
```json
{
  "patch": "16.1",
  "rune_id": 8000,
  "data": {
    "id": 8000,
    "key": "Precision",
    "name": "Präzision",
    "icon": "...",
    "pathId": 8000
  }
}
```

**Verwendung:**
- Rune-Referenzen und Metadaten

---

### 7. `summoner_spells`

Beschwörerzauber-Daten pro Patch-Version.

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `patch` | `text` | Patch-Version |
| `spell_key` | `text` | Beschwörerzauber-Schlüssel (z.B. "SummonerFlash") |
| `name` | `text` | Name des Zaubers |
| *(weitere Spalten möglich)* | | |

**Beispiel:**
```json
{
  "patch": "16.1",
  "spell_key": "SummonerFlash",
  "name": "Blitz"
}
```

**Verwendung:**
- Beschwörerzauber-Referenzen und Metadaten

---

### 8. `patches`

Patch-Versionen-Verwaltung.

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `patch` | `text` | Patch-Version (z.B. "16.1") - Primary Key |
| `created_at` | `timestamp` | Zeitstempel der Erstellung (automatisch) |

**Beispiel:**
```json
{
  "patch": "16.1",
  "created_at": "2024-01-15T12:00:00Z"
}
```

**Verwendung:**
- Verwaltung der verfügbaren Patch-Versionen
- Wird verwendet um den neuesten Patch zu ermitteln
- Referenz für Patch-basierte Queries

---

## Typische Queries

### Champion-Statistiken abrufen
```python
supabase.table('champion_stats') \
    .select('*') \
    .eq('patch', '16.1') \
    .eq('champion_key', '266') \
    .eq('role', 'top') \
    .execute()
```

### Matchups abrufen
```python
supabase.table('matchups') \
    .select('*') \
    .eq('patch', '16.1') \
    .eq('champion_key', '266') \
    .eq('role', 'top') \
    .execute()
```

### Synergien abrufen
```python
supabase.table('synergies') \
    .select('*') \
    .eq('patch', '16.1') \
    .eq('champion_key', '266') \
    .eq('role', 'top') \
    .execute()
```

### Neuesten Patch abrufen
```python
supabase.table('patches') \
    .select('patch') \
    .order('created_at', desc=True) \
    .limit(1) \
    .execute()
```

---

## Rolle-Namen

Die folgenden Rollen-Namen werden in der Datenbank verwendet:

- `top` - Top Lane
- `jungle` - Jungle
- `middle` / `mid` - Mid Lane
- `bottom` / `adc` - Bot Lane (ADC)
- `support` - Support

**Hinweis:** In `champion_stats` werden die Rollen normalisiert (z.B. "adc" → "bottom", "mid" → "middle").

---

## Datentypen

- `text` / `string` - Textwerte
- `integer` - Ganze Zahlen
- `jsonb` - JSON-Daten (binary JSON in PostgreSQL)
- `timestamp` - Zeitstempel

---

## Wichtige Hinweise

1. **Patch-Format:** Patches werden im Format "X.Y" gespeichert (z.B. "16.1"). Teilweise müssen Patch-Strings normalisiert werden (z.B. "16.1.1" → "16.1").

2. **Champion-Keys:** Champion-Keys werden als Strings gespeichert, obwohl sie numerisch sind (z.B. "266" statt 266).

3. **JSONB-Felder:** `damage_profile` und `stats_by_time` sind JSON-Objekte, die verschiedene Strukturen enthalten können.

4. **Indexierung:** Für optimale Performance sollten Indizes auf `(patch, champion_key, role)` Kombinationen vorhanden sein.

5. **Winrate-Berechnung:** Winrate wird meist berechnet als `wins / games`, nicht als gespeichertes Feld.

---

## Änderungshistorie

- **Erstellt:** 2024-01-XX
- **Zuletzt aktualisiert:** Basierend auf Code-Analyse der `supabase_repo.py` und `supabase-etl.ts`

---

## Weitere Informationen

- Siehe `supabase_repo.py` für Python-Query-Beispiele
- Siehe `supabase-etl.ts` für TypeScript-Datenimport-Logik
- Siehe `recommendation_engine.py` für komplexe Query-Patterns
