import {
    getChampions,
    getItems,
    getRunes,
    getSummonerSpells,
    getVersions,
    RiotChampion,
} from "./riot";
import { getChampionDataFromLolalytics } from "./lolalytics";
import { displayNameByRole, Role } from "./models/Role";
import {
    ChampionRow,
    PatchRow,
    ItemRow,
    RuneRow,
    SummonerSpellRow,
    ChampionStatsRow,
    MatchupRow,
    SynergyRow,
} from "./models/Rows";
import { fetchPreviousPatchFiles } from "./cdn-fetcher";
import { writeOutputs, TableInputs, PreviousPatchBundle } from "./writer";

const CDN_BASE_URL =
    process.env.CDN_BASE_URL ??
    "https://chertixd.github.io/lol-draft-helper-cdn/data";

const OUT_DIR = process.env.ETL_OUT_DIR ?? "public/data";

function normalizePatch(version: string): string {
    return version.split(".").slice(0, 2).join(".");
}

function roleToName(role: Role): string {
    return displayNameByRole[role].toLowerCase();
}

async function main(): Promise<void> {
    // Step 1: Patch detection
    const versions = await getVersions();
    const currentVersion = versions[0];
    const previousVersion = versions[1];
    const currentPatch = normalizePatch(currentVersion);
    const previousPatch = previousVersion ? normalizePatch(previousVersion) : null;
    console.log(`[etl] current=${currentPatch}, previous=${previousPatch ?? "(none)"}`);

    // Step 2: Previous-patch restore from live CDN (soft-fail on 404)
    let previousFiles: PreviousPatchBundle | null = null;
    if (previousPatch) {
        const fetched = await fetchPreviousPatchFiles(CDN_BASE_URL, previousPatch);
        if (fetched !== null) {
            previousFiles = { patch: previousPatch, files: fetched };
            console.log(`[etl] restored previous patch ${previousPatch} from CDN`);
        } else {
            console.log(`[etl] previous patch ${previousPatch} not on CDN — skipping`);
        }
    }

    // Step 3 + 4: scrape Riot Data Dragon + Lolalytics
    const [champions, championsZh, runes, items, summonerSpells] = await Promise.all([
        getChampions(currentVersion),
        getChampions(currentVersion, "zh_CN"),
        getRunes(currentVersion),
        getItems(currentVersion),
        getSummonerSpells(currentVersion),
    ]);
    const championByKey = Object.fromEntries(championsZh.map((c) => [c.key, c])) as Record<
        string,
        RiotChampion
    >;

    const championRows: ChampionRow[] = champions.map((c) => ({
        key: c.key,
        name: c.name,
        i18n: { zh_CN: { name: championByKey[c.key]?.name } },
    }));

    const itemRows: ItemRow[] = Object.entries(items).map(([id, item]) => ({
        patch: currentPatch,
        item_id: parseInt(id, 10),
        name: item.name,
        gold: item.gold.total,
    }));

    const runeRows: RuneRow[] = runes.flatMap((path) =>
        path.slots.flatMap((slot) =>
            slot.runes.map((rune) => ({
                patch: currentPatch,
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
    );

    const summonerSpellRows: SummonerSpellRow[] = Object.values(summonerSpells).map((spell) => ({
        patch: currentPatch,
        spell_key: spell.key,
        name: spell.name,
    }));

    // Patches list reflects retention rule (current + optional previous).
    const patchRows: PatchRow[] = previousFiles
        ? [{ patch: currentPatch }, { patch: previousFiles.patch }]
        : [{ patch: currentPatch }];

    // Per-champion Lolalytics scrape (cartesian-fix preserved in lolalytics/index.ts)
    const championStatsRows: ChampionStatsRow[] = [];
    const matchupRows: MatchupRow[] = [];
    const synergyRows: SynergyRow[] = [];

    const testChampionKeys =
        process.env.TEST_CHAMPIONS?.split(",")
            .map((c) => c.trim())
            .filter(Boolean) ?? [];
    const sampleKeys =
        testChampionKeys.length > 0 ? testChampionKeys : champions.map((c) => c.key);

    for (const championKey of sampleKeys) {
        const champion = champions.find(
            (c) =>
                c.key === championKey ||
                c.id.toLowerCase() === championKey.toLowerCase() ||
                c.name.toLowerCase() === championKey.toLowerCase()
        );
        if (!champion) {
            console.log(`[etl] champion "${championKey}" not found, skipping`);
            continue;
        }
        console.log(`[etl] processing ${champion.name} (key=${champion.key})`);
        const championData = await getChampionDataFromLolalytics(currentVersion, champion as RiotChampion);
        if (!championData) {
            console.log(`[etl] no usable data for ${champion.name}`);
            continue;
        }

        for (const [roleKey, roleStats] of Object.entries(championData.statsByRole)) {
            const role = Number(roleKey) as Role;
            const roleName = roleToName(role);

            championStatsRows.push({
                patch: currentPatch,
                champion_key: championData.key,
                role: roleName,
                games: Math.round(roleStats.games),
                wins: Math.round(roleStats.wins),
                damage_profile: roleStats.damageProfile,
                stats_by_time: roleStats.statsByTime,
            });

            for (const [opponentRoleKey, opponents] of Object.entries(roleStats.matchup)) {
                const opponentRoleName = roleToName(Number(opponentRoleKey) as Role);
                for (const [opponentKey, mu] of Object.entries(opponents)) {
                    matchupRows.push({
                        patch: currentPatch,
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
                        patch: currentPatch,
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
    }

    // Step 5: canonical write
    const tables: TableInputs = {
        champions: championRows,
        patches: patchRows,
        items: itemRows,
        runes: runeRows,
        summoner_spells: summonerSpellRows,
        champion_stats: championStatsRows,
        matchups_current: matchupRows,
        synergies_current: synergyRows,
    };
    await writeOutputs(OUT_DIR, tables, currentPatch, previousFiles, new Date());
    console.log(`[etl] wrote outputs to ${OUT_DIR}`);
}

// Exported for the golden test to call deterministically. Direct CLI invocation
// guards on import.meta.url so import-side-effects don't auto-run main during tests.
export { main };

if (
    import.meta.url === `file://${process.argv[1]}` ||
    process.argv[1]?.endsWith("etl.ts") ||
    process.argv[1]?.endsWith("etl.js")
) {
    main().catch((err) => {
        console.error("[etl] FATAL:", err);
        process.exit(1);
    });
}
