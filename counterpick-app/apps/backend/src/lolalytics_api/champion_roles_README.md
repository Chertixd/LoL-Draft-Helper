# Champion Roles Configuration

Diese Datei (`champion_roles.json`) enthält die Rollenzuordnung für Champions, um automatisch die richtige Synergy-Rolle zu bestimmen.

## Struktur

### `support_champions`
Liste aller Support-Champions (lowercase, ohne Sonderzeichen).
- Wenn ein Support eingegeben wird → Backend sucht ADC-Synergien

### `adc_champions`
Liste aller ADC/Marksman-Champions.
- Wenn ein ADC eingegeben wird → Backend sucht Support-Synergien

### `role_synergy_mapping`
Mapping für zukünftige Erweiterungen (Jungle↔Mid, etc.)

### `opgg_role_names`
OP.GG-spezifische Rollennamen (wird intern verwendet)

## Neue Champions hinzufügen

Wenn ein neuer Champion released wird:

1. Öffne `champion_roles.json`
2. Füge den Champion zur passenden Liste hinzu:
   - Support → `support_champions`
   - ADC → `adc_champions`
3. **Wichtig:** Champion-Name in lowercase ohne Sonderzeichen!
   - ✅ `"kaisa"` oder `"kai'sa"`
   - ❌ `"Kai'Sa"`

## Beispiele

```json
{
  "support_champions": [
    "neuer_support_champion"
  ],
  "adc_champions": [
    "neuer_adc_champion"
  ]
}
```

## Backend-Restart

Nach Änderungen an dieser Datei muss das Backend neu gestartet werden:
```bash
python backend.py
```

