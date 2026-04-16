"""
Recommendation Engine
Komplette Überarbeitung für Season 16:
- Dynamic Weights (Blind Pick vs. Counter Pick)
- Pacing Logic (Stats by Time Parsing)
- Synergy-First Logic für Support
"""

import math
import json
from typing import Dict, List, Optional, Any
from lolalytics_api.json_repo import (
    _resolve_champion,
    _champion_map,
    _get_latest_patch,
    _table,
)

# Config Import
from recommendation_config import (
    ROLE_SCORE_WEIGHTS,
    DEFAULT_SCORE_WEIGHTS,
    BLIND_PICK_MODIFIERS,
    PACING_CONFIG,
    CONFIDENCE_Z, 
    SYNERGY_Z_THRESHOLDS,
    SCALING, 
    ENEMY_IMPORTANCE, 
    TEAMMATE_IMPORTANCE
)

# --- HELPER FUNCTIONS ---

def safe_int(value):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None

def normalize_role(role_input):
    if role_input is None: return ''
    r = str(role_input).lower().strip()
    role_map = {
        '0': 'top', '1': 'jungle', '2': 'middle', '3': 'bottom', '4': 'support',
        'mid': 'middle', 'adc': 'bottom', 'utility': 'support'
    }
    return role_map.get(r, r)

def normalize_patch(patch: Optional[str]) -> Optional[str]:
    """
    Normalisiert Patch-Version auf Major.Minor Format (z.B. "16.1.1" -> "16.1")
    """
    if not patch:
        return None
    parts = str(patch).split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return patch

def wilson_score(wins, n, z=1.44):
    """
    Berechnet die statistisch sichere untere Grenze der Winrate.
    Löst das "Low Sample Size"-Problem ohne harte Caps.
    """
    if n == 0: return 0.0
    phat = wins / n
    denominator = 1 + z**2/n
    center_adjusted_probability = phat + z**2 / (2*n)
    adjusted_standard_deviation = z * math.sqrt((phat*(1-phat) + z**2 / (4*n)) / n)
    return (center_adjusted_probability - adjusted_standard_deviation) / denominator

def normalize_score(value, min_val, max_val):
    """Mappt einen Wert auf 0-100"""
    if value <= min_val: return 0.0
    if value >= max_val: return 100.0
    return ((value - min_val) / (max_val - min_val)) * 100.0

def analyze_pacing(stats_by_time_json: Any) -> dict:
    """
    Analysiert JSON-String (stats_by_time) und gibt Pacing-Werte zurück.
    Erwartet Format: [{"wins": x, "games": y}, ...] (0-15, 15-25, etc.)
    """
    default = {'is_early': False, 'is_scaling': False, 'early_wr': 0.5}
    if not stats_by_time_json: return default
    
    try:
        # Falls es schon ein Dict/List Objekt ist (Supabase client returned manchmal schon geparst)
        buckets = stats_by_time_json if isinstance(stats_by_time_json, list) else json.loads(stats_by_time_json)
        
        if not buckets or len(buckets) < 2: return default

        # Bucket 0 ist das früheste verfügbare (meist 0-20 min)
        b_early = buckets[0]
        early_wr = b_early['wins'] / b_early['games'] if b_early['games'] > 0 else 0.5
        
        # Letzter Bucket ist Late Game (35+ min)
        b_late = buckets[-1]
        late_wr = b_late['wins'] / b_late['games'] if b_late['games'] > 0 else 0.5
        
        return {
            'is_early': early_wr >= PACING_CONFIG['early_winrate_threshold'],
            'is_scaling': late_wr >= PACING_CONFIG['late_winrate_threshold'],
            'early_wr': early_wr
        }
    except Exception:
        return default

def get_weights_for_role(role: str) -> Dict[str, float]:
    """
    Gibt rollenbasierte Gewichtungen für Score-Berechnung zurück.
    Liest Werte aus recommendation_config.py.
    
    Args:
        role: Normalisierte Rolle (top, jungle, middle, bottom, support)
    
    Returns:
        Dictionary mit 'base', 'counter', 'synergy' Gewichtungen (Summe = 1.0)
    """
    role = normalize_role(role)
    return ROLE_SCORE_WEIGHTS.get(role, DEFAULT_SCORE_WEIGHTS)

