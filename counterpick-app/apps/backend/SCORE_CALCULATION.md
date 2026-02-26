# Score-Berechnung Dokumentation
## Recommendation Engine - Aktuelle Implementierung

**Letzte Aktualisierung:** Basierend auf `recommendation_engine.py` (Stand: 2025)

---

## Übersicht

Der **Final Score** (0-100) setzt sich aus drei normalisierten Komponenten zusammen, die gewichtet kombiniert werden:

```
Final Score = (Base Score × 0.30) + (Counter Score × 0.45) + (Synergy Score × 0.25)
```

Jede Komponente wird zunächst auf 0-100 normalisiert, bevor sie gewichtet wird.

---

## Mathematische Grundfunktionen

### 1. Wilson Score

Die Wilson Score Funktion berechnet eine statistisch sichere untere Grenze der Winrate und löst das "Low Sample Size"-Problem ohne harte Caps.

**Formel:**
```python
def wilson_score(wins, n, z=1.44):
    if n == 0: return 0.0
    phat = wins / n
    denominator = 1 + z²/n
    center_adjusted_probability = phat + z² / (2*n)
    adjusted_standard_deviation = z * √((phat*(1-phat) + z² / (4*n)) / n)
    return (center_adjusted_probability - adjusted_standard_deviation) / denominator
```

**Parameter:**
- `wins`: Anzahl der Siege
- `n`: Anzahl der Spiele (games)
- `z`: Z-Wert für Konfidenzintervall (Standard: 1.44 ≈ 85% Konfidenz)

**Verwendung:**
- **Base Stats**: z = 1.44 (konservativer, ~85% Konfidenz)
- **Matchups**: z = 1.28 (etwas lockerer, ~80% Konfidenz)
- **Synergien**: z = 1.28 (etwas lockerer, ~80% Konfidenz)

**Warum Wilson Score?**
- Berücksichtigt automatisch die Sample Size
- Kleine Samples werden konservativer bewertet
- Keine harten Caps nötig (z.B. "mindestens 15 Spiele")

### 2. Normalisierungs-Funktion

Mappt einen Wert linear auf den Bereich 0-100.

**Formel:**
```python
def normalize_score(value, min_val, max_val):
    if value <= min_val: return 0.0
    if value >= max_val: return 100.0
    return ((value - min_val) / (max_val - min_val)) * 100.0
```

**Verwendung:**
- **Base Winrate**: min_val = 0.46, max_val = 0.54 (46%-54% WR → 0-100 Score)
- **Delta (Matchup/Synergy)**: min_val = -0.08, max_val = 0.08 (-8% bis +8% Delta → 0-100 Score)

---

## 1. Base Score (0-100)

### Zweck
Bewertet die **grundlegende Stärke** eines Champions basierend auf seiner allgemeinen Winrate und Pickrate.

### Berechnung

#### Schritt 1: Wilson Score für Base Winrate
```python
base_wr_safe = wilson_score(champ['wins'], champ['games'], z=1.44)
```
- Verwendet z = 1.44 für konservative Bewertung
- Ergebnis ist eine Dezimalzahl (z.B. 0.52 für 52% WR)

#### Schritt 2: Normalisierung auf 0-100
```python
norm_base_score = normalize_score(base_wr_safe, 0.46, 0.54)
```
- Winrate ≤ 46% → 0 Punkte
- Winrate ≥ 54% → 100 Punkte
- Dazwischen: Linear interpoliert

**Beispiele:**
- 46% WR → 0.0 Punkte
- 50% WR → 50.0 Punkte
- 52% WR → 75.0 Punkte
- 54% WR → 100.0 Punkte

#### Schritt 3: Pickrate-Bonus
```python
pr_bonus = min(math.log(champ['global_pickrate'] * 100 + 1) * 2, 10)
norm_base_score = min(norm_base_score + pr_bonus, 100)
```
- **Pickrate-Bonus**: Logarithmischer Bonus für Popularität
- **Maximum**: 10 Punkte zusätzlich
- **Formel**: `log(pickrate_in_percent + 1) * 2`
- **Final**: Base Score + Bonus, gecappt auf 100

