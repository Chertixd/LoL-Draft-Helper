/**
 * Role-bezogene Konstanten
 * Entspricht teilweise recommendation_config.py
 */

import type { ScoreWeights, RoleImportanceMatrix } from '../types/recommendation';

/**
 * Score Weights für Recommendation Engine
 * Entspricht Python: SCORE_WEIGHTS
 */
export const SCORE_WEIGHTS: ScoreWeights = {
    base: 0.30,      // 30% - Wie stark ist der Champ im Vakuum?
    counter: 0.45,   // 45% - Wie gut kontert er die Gegner?
    synergy: 0.25    // 25% - Wie gut passt er ins eigene Team?
};

/**
 * Gegner-Importance Matrix
 * Wie wichtig ist der GEGNER auf Rolle Y für MICH auf Rolle X?
 * Entspricht Python: ENEMY_IMPORTANCE
 */
export const ENEMY_IMPORTANCE: RoleImportanceMatrix = {
    bottom:  { support: 1.8, bottom: 1.5, jungle: 0.8, middle: 0.5, top: 0.0 },
    support: { support: 2.0, bottom: 1.5, jungle: 1.0, middle: 0.8, top: 0.2 },
    top:     { top: 2.5, jungle: 0.8, middle: 0.4, bottom: 0.1, support: 0.1 },
    middle:  { middle: 2.0, jungle: 1.5, support: 0.8, top: 0.4, bottom: 0.4 },
    jungle:  { jungle: 1.8, middle: 1.2, support: 1.0, top: 0.8, bottom: 0.8 }
};

/**
 * Teammate-Importance Matrix
 * Wie wichtig ist der TEAMMATE auf Rolle Y für MICH auf Rolle X?
 * Entspricht Python: TEAMMATE_IMPORTANCE
 */
export const TEAMMATE_IMPORTANCE: RoleImportanceMatrix = {
    bottom:  { support: 2.5, jungle: 1.2, middle: 0.8, top: 0.2, bottom: 0.0 },
    support: { bottom: 2.5, jungle: 1.5, middle: 1.0, top: 0.2, support: 0.0 },
    top:     { jungle: 1.5, middle: 1.0, support: 0.5, bottom: 0.5, top: 0.0 },
    middle:  { jungle: 2.0, support: 1.2, top: 0.6, bottom: 0.6, middle: 0.0 },
    jungle:  { middle: 1.8, top: 1.2, support: 1.2, bottom: 1.0, jungle: 0.0 }
};

/**
 * Rank-Optionen für UI
 */
export const RANK_OPTIONS = [
    { value: 'emerald', label: 'Emerald+ (Standard)' },
    { value: 'diamond', label: 'Diamond+' },
    { value: 'master', label: 'Master+' },
    { value: 'grandmaster', label: 'Grandmaster+' },
    { value: 'challenger', label: 'Challenger' },
    { value: 'platinum', label: 'Platinum+' },
    { value: 'gold', label: 'Gold+' },
    { value: 'silver', label: 'Silver+' },
    { value: 'bronze', label: 'Bronze+' },
    { value: 'iron', label: 'Iron+' },
    { value: 'all', label: 'Alle Ränge' }
] as const;

/**
 * Standard-Rank
 */
export const DEFAULT_RANK = 'emerald';

