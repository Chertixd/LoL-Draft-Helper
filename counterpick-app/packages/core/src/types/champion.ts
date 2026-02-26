/**
 * Champion-bezogene TypeScript-Types
 */

export interface Champion {
    id: string;
    key: string;
    name: string;
    title?: string;
}

export interface ChampionStats {
    championKey: string;
    role: string;
    patch: string;
    winrate: number;
    pickrate: number;
    banrate: number;
    games: number;
    wins: number;
    tier?: string;
    rank?: number;
}

export interface ChampionIconInfo {
    name: string;
    iconUrl: string;
    splashUrl?: string;
}

