/**
 * Draft-bezogene TypeScript-Types
 */

export type Role = 'top' | 'jungle' | 'middle' | 'bottom' | 'support';
export type RoleId = 0 | 1 | 2 | 3 | 4;

/**
 * Typ des Rollen-Locks
 * - none: Keine Rolle zugewiesen
 * - auto: Automatisch aus LCU assignedPosition (höchste Priorität, unüberschreibbar)
 * - manual: Vom User manuell gesetzt
 * - prediction: Basierend auf statistischen Wahrscheinlichkeiten
 */
export type RoleLockType = 'none' | 'auto' | 'manual' | 'prediction';

/**
 * Wahrscheinlichkeiten pro Rolle für einen Champion
 */
export type RoleProbabilities = Record<Role, number>;

/**
 * Pick im Draft
 */
export interface DraftPick {
    champion: string;
    championId?: number;
    role?: Role;  // Finale Rolle (manuell, auto oder predicted)
    predictedRole?: Role;  // Vom Backend vorhergesagte Rolle (basierend auf Stats)
    assignedPosition?: string;  // Originale LCU assignedPosition
    cellId?: number;  // CellId für manuelle Rollen-Overrides
    isLocked: boolean;
    hoverChampion?: string;
    
    // Neue Felder für Smart Role Locking
    roleProbabilities?: RoleProbabilities;  // Wahrscheinlichkeiten pro Rolle (0-1)
    roleLockType?: RoleLockType;  // Typ des Locks
    roleConfidence?: number;  // Confidence-Score (0-1) für die zugewiesene Rolle
    totalGames?: number;  // Anzahl Spiele für den Champion (für Confidence-Berechnung)
}

/**
 * Ban im Draft
 */
export interface DraftBan {
    champion: string;
    championId?: number;
}

/**
 * Draft-State für ein Team
 */
export interface TeamDraft {
    picks: DraftPick[];
    bans: DraftBan[];
}

/**
 * Kompletter Draft-State
 */
export interface DraftState {
    team1: TeamDraft;
    team2: TeamDraft;
    myTeam?: 'team1' | 'team2';
    myRole?: Role;
    phase?: string;
}

/**
 * WebSocket Draft-Update Event
 */
export interface DraftUpdateEvent {
    success: boolean;
    draft: {
        team1_picks: DraftPick[];
        team2_picks: DraftPick[];
        team1_bans: DraftBan[];
        team2_bans: DraftBan[];
        myTeam?: number;
        myRole?: string;
    };
}