**Beispiele für Pickrate-Bonus:**
- 0.5% PR → `log(0.5 + 1) * 2 ≈ 0.81` Punkte
- 1% PR → `log(1 + 1) * 2 ≈ 1.39` Punkte
- 5% PR → `log(5 + 1) * 2 ≈ 3.58` Punkte
- 20% PR → `log(20 + 1) * 2 ≈ 6.10` Punkte
- 50% PR → `log(50 + 1) * 2 ≈ 7.82` Punkte (gecappt auf 10)

### Vollständiges Beispiel: Base Score

**Champion:**
- Wins: 5200
- Games: 10000
- Global Pickrate: 0.03 (3%)

**Berechnung:**
1. Wilson Score: `wilson_score(5200, 10000, 1.44) ≈ 0.515` (51.5% WR)
2. Normalisierung: `normalize_score(0.515, 0.46, 0.54) = 68.75` Punkte
3. Pickrate-Bonus: `min(log(3 + 1) * 2, 10) = min(2.77, 10) = 2.77` Punkte
4. **Final Base Score**: `min(68.75 + 2.77, 100) = 71.52` Punkte

---

## 2. Counter Score (0-100)

### Zweck
Bewertet, wie gut ein Champion **gegen die gegnerischen Champions** performt.

### Besonderheit: Blind Pick
Wenn `is_blind_pick = true` oder keine Gegner-Picks vorhanden sind:
```python
norm_counter_score = 50.0  # Neutral
```

### Berechnung (mit Gegnern)

Für jeden gegnerischen Champion wird ein individueller Score berechnet und gewichtet gemittelt.

#### Schritt 1: Matchup-Filterung
```python
if m['games'] < 5: continue  # Minimum 5 Spiele
```
- Matchups mit weniger als 5 Spielen werden ignoriert
- Wilson Score regelt die Sample Size, daher niedrigeres Minimum als in alter Dokumentation

#### Schritt 2: Specialist Ratio
```python
total_vs = enemy_total_games.get((opponent_id, enemy_role), 1)
m_pr = m['games'] / total_vs  # Matchup Pickrate
g_pr = max(champ['global_pickrate'], 0.001)  # Global Pickrate
spec_ratio = m_pr / g_pr
```
- **Bedeutung**: Wie oft wird dieser Champion speziell gegen diesen Gegner gepickt?
- **Ratio > 1.0**: Champion wird häufiger gegen diesen Gegner gepickt (potentieller Counter)
- **Ratio < 1.0**: Champion wird seltener gegen diesen Gegner gepickt

#### Schritt 3: Performance Delta
```python
m_wr_safe = wilson_score(m['wins'], m['games'], z=1.28)
delta = m_wr_safe - base_wr_safe
```
- **Delta**: Differenz zwischen Matchup-Winrate und Base-Winrate
- **Positiv**: Besser gegen diesen Gegner als im Durchschnitt
- **Negativ**: Schlechter gegen diesen Gegner als im Durchschnitt

#### Schritt 4: Normalisierung auf 0-100
```python
m_score = normalize_score(delta, -0.08, 0.08)
```
- Delta ≤ -8% → 0 Punkte (schlechter Matchup)
- Delta ≥ +8% → 100 Punkte (starker Counter)
- Dazwischen: Linear interpoliert

**Beispiele:**
- Delta = -8% → 0.0 Punkte
- Delta = 0% → 50.0 Punkte (neutral)
- Delta = +4% → 75.0 Punkte
- Delta = +8% → 100.0 Punkte

#### Schritt 5: Specialist Counter Bonus
```python
if spec_ratio > 1.5 and delta > 0:
    m_score = min(m_score * 1.1, 100)
```
- **Bedingung**: Specialist Ratio > 1.5 UND Delta > 0
- **Bonus**: Score wird um 10% erhöht (max. 100)
- **Bedeutung**: Belohnt bestätigte Counter-Picks (häufig gepickt + gute Performance)

