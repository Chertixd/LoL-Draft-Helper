"""
recommendation_config.py
Konfiguration für die Recommendation Engine (Season 16 Draft Logic).
"""

# --- 1. BASIS GEWICHTUNGEN (Standard Scenario) ---
# Diese werden genutzt, wenn wir eine Mischung aus Infos haben.
ROLE_SCORE_WEIGHTS = {
    'top':     {'base': 0.30, 'counter': 0.60, 'synergy': 0.10},
    'jungle':  {'base': 0.50, 'counter': 0.15, 'synergy': 0.35},
    'middle':  {'base': 0.45, 'counter': 0.35, 'synergy': 0.20},
    'bottom':  {'base': 0.55, 'counter': 0.25, 'synergy': 0.20},
    'support': {'base': 0.20, 'counter': 0.40, 'synergy': 0.40}
}

DEFAULT_SCORE_WEIGHTS = {'base': 0.35, 'counter': 0.35, 'synergy': 0.30}

# --- 2. DYNAMISCHE PICK-ORDER MODIFIKATOREN (NEU) ---
# Wenn wir "Blind Picken" (Gegner auf meiner Lane ist noch nicht gepickt):
# - Counter wird fast irrelevant (wir wissen ja nicht gegen wen)
# - Synergy und Base Stats werden extrem wichtig
BLIND_PICK_MODIFIERS = {
    'top':     {'base_mult': 1.5, 'synergy_mult': 1.2, 'counter_mult': 0.1}, # Top Blind: Safe Pick (Base)
    'jungle':  {'base_mult': 1.3, 'synergy_mult': 1.5, 'counter_mult': 0.1}, # Jgl Blind: Synergy/Meta
    'middle':  {'base_mult': 1.4, 'synergy_mult': 1.3, 'counter_mult': 0.2},
    'bottom':  {'base_mult': 1.2, 'synergy_mult': 1.5, 'counter_mult': 0.2}, # ADC Blind: Synergy mit Supp
    'support': {'base_mult': 1.0, 'synergy_mult': 2.5, 'counter_mult': 0.1}, # SUPP Blind: MAX SYNERGY
}

# --- 3. PACING & STATS BY TIME (NEU) ---
PACING_CONFIG = {
    'early_winrate_threshold': 0.525, # Ab 52.5% WR im ersten Bucket = Early Champ
    'late_winrate_threshold': 0.535,  # Ab 53.5% WR im letzten Bucket = Scaling Champ
    'passive_jungler_penalty': 15.0,  # Score-Abzug für Early-Weak Laners wenn Jungler passiv ist
    'synergy_compensation_bonus': 10.0 # Bonus wenn man Early pickt um Scaling Jungler zu helfen
}

# --- 4. STATISTIK / WILSON SCORE ---
CONFIDENCE_Z = {
    'base': 1.44,      # ~85%
    'matchup': 1.28    # ~80%
}

SYNERGY_Z_THRESHOLDS = {
    'very_small': {'games_max': 15, 'z': 1.64},
    'small': {'games_max': 40, 'z': 1.44},
    'medium': {'games_max': 100, 'z': 1.36},
    'large': {'games_max': float('inf'), 'z': 1.28}
}

# --- 5. SKALIERUNG ---
SCALING = {
    'base_wr_min': 0.45,
    'base_wr_max': 0.56,
    'delta_min': -0.10,
    'delta_max': 0.10,
    'k_exponent': 0.8
}

# --- 6. IMPORTANCE MATRIZEN (Season 16 Meta) ---
# Botlane = 2v2 Insel, Top = 1v1 + Jungle

ENEMY_IMPORTANCE = {
    'bottom':  {'support': 2.5, 'bottom': 2.0, 'jungle': 0.5, 'middle': 0.2, 'top': 0.0},
    'support': {'support': 2.0, 'bottom': 2.5, 'jungle': 0.5, 'middle': 0.2, 'top': 0.0},
    'top':     {'top': 2.2, 'jungle': 1.0, 'middle': 0.3, 'bottom': 0.0, 'support': 0.0},
    'middle':  {'middle': 2.0, 'jungle': 1.5, 'support': 0.8, 'top': 0.3, 'bottom': 0.3},
    'jungle':  {'jungle': 1.8, 'middle': 1.2, 'support': 1.0, 'top': 1.0, 'bottom': 1.0}
}

TEAMMATE_IMPORTANCE = {
    'bottom':  {'support': 3.0, 'jungle': 1.0, 'middle': 0.5, 'top': 0.1, 'bottom': 0.0},
    'support': {'bottom': 3.0, 'jungle': 1.2, 'middle': 0.8, 'top': 0.1, 'support': 0.0},
    'top':     {'jungle': 1.8, 'middle': 0.8, 'support': 0.2, 'bottom': 0.1, 'top': 0.0},
    'middle':  {'jungle': 2.0, 'support': 1.0, 'top': 0.5, 'bottom': 0.5, 'middle': 0.0},
    'jungle':  {'middle': 1.5, 'top': 1.2, 'support': 1.2, 'bottom': 1.0, 'jungle': 0.0}
}
