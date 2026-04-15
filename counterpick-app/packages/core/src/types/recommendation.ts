/**
 * Recommendation Engine TypeScript-Types
 * Entspricht der Python recommendation_engine.py
 */

/**
 * Team-Mitglied für Recommendation Request
 */
export interface TeamMember {
    championKey: string;
    role: string;
}

/**
 * Request für die Recommendation Engine
 */
export interface RecommendationRequest {
    myRole: string;
    myTeam: TeamMember[];
    enemyTeam: TeamMember[];
    patch?: string;
    isBlindPick?: boolean;
}

/**
 * Einzelne Recommendation aus der Engine
 */
export interface RecommendationItem {
    championKey: string;
    role: string;
    score: number;
    baseScore: number;
    counterScore: number;
    synergyScore: number;
    winrate: number;
    details: {
        base: number;
        counter: number;
        synergy: number;
    };
}

/**
 * Score für einen bereits gepickten Champion
 * Enthält den kombinierten Score basierend auf Base, Counter und Synergy
 * GLEICHE Berechnung wie RecommendationItem!
 */
export interface PickScore {
    championKey: string;
    role: string;
    score: number;           // Kombinierter Score (0-100) - gleiche Gewichtung wie Recommendations
    baseScore?: number;      // Basis-Score (Winrate + Meta) - 30%
    counterScore?: number;   // Counter-Score gegen gepickte Gegner - 45%
    synergyScore?: number;   // Synergy-Score mit Teammates - 25%
    winrate: number;         // Basis-Winrate in %
}

/**
 * Response von der Recommendation Engine
 */
export interface RecommendationResponse {
    success: boolean;
    recommendations: RecommendationItem[];
    patch: string;
    error?: string;
    pickScores?: Record<string, PickScore>;  // Scores für gepickte Champions
}

/**
 * Score Weights Konfiguration
 * Entspricht recommendation_config.py SCORE_WEIGHTS
 */
export interface ScoreWeights {
    base: number;
    counter: number;
    synergy: number;
}

/**
 * Role Importance Matrix
 * Entspricht recommendation_config.py ENEMY_IMPORTANCE / TEAMMATE_IMPORTANCE
 */
export type RoleImportanceMatrix = {
    [myRole: string]: {
        [targetRole: string]: number;
    };
};