#### Schritt 6: Importance-Gewichtung
```python
imp = ENEMY_IMPORTANCE.get(my_role, {}).get(enemy_role, 0.5)
counter_values.append(m_score * imp)
total_imp_counter += imp
```
- Jeder Gegner wird mit seiner Importance gewichtet
- Importance hängt von der Rollen-Kombination ab

#### Schritt 7: Gewichteter Durchschnitt
```python
if total_imp_counter > 0:
    norm_counter_score = sum(counter_values) / total_imp_counter
else:
    norm_counter_score = 50.0  # Neutral wenn keine Matchups
```

### ENEMY_IMPORTANCE Matrix

Wie wichtig ist der **GEGNER** auf Rolle Y für **MICH** auf Rolle X?

| Meine Rolle | Top | Jungle | Middle | Bottom | Support |
|------------|-----|--------|--------|--------|---------|
| **Top** | 2.5 | 0.8 | 0.4 | 0.1 | 0.1 |
| **Jungle** | 0.8 | 1.8 | 1.2 | 0.8 | 1.0 |
| **Middle** | 0.4 | 1.5 | 2.0 | 0.4 | 0.8 |
| **Bottom** | 0.2 | 0.8 | 0.6 | 1.5 | 1.8 |
| **Support** | 0.2 | 1.0 | 0.8 | 1.5 | 2.0 |

### Vollständiges Beispiel: Counter Score

**Szenario:**
- Meine Rolle: Top
- Gegner: Top (Jax), Jungle (Lee Sin)
- Champion: Malphite

**Gegner 1: Jax (Top)**
- Matchup: 1200 Wins / 2000 Games
- Base WR: 0.515 (51.5%)
- Matchup WR (Wilson): 0.595 (59.5%)
- Delta: +8%
- Normalisierung: `normalize_score(0.08, -0.08, 0.08) = 100.0` Punkte
- Specialist Ratio: 1.8 (> 1.5) → Bonus: `100.0 * 1.1 = 110.0` → gecappt auf `100.0`
- Importance: 2.5
- Gewichteter Wert: `100.0 * 2.5 = 250.0`

**Gegner 2: Lee Sin (Jungle)**
- Matchup: 450 Wins / 800 Games
- Matchup WR (Wilson): 0.545 (54.5%)
- Delta: +3%
- Normalisierung: `normalize_score(0.03, -0.08, 0.08) = 68.75` Punkte
- Specialist Ratio: 0.9 (< 1.5) → Kein Bonus
- Importance: 0.8
- Gewichteter Wert: `80.0 * 0.8 = 64.0`

**Final Counter Score:**
- Total Importance: `2.5 + 0.8 = 3.3`
- Summe gewichteter Werte: `250.0 + 64.0 = 314.0`
- **Final**: `314.0 / 3.3 = 95.15` Punkte

---

## 3. Synergy Score (0-100)

### Zweck
Bewertet, wie gut ein Champion **mit den eigenen Teamkollegen** harmoniert.

### Berechnung

Für jeden Teammate wird ein individueller Score berechnet und gewichtet gemittelt.

#### Schritt 1: Synergy-Filterung und Beste-Synergie-Auswahl
```python
if s['games'] < 5: continue  # Minimum 5 Spiele
# Filtere nach Rolle des empfohlenen Champions
if s_role not in my_db_roles: continue
# Verwende nur die beste Synergie pro Teammate (höchster Score)
```
- Synergien mit weniger als 5 Spielen werden ignoriert
- Nur Synergien für die aktuelle Rolle des empfohlenen Champions werden berücksichtigt
- **Wichtig**: Wenn mehrere Synergien für denselben Teammate existieren, wird nur die beste (höchster Score) verwendet
- Dies vermeidet Verzerrungen durch Ausreißer oder verschiedene Rollen-Varianten

