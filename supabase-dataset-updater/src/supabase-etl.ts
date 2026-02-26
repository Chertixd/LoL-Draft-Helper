import "dotenv/config";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import {
    getChampions,
    getItems,
    getRunes,
    getSummonerSpells,
    getVersions,
    RiotChampion,
    RiotItem,
    RiotRunePath,
    RiotSummonerSpell,
} from "./riot";
import { getChampionDataFromLolalytics } from "./lolalytics";
import { displayNameByRole, Role } from "./models/Role";

type DbClient = SupabaseClient;

type ChampionStatsRow = {
    patch: string;
    champion_key: string;
    role: string;
    games: number;
    wins: number;
    damage_profile: unknown;
    stats_by_time: unknown;
};

type MatchupRow = {
    patch: string;
    champion_key: string;
    role: string;
    opponent_key: string;
    opponent_role: string;
    games: number;
    wins: number;
};

type SynergyRow = {
    patch: string;
    champion_key: string;
    role: string;
    mate_key: string;
    mate_role: string;
    games: number;
    wins: number;
};

function envRequired(key: string) {
    const value = process.env[key];
    if (!value) {
        throw new Error(`${key} must be set`);
    }
    return value;
}

function normalizePatch(version: string) {
    return version.split(".").slice(0, 2).join(".");
}

async function upsert<T extends Record<string, unknown>>(
    supabase: DbClient,
    table: string,
    rows: T[]
) {
    if (!rows.length) return;
    const { error } = await supabase.from(table).upsert(rows);
    if (error) {
        throw error;
    }
}

async function upsertChampions(
    supabase: DbClient,
    champions: RiotChampion[],
    i18nMap: Record<string, RiotChampion | undefined>
) {
    const rows = champions.map((c) => ({
        key: c.key,
        name: c.name,
        i18n: {
            zh_CN: { name: i18nMap[c.key]?.name },
        },
    }));
    await upsert(supabase, "champions", rows);
}

async function upsertItems(
    supabase: DbClient,
    patch: string,
    items: Record<string, RiotItem>
) {
    const rows = Object.entries(items).map(([id, item]) => ({
        patch,
        item_id: parseInt(id, 10),
        name: item.name,
        gold: item.gold.total,
    }));
    await upsert(supabase, "items", rows);
}

async function upsertRunes(
    supabase: DbClient,
    patch: string,
    runes: RiotRunePath[]
) {
    const rows = runes
        .map((path) =>
            path.slots
                .map((slot) =>
                    slot.runes.map((rune) => ({
                        patch,
                        rune_id: rune.id,
                        data: {
                            id: rune.id,
                            key: rune.key,
                            name: rune.name,
                            icon: rune.icon,
                            pathId: path.id,
                        },
                    }))
                )
                .flat()
        )
        .flat();
    await upsert(supabase, "runes", rows);
}

async function upsertSummonerSpells(
    supabase: DbClient,
    patch: string,
    spells: Record<string, RiotSummonerSpell>
) {
    const rows = Object.values(spells).map((spell) => ({
        patch,
        spell_key: spell.key,
        name: spell.name,
    }));
    await upsert(supabase, "summoner_spells", rows);
}

function roleToName(role: Role) {
    return displayNameByRole[role].toLowerCase();
}

async function upsertChampionDataset(
    supabase: DbClient,
    patch: string,
    champion: RiotChampion
) {
    const championData = await getChampionDataFromLolalytics(patch, champion);
    if (!championData) {
        console.log(`No data for ${champion.name}`);
        return;
    }

    const statsRows: ChampionStatsRow[] = [];
    const matchupRows: MatchupRow[] = [];
    const synergyRows: SynergyRow[] = [];

    for (const [roleKey, roleStats] of Object.entries(
        championData.statsByRole
    )) {
        const role = Number(roleKey) as Role;
        const roleName = roleToName(role);

        statsRows.push({
            patch,
            champion_key: championData.key,
            role: roleName,
            games: Math.round(roleStats.games),
            wins: Math.round(roleStats.wins),
            damage_profile: roleStats.damageProfile,
            stats_by_time: roleStats.statsByTime,
        });

        for (const [opponentRoleKey, opponents] of Object.entries(
            roleStats.matchup
        )) {
            const opponentRoleName = roleToName(Number(opponentRoleKey) as Role);
            for (const [opponentKey, mu] of Object.entries(opponents)) {
                matchupRows.push({
                    patch,
                    champion_key: championData.key,
                    role: roleName,
                    opponent_key: opponentKey,
                    opponent_role: opponentRoleName,
                    games: Math.round(mu.games),
                    wins: Math.round(mu.wins),
                });
            }
        }

        for (const [mateRoleKey, mates] of Object.entries(roleStats.synergy)) {
            const mateRoleName = roleToName(Number(mateRoleKey) as Role);
            for (const [mateKey, syn] of Object.entries(mates)) {
                synergyRows.push({
                    patch,
                    champion_key: championData.key,
                    role: roleName,
                    mate_key: mateKey,
                    mate_role: mateRoleName,
                    games: Math.round(syn.games),
                    wins: Math.round(syn.wins),
                });
            }
        }
    }

    await upsert(supabase, "champion_stats", statsRows);
    await upsert(supabase, "matchups", matchupRows);
    await upsert(supabase, "synergies", synergyRows);
}

async function insertPatch(supabase: DbClient, patch: string) {
    const { error } = await supabase
        .from("patches")
        .upsert({ patch }, { onConflict: "patch" });
    if (error) {
        throw error;
    }
}

async function main() {
    const SUPABASE_URL = envRequired("SUPABASE_URL");
    const SUPABASE_SERVICE_ROLE_KEY = envRequired("SUPABASE_SERVICE_ROLE_KEY");

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    const [currentVersion] = await getVersions();
    const patch = normalizePatch(currentVersion);

    console.log("Patch:", patch);
    await insertPatch(supabase, patch);

    const [champions, championsZh, runes, items, summonerSpells] =
        await Promise.all([
            getChampions(currentVersion),
            getChampions(currentVersion, "zh_CN"),
            getRunes(currentVersion),
            getItems(currentVersion),
            getSummonerSpells(currentVersion),
        ]);

    const championByKey = Object.fromEntries(
        championsZh.map((c) => [c.key, c])
    ) as Record<string, RiotChampion>;

    await upsertChampions(supabase, champions, championByKey);
    await upsertItems(supabase, patch, items);
    await upsertRunes(supabase, patch, runes);
    await upsertSummonerSpells(supabase, patch, summonerSpells);

    const testChampionKeys =
        process.env.TEST_CHAMPIONS?.split(",")
            .map((c) => c.trim())
            .filter(Boolean) ?? [];

    const sampleChampionKeys =
        testChampionKeys.length > 0
            ? testChampionKeys
            : champions.map((c) => c.key);

    for (const championKey of sampleChampionKeys) {
        // Try to find by key (numeric), id (e.g. "Aatrox"), or name
        const champion = champions.find(
            (c) =>
                c.key === championKey ||
                c.id.toLowerCase() === championKey.toLowerCase() ||
                c.name.toLowerCase() === championKey.toLowerCase()
        );
        if (!champion) {
            console.log(`Champion with key/id/name "${championKey}" not found, skipping.`);
            continue;
        }
        console.log(`Processing ${champion.name} (key: ${champion.key})`);
        await upsertChampionDataset(supabase, patch, champion);
    }

    console.log("Done.");
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});

