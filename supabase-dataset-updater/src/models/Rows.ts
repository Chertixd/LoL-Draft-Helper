/**
 * Row shapes for the 8 logical tables produced by the ETL.
 *
 * Field names and types match what the Tauri client (json_repo.py) expects.
 * Any change here REQUIRES coordination with json_repo.py — the shapes are
 * coupled by the canonical sha256 hash.
 *
 * Source-of-truth field origins:
 *  - patch / champion_key / role / opponent_key / etc. — Lolalytics responses
 *  - games / wins — derived from Lolalytics with Math.round (integer values)
 */

export interface ChampionRow {
    key: string;
    name: string;
    i18n: { zh_CN: { name: string | undefined } };
}

export interface PatchRow {
    patch: string;
}

export interface ItemRow {
    patch: string;
    item_id: number;
    name: string;
    gold: number;
}

export interface RuneRow {
    patch: string;
    rune_id: number;
    data: {
        id: number;
        key: string;
        name: string;
        icon: string;
        pathId: number;
    };
}

export interface SummonerSpellRow {
    patch: string;
    spell_key: string;
    name: string;
}

export interface ChampionStatsRow {
    patch: string;
    champion_key: string;
    role: string;
    games: number;
    wins: number;
    damage_profile: unknown;
    stats_by_time: unknown;
}

export interface MatchupRow {
    patch: string;
    champion_key: string;
    role: string;
    opponent_key: string;
    opponent_role: string;
    games: number;
    wins: number;
}

export interface SynergyRow {
    patch: string;
    champion_key: string;
    role: string;
    mate_key: string;
    mate_role: string;
    games: number;
    wins: number;
}