#### Schritt 2: Importance mit Hover-Reduktion
```python
base_imp = TEAMMATE_IMPORTANCE.get(my_role, {}).get(mate_role, 0.5)
imp = base_imp * (0.5 if mate_data.get('isHovered', False) else 1.0)
```
- **Gelockte Champions**: 100% Importance
- **Gehoverte Champions**: 50% Importance
- **Bedeutung**: Gehoverte Champions sind noch nicht sicher, daher weniger Gewicht

#### Schritt 3: Performance Delta
```python
s_wr_safe = wilson_score(s['wins'], s['games'], z=1.28)
mate_base_wr_safe = wilson_score(mate_base['wins'], mate_base['games'], z=1.44)
delta = s_wr_safe - mate_base_wr_safe
```
- **Delta**: Differenz zwischen Synergy-Winrate und **Base-Winrate des TEAMMATES** (nicht des empfohlenen Champions)
- **Bedeutung**: Zeigt, wie sehr der empfohlene Champion dem Teammate hilft, besser zu performen
- **Positiv**: Der Teammate performt besser mit diesem Champion als im Durchschnitt
- **Negativ**: Der Teammate performt schlechter mit diesem Champion als im Durchschnitt
- **Wichtig**: Verwendet die Base-WR des Teammates, um zu zeigen, ob die Synergie dem Teammate hilft

#### Schritt 4: Normalisierung auf 0-100
```python
s_score = normalize_score(delta, -0.08, 0.08)
```
- Delta ≤ -8% → 0 Punkte (schlechte Synergie)
- Delta ≥ +8% → 100 Punkte (starke Synergie)
- Dazwischen: Linear interpoliert

#### Schritt 5: Importance-Gewichtung
```python
synergy_values.append(s_score * imp)
total_imp_synergy += imp
```

#### Schritt 6: Gewichteter Durchschnitt
```python
if total_imp_synergy > 0:
    norm_synergy_score = sum(synergy_values) / total_imp_synergy
else:
    norm_synergy_score = 50.0  # Neutral wenn keine Synergien
```

### TEAMMATE_IMPORTANCE Matrix

Wie wichtig ist der **TEAMMATE** auf Rolle Y für **MICH** auf Rolle X?

| Meine Rolle | Top | Jungle | Middle | Bottom | Support |
|------------|-----|--------|--------|--------|---------|
| **Top** | 0.0 | 1.5 | 1.0 | 0.5 | 0.5 |
| **Jungle** | 1.2 | 0.0 | 1.8 | 1.0 | 1.2 |
| **Middle** | 0.6 | 2.0 | 0.0 | 0.6 | 1.2 |
| **Bottom** | 0.2 | 1.2 | 0.8 | 0.0 | 2.5 |
| **Support** | 0.2 | 1.5 | 1.0 | 2.5 | 0.0 |

### Vollständiges Beispiel: Synergy Score

**Szenario:**
- Meine Rolle: Bottom
- Teammates: Support (Thresh, gelockt), Jungle (Elise, gelockt)
- Champion: Jinx

**Teammate 1: Thresh (Support, gelockt)**
- Synergy: 1800 Wins / 3000 Games
- Thresh Base WR: 0.515 (51.5%) - **Base-WR des Teammates**
- Synergy WR (Wilson): 0.565 (56.5%)
- Delta: +5% (Synergy-WR vs. Thresh Base-WR)
- Normalisierung: `normalize_score(0.05, -0.08, 0.08) = 81.25` Punkte
- Base Importance: 2.5
- Importance (gelockt): `2.5 * 1.0 = 2.5`
- Gewichteter Wert: `100.0 * 2.5 = 250.0`

**Teammate 2: Elise (Jungle, gelockt)**
- Synergy: 600 Wins / 1200 Games
- Synergy WR (Wilson): 0.535 (53.5%)
- Delta: +2%
- Normalisierung: `normalize_score(0.02, -0.08, 0.08) = 62.5` Punkte
- Base Importance: 1.2
- Importance (gelockt): `1.2 * 1.0 = 1.2`
- Gewichteter Wert: `70.0 * 1.2 = 84.0`