def get_synergy_z_value(games: int) -> float:
    """
    Gibt den Z-Wert für Synergy-Berechnung basierend auf Sample Size zurück.
    Kleinere Samples erhalten einen höheren (konservativeren) Z-Wert.
    """
    if games <= SYNERGY_Z_THRESHOLDS['very_small']['games_max']:
        return SYNERGY_Z_THRESHOLDS['very_small']['z']
    elif games <= SYNERGY_Z_THRESHOLDS['small']['games_max']:
        return SYNERGY_Z_THRESHOLDS['small']['z']
    elif games <= SYNERGY_Z_THRESHOLDS['medium']['games_max']:
        return SYNERGY_Z_THRESHOLDS['medium']['z']
    return SYNERGY_Z_THRESHOLDS['large']['z']

# --- MAIN LOGIC ---

def get_recommendations(
    my_role: str,
    my_team: List[Dict[str, str]],
    enemy_team: List[Dict[str, str]],
    patch: Optional[str] = None,
    is_blind_pick: bool = False
) -> Dict[str, Any]:
    try:
        print(f"[RECOMMENDATIONS] Request erhalten: role={my_role}, myTeam={len(my_team)}, enemyTeam={len(enemy_team)}, isBlindPick={is_blind_pick}")
        print(f"[RECOMMENDATIONS] myTeam Details: {my_team}")
        print(f"[RECOMMENDATIONS] enemyTeam Details: {enemy_team}")
        
        # 1. SETUP & MAPPING
        champion_maps = _champion_map()
        key_to_name = champion_maps["key_to_name"]
        name_to_key = {v: k for k, v in key_to_name.items()}

        my_role = normalize_role(my_role)
        
        # Berechne rollenbasierte Gewichtungen
        weights = get_weights_for_role(my_role)
        
        db_role_variants = {
            'support': ['support'],
            'bottom': ['bottom', 'adc'],
            'middle': ['middle', 'mid'],
            'jungle': ['jungle'],
            'top': ['top']
        }
        my_db_roles = db_role_variants.get(my_role, [my_role])

        if not patch:
            patch = _get_latest_patch()
        
        # Normalisiere Patch-Format (z.B. "16.1.1" -> "16.1")
        patch = normalize_patch(patch)

        def resolve_team_to_ids(team_list):
            resolved_ids = []
            for item in team_list:
                name_input = item.get('championKey', '') 
                raw_role = item.get('role', '')
                role = normalize_role(raw_role)
                is_hovered = item.get('isHovered', False)  # Flag für gehoverte Champions
                
                champ_id = None
                if str(name_input) in key_to_name: champ_id = str(name_input)
                elif name_input in name_to_key: champ_id = name_to_key[name_input]
                else:
                    try:
                        resolved_key, _ = _resolve_champion(name_input)
                        if resolved_key in name_to_key: champ_id = name_to_key[resolved_key]
                        elif resolved_key in key_to_name: champ_id = resolved_key
                    except: pass
                if champ_id:
                    resolved_ids.append({
                        'id': safe_int(champ_id), 
                        'role': role, 
                        'name': name_input,
                        'isHovered': is_hovered  # Flag für gehoverte Champions weitergeben
                    })
            return resolved_ids

        my_team_ids = resolve_team_to_ids(my_team)
        enemy_team_ids = resolve_team_to_ids(enemy_team)
        
        # ---------------------------------------------------------
        # ANALYSE: BLIND PICK VS COUNTER PICK
        # ---------------------------------------------------------
        # Wir prüfen, ob ein direkter Gegner auf meiner Lane existiert.
        enemy_in_lane = next((e for e in enemy_team_ids if e['role'] == my_role), None)
        
        # Wir sind im Blind Pick, wenn kein Gegner auf der Lane ist ODER explizit Blind Pick Modus an ist
        is_actually_blind_pick = is_blind_pick or (enemy_in_lane is None)
        
        print(f"[RECO] Role: {my_role} | Blind Pick Mode: {is_actually_blind_pick} (Enemy in lane: {enemy_in_lane is not None})")

        # GEWICHTUNGEN ANPASSEN
        base_weights = ROLE_SCORE_WEIGHTS.get(my_role, DEFAULT_SCORE_WEIGHTS).copy()
        
        if is_actually_blind_pick:
            mods = BLIND_PICK_MODIFIERS.get(my_role, {'base_mult': 1.0, 'synergy_mult': 1.0, 'counter_mult': 1.0})
            
            # Wende Multiplikatoren an
            base_weights['base'] *= mods['base_mult']
            base_weights['synergy'] *= mods['synergy_mult']
            base_weights['counter'] *= mods['counter_mult']
            
            # Normalisieren, damit Summe wieder 1.0 ist
            total_w = sum(base_weights.values())
            for k in base_weights:
                base_weights[k] /= total_w
                
            print(f"[RECO] Applied Blind Pick Weights: {base_weights}")
        
        weights = base_weights

        # 2. KANDIDATEN LADEN (Inklusive stats_by_time!)
        candidates = [
            row for row in _table('champion_stats')
            if row.get('patch') == patch
            and row.get('role') in my_db_roles
            and (row.get('games') or 0) > 50
        ]
        print(f"[RECOMMENDATIONS] Kandidaten aus DB geladen: {len(candidates)} für Rollen {my_db_roles}")
        if not candidates:
            print(f"[RECOMMENDATIONS] Keine Kandidaten gefunden für Rolle {my_role}, patch {patch}")
            return {'success': False, 'recommendations': [], 'error': 'No candidates found', 'patch': patch}

        # Global Pickrate Calc
        total_games_global = sum(c['games'] for c in candidates)
        picked_ids = {c['id'] for c in my_team_ids + enemy_team_ids}
        
        filtered_candidates = []
        for c in candidates:
            if safe_int(c['champion_key']) in picked_ids: continue
            pr = c['games'] / total_games_global if total_games_global > 0 else 0
            c['global_pickrate'] = pr
            # Filterung sehr schwacher/unbeliebter Champs
            if pr >= 0.005: 
                filtered_candidates.append(c)
        candidates = filtered_candidates
        
        cand_ids = [c['champion_key'] for c in candidates]
        enemy_query_ids = [str(e['id']) for e in enemy_team_ids]
        ally_query_ids = [str(a['id']) for a in my_team_ids]

        # 3. STATS LADEN
        matchups = []
        if enemy_query_ids:
            cand_ids_set = set(cand_ids)
            enemy_ids_set = set(enemy_query_ids)
            matchups = [
                row for row in _table('matchups', patch=patch)
                if row.get('patch') == patch
                and row.get('role') in my_db_roles
                and row.get('champion_key') in cand_ids_set
                and row.get('opponent_key') in enemy_ids_set
            ]

        synergies = []
        if ally_query_ids:
            cand_ids_set = set(cand_ids)
            ally_ids_set = set(ally_query_ids)
            synergies = [
                row for row in _table('synergies', patch=patch)
                if row.get('patch') == patch
                and row.get('role') in my_db_roles
                and row.get('champion_key') in cand_ids_set
                and row.get('mate_key') in ally_ids_set
            ]

        # Base-Stats der Teammates laden (für Synergy-Delta-Berechnung)
        teammate_base_stats = {}
        if ally_query_ids:
            for mate in my_team_ids:
                mate_id = mate['id']
                if mate_id is None:
                    print(f"[SYNERGY DEBUG] WARNUNG: Teammate hat keine gültige ID: {mate}")
                    continue
                    
                mate_role = normalize_role(mate['role'])
                mate_db_roles = db_role_variants.get(mate_role, [mate_role])
                
                print(f"[SYNERGY DEBUG] Lade Base-Stats für Teammate: ID={mate_id}, Role={mate_role}, DB-Roles={mate_db_roles}")
                mate_stats_data = [
                    row for row in _table('champion_stats')
                    if row.get('patch') == patch
                    and row.get('champion_key') == str(mate_id)
                    and row.get('role') in mate_db_roles
                    and (row.get('games') or 0) > 50
                ]

                if mate_stats_data:
                    # Nehme den ersten Match (sollte nur einer sein pro Champion+Rolle)
                    mate_stat = mate_stats_data[0]
                    teammate_base_stats[mate_id] = {
                        'wins': mate_stat.get('wins', 0),
                        'games': mate_stat.get('games', 0)
                    }
                    print(f"[SYNERGY DEBUG] Teammate {mate_id} ({mate_role}): Base Stats geladen - {mate_stat.get('wins', 0)}/{mate_stat.get('games', 0)}")
                else:
                    print(f"[SYNERGY DEBUG] WARNUNG: Keine Base-Stats gefunden für Teammate {mate_id} ({mate_role}) - Query: patch={patch}, champion_key={str(mate_id)}, roles={mate_db_roles}")

        # Aggregation für Specialist-Check
        enemy_total_games = {} 
        for m in matchups:
            opp_key = safe_int(m['opponent_key'])
            opp_role = normalize_role(m['opponent_role'])
            enemy_total_games[(opp_key, opp_role)] = enemy_total_games.get((opp_key, opp_role), 0) + m['games']

        # CONTEXT & PACING ANALYSE
        # Finde meinen Jungler
        my_jungler = next((m for m in my_team_ids if m['role'] == 'jungle'), None)
        my_jungler_pacing = {'is_early': False, 'is_scaling': False}
        
        if my_jungler:
            # Stats für Jungler holen um Pacing zu checken
            j_rows = [
                row for row in _table('champion_stats')
                if row.get('champion_key') == str(my_jungler['id'])
                and row.get('patch') == patch
                and row.get('role') == 'jungle'
            ]

            if j_rows:
                my_jungler_pacing = analyze_pacing(j_rows[0].get('stats_by_time'))
                print(f"[PACING] My Jungler is Early: {my_jungler_pacing['is_early']}, Scaling: {my_jungler_pacing['is_scaling']}")

        # 4. SCORE BERECHNUNG
        recommendations = []

        for champ in candidates:
            c_id = safe_int(champ['champion_key'])
            
            # --- A. BASE SCORE (0-100) ---
            # Wilson Score für solide Basis-Bewertung
            base_wr_safe = wilson_score(champ['wins'], champ['games'], z=CONFIDENCE_Z['base'])
            norm_base_score = normalize_score(base_wr_safe, SCALING['base_wr_min'], SCALING['base_wr_max'])
            
            # Popularitäts-Bonus (Meta-Faktor), max 10% on top
            pr_bonus = min(math.log(champ['global_pickrate'] * 100 + 1) * 2, 10)
            norm_base_score = min(norm_base_score + pr_bonus, 100)

            # --- B. COUNTER SCORE (0-100) ---
            # Auch im Blind Pick berechnen wir Counter, gewichten sie aber niedrig
            norm_counter_score = 50.0
            if enemy_team_ids:
                counter_values = []
                total_imp_counter = 0
                c_matchups = [m for m in matchups if safe_int(m['champion_key']) == c_id]
                
                for m in c_matchups:
                    m_opp_id = safe_int(m['opponent_key'])
                    opp_data = next((e for e in enemy_team_ids if e['id'] == m_opp_id), None)
                    
                    # Wilson regelt Sample Size, nur extrems kleine Samples filtern
                    if not opp_data or m['games'] < 5: continue

                    enemy_role = normalize_role(opp_data['role'])
                    db_role = normalize_role(m['opponent_role'])
                    if enemy_role != db_role: continue

                    imp = ENEMY_IMPORTANCE.get(my_role, {}).get(enemy_role, 0.5)
                    
                    # 1. Specialist Ratio (Ist es ein Nischen-Counter?)
                    total_vs = enemy_total_games.get((m_opp_id, enemy_role), 1)
                    m_pr = m['games'] / total_vs
                    g_pr = max(champ['global_pickrate'], 0.001)
                    spec_ratio = m_pr / g_pr
                    
                    # 2. Performance Delta (Wilson Matchup vs. Wilson Base)
                    m_wr_safe = wilson_score(m['wins'], m['games'], z=CONFIDENCE_Z['matchup'])
                    delta = m_wr_safe - base_wr_safe
                    
                    # Mapping auf 0-100
                    m_score = normalize_score(delta, SCALING['delta_min'], SCALING['delta_max'])
                    
                    # Bonus für bestätigte Specialist-Counter
                    if spec_ratio > 1.5 and delta > 0:
                         m_score = min(m_score * 1.1, 100)

                    counter_values.append(m_score * imp)
                    total_imp_counter += imp

                if total_imp_counter > 0:
                    norm_counter_score = sum(counter_values) / total_imp_counter

            # --- C. SYNERGY SCORE (0-100) ---
            synergy_values = []
            total_imp_synergy = 0
            c_synergies = [s for s in synergies if safe_int(s['champion_key']) == c_id]
            
            # Gruppiere Synergien nach Teammate und verwende nur die beste pro Teammate
            synergies_by_mate = {}
            for s in c_synergies:
                s_mate_id = safe_int(s['mate_key'])
                mate_data = next((a for a in my_team_ids if a['id'] == s_mate_id), None)
                if not mate_data or s['games'] < 5: continue
                
                # Filtere nach Rolle des empfohlenen Champions (nur Synergien für die aktuelle Rolle)
                s_role = normalize_role(s.get('role', ''))
                if s_role not in my_db_roles:
                    print(f"[SYNERGY DEBUG] Champion {c_id} + Teammate {s_mate_id}: Synergie gefiltert - Champion-Rolle '{s_role}' nicht in {my_db_roles}")
                    continue
                
                # Filtere nach Rolle des Teammates (strikte Rollen-Matching)
                s_mate_role = normalize_role(s.get('mate_role', ''))
                mate_role_normalized = normalize_role(mate_data['role'])
                if s_mate_role != mate_role_normalized:
                    print(f"[SYNERGY DEBUG] Champion {c_id} + Teammate {s_mate_id}: Synergie gefiltert - Teammate-Rolle '{s_mate_role}' passt nicht zu erwarteter Rolle '{mate_role_normalized}' (Games={s['games']})")
                    continue
                
                # Berechne Score für diese Synergie
                mate_base = teammate_base_stats.get(s_mate_id)
                synergy_z = get_synergy_z_value(s['games'])
                if mate_base and mate_base['games'] > 0:
                    mate_base_wr_safe = wilson_score(mate_base['wins'], mate_base['games'], z=CONFIDENCE_Z['base'])
                    s_wr_safe = wilson_score(s['wins'], s['games'], z=synergy_z)
                    delta = s_wr_safe - mate_base_wr_safe
                else:
                    s_wr_safe = wilson_score(s['wins'], s['games'], z=synergy_z)
                    delta = s_wr_safe - base_wr_safe
                
                s_score = normalize_score(delta, SCALING['delta_min'], SCALING['delta_max'])
                
                # Sammle alle passenden Synergien (mit korrekten Rollen)
                if s_mate_id not in synergies_by_mate:
                    synergies_by_mate[s_mate_id] = []
                synergies_by_mate[s_mate_id].append({
                    'synergy': s,
                    'score': s_score,
                    'delta': delta,
                    'mate_data': mate_data,
                    'games': s['games']
                })
            
            # Wähle für jeden Teammate die Synergie mit den meisten Games (nicht den höchsten Score)
            best_synergies_by_mate = {}
            for s_mate_id, synergy_list in synergies_by_mate.items():
                # Sortiere nach Games (absteigend) - mehr Games = zuverlässigere Daten
                synergy_list.sort(key=lambda x: x['games'], reverse=True)
                best_synergy = synergy_list[0]
                best_synergies_by_mate[s_mate_id] = best_synergy
                print(f"[SYNERGY DEBUG] Champion {c_id} + Teammate {s_mate_id}: {len(synergy_list)} passende Synergien gefunden, gewählt: Games={best_synergy['games']} (Rolle: {normalize_role(best_synergy['synergy'].get('role', ''))} + {normalize_role(best_synergy['synergy'].get('mate_role', ''))})")
            
            # Verarbeite die besten Synergien pro Teammate
            for s_mate_id, best_synergy in best_synergies_by_mate.items():
                s = best_synergy['synergy']
                s_score = best_synergy['score']
                delta = best_synergy['delta']
                mate_data = best_synergy['mate_data']
                
                mate_role = normalize_role(mate_data['role'])
                base_imp = TEAMMATE_IMPORTANCE.get(my_role, {}).get(mate_role, 0.5)
                
                # Reduziere Importance für gehoverte Champions (50% Gewichtung)
                # Gelockte Champions haben 100% Gewichtung
                imp = base_imp * (0.5 if mate_data.get('isHovered', False) else 1.0)
                
                mate_base = teammate_base_stats.get(s_mate_id)
                synergy_z = get_synergy_z_value(s['games'])
                raw_wr = s['wins'] / s['games'] if s['games'] > 0 else 0.0
                if mate_base and mate_base['games'] > 0:
                    mate_base_wr_safe = wilson_score(mate_base['wins'], mate_base['games'], z=CONFIDENCE_Z['base'])
                    s_wr_safe = wilson_score(s['wins'], s['games'], z=synergy_z)
                    print(f"[SYNERGY DEBUG] Champion {c_id} + Teammate {s_mate_id}: BESTE Synergie (gewählt nach Games-Priorisierung) - Games={s['games']}, Z={synergy_z:.2f}, Raw-WR={raw_wr:.4f}, Safe-WR={s_wr_safe:.4f}, Mate-Base-WR={mate_base_wr_safe:.4f}, Delta={delta:.4f}, Score={s_score:.2f}")
                else:
                    s_wr_safe = wilson_score(s['wins'], s['games'], z=synergy_z)
                    print(f"[SYNERGY DEBUG] WARNUNG: Champion {c_id} + Teammate {s_mate_id}: BESTE Synergie - Games={s['games']}, Z={synergy_z:.2f}, Raw-WR={raw_wr:.4f}, Safe-WR={s_wr_safe:.4f}, Keine Base-Stats für Teammate, verwende Fallback (Delta={delta:.4f}, Score={s_score:.2f})")
                
                print(f"[SYNERGY DEBUG] Champion {c_id} + Teammate {s_mate_id}: Score={s_score:.2f}, Importance={imp:.2f}, Gewichteter Wert={s_score * imp:.2f}")
                
                synergy_values.append(s_score * imp)
                total_imp_synergy += imp

            if total_imp_synergy > 0:
                norm_synergy_score = sum(synergy_values) / total_imp_synergy
                print(f"[SYNERGY DEBUG] Champion {c_id}: Final Synergy Score = {norm_synergy_score:.2f} (Total Importance: {total_imp_synergy:.2f}, Summe gewichteter Werte: {sum(synergy_values):.2f})")
            else:
                norm_synergy_score = 50.0
                print(f"[SYNERGY DEBUG] Champion {c_id}: Keine Synergien gefunden, Score = 50.0 (neutral)")

            # --- D. PACING PENALTY & BONUS (Season 16 Logic) ---
            pacing_mod = 0
            cand_pacing = analyze_pacing(champ.get('stats_by_time'))
            
            # Szenario 1: Passiver Jungler im Team
            if my_jungler_pacing['is_scaling']:
                # Wenn ich auch passiv bin -> Schlecht (zu viele Losing Lanes / kein Druck)
                if cand_pacing['is_scaling']:
                    # Kleiner Abzug, wir wollen nicht 3 Scaling Lanes + Scaling Jungle
                    pacing_mod -= PACING_CONFIG['passive_jungler_penalty']
                
                # Wenn ich Early stark bin -> Gut (Ich kaufe Zeit für den Jungler)
                if cand_pacing['is_early']:
                    pacing_mod += PACING_CONFIG['synergy_compensation_bonus']

            # --- FINAL CALCULATION ---
            final_score = (
                (norm_base_score * weights['base']) +
                (norm_counter_score * weights['counter']) +
                (norm_synergy_score * weights['synergy'])
            ) + pacing_mod

            c_name = key_to_name.get(str(c_id), str(c_id))
            recommendations.append({
                'championKey': c_name,
                'role': my_role,
                'score': round(final_score, 1),
                'baseScore': round(norm_base_score, 1),
                'counterScore': round(norm_counter_score, 1),
                'synergyScore': round(norm_synergy_score, 1),
                'details': {
                    'base': round(norm_base_score, 1),
                    'counter': round(norm_counter_score, 1),
                    'synergy': round(norm_synergy_score, 1),
                    'pacing_mod': round(pacing_mod, 1)
                },
                'winrate': round(base_wr_safe * 100, 1),
                'pacing': {  # Für Frontend Debugging nützlich
                    'early': cand_pacing['is_early'],
                    'scaling': cand_pacing['is_scaling']
                }
            })

        recommendations.sort(key=lambda x: x['score'], reverse=True)
        
        # 5. PICK SCORES für bereits gepickte Champions berechnen
        # WICHTIG: Verwendet die GLEICHE Logik wie Recommendations (inkl. Synergy)!
        pick_scores = {}
        
        # Berechne Scores für alle gepickten Champions (eigenes Team + gegnerisches Team)
        all_picked_ids = list(picked_ids)
        if all_picked_ids:
            # Lade Stats für gepickte Champions (alle Rollen)
            picked_key_set = {str(pid) for pid in all_picked_ids}
            picked_stats = [
                row for row in _table('champion_stats')
                if row.get('patch') == patch
                and row.get('champion_key') in picked_key_set
            ]

            # Lade Matchups für gepickte Champions gegen andere gepickte Champions
            picked_matchups = []
            if len(all_picked_ids) > 1:
                picked_matchups = [
                    row for row in _table('matchups', patch=patch)
                    if row.get('patch') == patch
                    and row.get('champion_key') in picked_key_set
                    and row.get('opponent_key') in picked_key_set
                ]

            # Lade Synergien für gepickte Champions im eigenen Team
            picked_synergies = []
            my_team_pick_ids = [str(m['id']) for m in my_team_ids]
            if len(my_team_ids) > 1:
                my_team_key_set = set(my_team_pick_ids)
                picked_synergies = [
                    row for row in _table('synergies', patch=patch)
                    if row.get('patch') == patch
                    and row.get('champion_key') in my_team_key_set
                    and row.get('mate_key') in my_team_key_set
                ]
            
            # Berechne Scores für jeden gepickten Champion
            for team_member in my_team_ids + enemy_team_ids:
                c_id = team_member['id']
                pick_role = normalize_role(team_member.get('role', ''))
                c_name = team_member.get('name', key_to_name.get(str(c_id), str(c_id)))
                
                # DB-Rollen-Varianten für Matching
                pick_db_roles = db_role_variants.get(pick_role, [pick_role]) if pick_role else []
                
                # Finde Stats für diesen Champion in seiner Rolle
                matching_stat = None
                for stat in picked_stats:
                    stat_id = safe_int(stat['champion_key'])
                    stat_role = normalize_role(stat.get('role', ''))
                    if stat_id == c_id:
                        # Bevorzuge passende Rolle, sonst nimm ersten Match
                        if stat_role in pick_db_roles:
                            matching_stat = stat
                            break
                        elif matching_stat is None:
                            matching_stat = stat
                
                if not matching_stat:
                    print(f"[PICK-SCORE] Warnung: Keine Stats für {c_name} (ID: {c_id}, Rolle: {pick_role})")
                    continue
                
                # --- A. BASE SCORE (0-100) --- (GLEICH wie Recommendations)
                base_wr_safe = wilson_score(matching_stat['wins'], matching_stat['games'], z=CONFIDENCE_Z['base'])
                norm_base_score = normalize_score(base_wr_safe, SCALING['base_wr_min'], SCALING['base_wr_max'])
                
                pr = matching_stat['games'] / total_games_global if total_games_global > 0 else 0
                pr_bonus = min(math.log(pr * 100 + 1) * 2, 10)
                norm_base_score = min(norm_base_score + pr_bonus, 100)
                
                # --- B. COUNTER SCORE (0-100) --- (GLEICH wie Recommendations)
                counter_values = []
                total_imp_counter = 0
                
                # Bestimme gegnerische Champions
                is_my_team = team_member in my_team_ids
                opponents = enemy_team_ids if is_my_team else my_team_ids
                
                for opp in opponents:
                    opp_id = opp['id']
                    opp_role = normalize_role(opp.get('role', ''))
                    
                    # Finde Matchup - prüfe alle Rollen-Varianten
                    for m in picked_matchups:
                        if safe_int(m['champion_key']) == c_id and safe_int(m['opponent_key']) == opp_id:
                            m_role = normalize_role(m.get('role', ''))
                            m_opp_role = normalize_role(m.get('opponent_role', ''))
                            
                            # Rolle muss passen (mit Varianten-Check)
                            opp_db_roles = db_role_variants.get(opp_role, [opp_role]) if opp_role else []
                            if m_role not in pick_db_roles or m_opp_role not in opp_db_roles:
                                continue
                            
                            if m['games'] < 5:
                                continue
                            
                            imp = ENEMY_IMPORTANCE.get(pick_role, {}).get(opp_role, 0.5)
                            m_wr_safe = wilson_score(m['wins'], m['games'], z=CONFIDENCE_Z['matchup'])
                            delta = m_wr_safe - base_wr_safe
                            m_score = normalize_score(delta, SCALING['delta_min'], SCALING['delta_max'])
                            
                            counter_values.append(m_score * imp)
                            total_imp_counter += imp
                            break
                
                if total_imp_counter > 0:
                    norm_counter_score = sum(counter_values) / total_imp_counter
                else:
                    norm_counter_score = 50.0  # Neutral wenn keine Matchups
                
                # --- C. SYNERGY SCORE (0-100) --- (NEU! Gleich wie Recommendations)
                synergy_values = []
                total_imp_synergy = 0
                
                # Synergien nur für eigenes Team berechnen
                if is_my_team and len(my_team_ids) > 1:
                    # Gruppiere Synergien nach Teammate und verwende nur die beste pro Teammate
                    synergies_by_mate = {}
                    for mate in my_team_ids:
                        if mate['id'] == c_id:  # Überspringe sich selbst
                            continue
                        
                        mate_id = mate['id']
                        mate_role = normalize_role(mate.get('role', ''))
                        
                        # Finde alle Synergien für diesen Teammate
                        for s in picked_synergies:
                            if safe_int(s['champion_key']) == c_id and safe_int(s['mate_key']) == mate_id:
                                s_role = normalize_role(s.get('role', ''))
                                if s_role not in pick_db_roles:
                                    continue
                                
                                if s['games'] < 5:
                                    continue
                                
                                # Berechne Score für diese Synergie
                                synergy_z = get_synergy_z_value(s['games'])
                                s_wr_safe = wilson_score(s['wins'], s['games'], z=synergy_z)
                                mate_base = teammate_base_stats.get(mate_id)
                                if mate_base and mate_base['games'] > 0:
                                    mate_base_wr_safe = wilson_score(mate_base['wins'], mate_base['games'], z=CONFIDENCE_Z['base'])
                                    delta = s_wr_safe - mate_base_wr_safe
                                else:
                                    delta = s_wr_safe - base_wr_safe
                                
                                s_score = normalize_score(delta, SCALING['delta_min'], SCALING['delta_max'])
                                
                                # Speichere nur die beste Synergie pro Teammate (höchster Score)
                                if mate_id not in synergies_by_mate or s_score > synergies_by_mate[mate_id]['score']:
                                    synergies_by_mate[mate_id] = {
                                        'synergy': s,
                                        'score': s_score,
                                        'mate': mate
                                    }
                    
                    # Verarbeite die besten Synergien pro Teammate
                    for mate_id, best_synergy in synergies_by_mate.items():
                        s = best_synergy['synergy']
                        s_score = best_synergy['score']
                        mate = best_synergy['mate']
                        mate_role = normalize_role(mate.get('role', ''))
                        
                        imp = TEAMMATE_IMPORTANCE.get(pick_role, {}).get(mate_role, 0.5)
                        
                        synergy_values.append(s_score * imp)
                        total_imp_synergy += imp
                
                if total_imp_synergy > 0:
                    norm_synergy_score = sum(synergy_values) / total_imp_synergy
                else:
                    norm_synergy_score = 50.0  # Neutral wenn keine Synergien
                
                # Berechne rollenbasierte Gewichtungen für diesen Champion
                pick_weights = get_weights_for_role(pick_role)
                
                # --- FINAL CALCULATION --- (GLEICHE Gewichtung wie Recommendations!)
                final_score = (
                    (norm_base_score * pick_weights['base']) +
                    (norm_counter_score * pick_weights['counter']) +
                    (norm_synergy_score * pick_weights['synergy'])
                )
                
                # Speichere Score mit Champion-Name als Key
                pick_scores[c_name] = {
                    'championKey': c_name,
                    'role': pick_role,
                    'score': round(final_score, 1),
                    'baseScore': round(norm_base_score, 1),
                    'counterScore': round(norm_counter_score, 1),
                    'synergyScore': round(norm_synergy_score, 1),
                    'winrate': round(base_wr_safe * 100, 1)
                }
        
        print(f"[RECOMMENDATIONS] {len(recommendations)} Kandidaten bewertet, Top 15 zurückgegeben")
        if recommendations:
            print(f"[RECOMMENDATIONS] Top 3: {[(r['championKey'], r['score']) for r in recommendations[:3]]}")
        
        return {
            'success': True, 
            'recommendations': recommendations[:15], 
            'patch': patch,
            'pickScores': pick_scores  # Scores für gepickte Champions (mit Matchup + Synergy)
        }

    except Exception as e:
        print(f"[RECOMMENDATIONS ERROR] {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e), 'recommendations': [], 'pickScores': {}}