**Final Synergy Score:**
- Total Importance: `2.5 + 1.2 = 3.7`
- Summe gewichteter Werte: `81.25 * 2.5 + 62.5 * 1.2 = 203.125 + 75.0 = 278.125`
- **Final**: `278.125 / 3.7 = 75.17` Punkte

---

## 4. Final Score (0-100)

### Berechnung
```python
final_score = (
    (norm_base_score * SCORE_WEIGHTS['base']) +
    (norm_counter_score * SCORE_WEIGHTS['counter']) +
    (norm_synergy_score * SCORE_WEIGHTS['synergy'])
)
```

**Gewichtungen** (aus `recommendation_config.py`):
- Base: **30%** (0.30)
- Counter: **45%** (0.45) - Wichtigster Faktor
- Synergy: **25%** (0.25)

**Bedingung**: Die Summe der Gewichtungen muss 1.0 ergeben.

### Vollständiges Beispiel: Final Score

**Champion: Malphite (Top)**
- Base Score: 71.52
- Counter Score: 95.15
- Synergy Score: 50.0 (keine Teammates)

**Berechnung:**
```
Final Score = (71.52 × 0.30) + (95.15 × 0.45) + (50.0 × 0.25)
            = 21.456 + 42.818 + 12.5
            = 76.77
```

---

## Konfigurationsparameter

Alle Parameter können in `recommendation_config.py` angepasst werden:

### SCORE_WEIGHTS
```python
SCORE_WEIGHTS = {
    'base': 0.30,      # 30% - Wie stark ist der Champ im Vakuum?
    'counter': 0.45,   # 45% - Wie gut kontert er die Gegner?
    'synergy': 0.25    # 25% - Wie gut passt er ins eigene Team?
}
```

### CONFIDENCE_Z
```python
CONFIDENCE_Z = {
    'base': 1.44,      # ~85% Sicherheit für Base Stats
    'matchup': 1.28,   # ~80% Sicherheit für Matchups
    'synergy': 1.28    # ~80% Sicherheit für Synergien
}
```

### SCALING
```python
SCALING = {
    'base_wr_min': 0.46,   # Unter 46% WR gibt es 0 Punkte
    'base_wr_max': 0.54,   # Über 54% WR gibt es volle Punktzahl
    'delta_min': -0.08,    # -8% WR Unterschied = 0 Punkte
    'delta_max': 0.08,     # +8% WR Unterschied = 100 Punkte
    'k_exponent': 0.8      # Exponent für Specialist-Ratio (aktuell nicht verwendet)
}
```

### ENEMY_IMPORTANCE & TEAMMATE_IMPORTANCE
Siehe Matrizen oben.

---

## Pick Scores

Für bereits gepickte Champions (eigene und gegnerische) wird die **gleiche Logik** verwendet:

1. **Base Score**: Identisch zu Recommendations
2. **Counter Score**: Berechnet gegen alle gegnerischen Champions
3. **Synergy Score**: Berechnet mit allen eigenen Teammates (nur für eigenes Team)

**Besonderheiten:**
- Pick Scores werden für alle gepickten Champions berechnet
- Gleiche Gewichtungen und Formeln wie Recommendations
- Werden im Response als `pickScores` zurückgegeben

---

## Design-Entscheidungen

### Warum Wilson Score statt harte Caps?
- Automatische Anpassung an Sample Size
- Keine willkürlichen Schwellenwerte (z.B. "mindestens 15 Spiele")
- Statistisch fundiert

### Warum Normalisierung auf 0-100?
- Einheitliche Skala für alle Komponenten
- Einfache Gewichtung und Kombination
- Intuitive Interpretation (höher = besser)

### Warum Pickrate-Bonus im Base Score?
- Belohnt Meta-Relevanz
- Logarithmisch, um Extremwerte zu vermeiden
- Maximal 10 Punkte zusätzlich

### Warum Specialist Ratio Bonus?
- Belohnt bestätigte Counter-Picks
- Nur wenn Ratio > 1.5 UND Delta > 0 (konservativ)
- 10% Bonus (nicht zu aggressiv)

### Warum Hover-Reduktion bei Synergy?
- Gehoverte Champions sind noch nicht sicher
- 50% Gewichtung reflektiert Unsicherheit
- Gelockte Champions haben volle Gewichtung

### Warum Delta zur Base-WR des Teammates (nicht des empfohlenen Champions)?
- **Ziel**: Zeigen, wie sehr der empfohlene Champion dem Teammate hilft
- **Beispiel**: Wenn Varus (ADC) normalerweise 48% WR hat und mit Braum (Support) 52% WR hat, dann ist das eine +4% Synergie
- **Vorteil**: Unabhängig von der generellen Stärke des empfohlenen Champions (z.B. ob Braum generell gut ist)
- **Bedeutung**: Ein Support, der einem schwachen ADC hilft, sollte höher bewertet werden als ein Support, der nur gut ist, weil er selbst stark ist

### Warum nur die beste Synergie pro Teammate?
- **Problem**: Es können mehrere Synergien für denselben Champion+Teammate existieren (verschiedene Rollen-Varianten, Patches, etc.)
- **Lösung**: Nur die Synergie mit dem höchsten Score pro Teammate wird verwendet
- **Vorteil**: Vermeidet Verzerrungen durch Ausreißer oder schlechte Synergien aus anderen Rollen
- **Beispiel**: Wenn Braum+Varus in Support-Rolle +5% Delta hat, aber in Top-Rolle -3% Delta, wird nur die +5% Synergie verwendet

### Warum Importance-Matrizen?
- Nicht alle Matchups/Synergien sind gleich wichtig
- Top vs. Top ist wichtiger als Top vs. Bottom
- Reflektiert tatsächliche Spiel-Dynamik

---

## Häufige Fragen

### Warum wird ein Champion mit niedriger Base WR empfohlen?
- Starker Counter Score kann Base Score ausgleichen
- Beispiel: Base 40, Counter 90, Synergy 60 → Final 65.5

### Warum ist Counter Score wichtiger als Base Score?
- Counter-Picks sind im Draft entscheidend
- 45% Gewichtung vs. 30% für Base
- Kann in `recommendation_config.py` angepasst werden

### Was passiert bei Blind Pick?
- Counter Score wird auf 50.0 (neutral) gesetzt
- Nur Base Score und Synergy Score zählen
- Empfehlungen basieren auf allgemeiner Stärke + Team-Synergy

### Wie werden gehoverte Champions behandelt?
- Bei Synergy Score: 50% Gewichtung
- Bei Counter Score: Keine besondere Behandlung (gegnerische Hovers sind irrelevant)

### Was ist der Unterschied zwischen Pick Scores und Recommendations?
- **Recommendations**: Für noch nicht gepickte Champions
- **Pick Scores**: Für bereits gepickte Champions
- **Gleiche Logik**: Beide verwenden identische Berechnungen

---

## Debugging

### Score scheint falsch
1. Prüfe Base Score: Ist die Winrate realistisch?
2. Prüfe Counter Score: Gibt es Matchup-Daten? (Minimum 5 Spiele)
3. Prüfe Synergy Score: Gibt es Synergy-Daten? (Minimum 5 Spiele)
4. Prüfe Gewichtungen in `recommendation_config.py`

### Counter Score = 50.0
- Blind Pick Modus aktiv, oder
- Keine Matchup-Daten gefunden, oder
- Alle Matchups haben < 5 Spiele

### Synergy Score = 50.0
- Keine Teammates vorhanden, oder
- Keine Synergy-Daten gefunden, oder
- Alle Synergien haben < 5 Spiele

---

*Diese Dokumentation beschreibt exakt die Implementierung in `recommendation_engine.py`.*
