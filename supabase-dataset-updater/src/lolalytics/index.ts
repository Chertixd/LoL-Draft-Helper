import { ChampionData } from "../models/ChampionData";
import { ChampionSynergyData } from "../models/ChampionSynergyData";
import { ChampionMatchupData } from "../models/ChampionMatchupData";
import { getRoleFromString, Role } from "../models/Role";
import {
    ChampionRoleData,
    defaultChampionRoleData,
} from "../models/ChampionRoleData";
import { LOLALYTICS_ROLES, LolalyticsRole } from "./roles";
import { getLolalyticsQwikChampion } from "./qwik";
import { getLolalyticsQwikChampion2 } from "./qwik-champion2";
import { RiotChampion } from "../riot";

export async function getChampionDataFromLolalytics(
    version: string,
    champion: RiotChampion
) {
    // Fan out to ALL five lanes explicitly. The previous version did one
    // un-laned request first and trusted `header.lane` to identify the
    // "main" role, but Lolalytics's default-lane heuristic occasionally
    // points at a lane the champion barely plays — when that happened
    // the dominant lane (e.g. Nautilus support) silently went through
    // the no-data branch on the next pass and never had its matchups
    // / synergies persisted, even though the data exists upstream.
    // Always asking for `?lane=<role>` for every role gives a
    // deterministic 5-row matrix per champion and lets `header.n === 0`
    // be the only signal we need for "this lane has no games."
    const rolePromises = LOLALYTICS_ROLES.map((role) =>
        Promise.all([
            getLolalyticsQwikChampion(version, champion.id, role),
            getLolalyticsQwikChampion2(version, champion.id, role),
        ])
    );
    const roleDataResults = await Promise.allSettled(rolePromises);

    // If every role fetch failed or returned an empty payload, the
    // champion isn't on this patch yet. Mirror the previous skill6
    // null-check semantics so the upsert loop in supabase-etl.ts gets
    // the same `undefined` it knows how to skip.
    const hasAnyUsableRole = roleDataResults.some(
        (r) =>
            r.status === "fulfilled" &&
            r.value[0]?.skill6 != null &&
            r.value[0].header.n > 0
    );
    if (!hasAnyUsableRole) {
        return undefined;
    }

    const roleData = roleDataResults.map((result, i) => {
        const role = LOLALYTICS_ROLES[i];
        if (result.status === "fulfilled") {
            return [role, result.value] as const;
        }
        console.log(
            `No data for ${champion.id} in role ${role}`,
            result.reason
        );
        return [role, undefined] as const;
    });

    const model: ChampionData = {
        ...champion,
        statsByRole: Object.fromEntries(
            roleData.map(([role, data]) => {
                if (!data || data[0].header.n === 0) {
                    return [getRoleFromString(role), defaultChampionRoleData()];
                }

                const [championData, champion2Data] = data;

                const championRoleData: ChampionRoleData = {
                    games: championData.header.n,
                    wins: Math.round(
                        (championData.header.n * championData.header.wr) / 100
                    ),
                    matchup: Object.fromEntries(
                        LOLALYTICS_ROLES.map((role) => {
                            const data = championData.enemy[role];
                            if (!data) {
                                console.log(championData);
                            }

                            return [
                                getRoleFromString(role),
                                Object.fromEntries(
                                    data.map((d) => {
                                        const [
                                            championKey,
                                            winRate,
                                            ,
                                            ,
                                            ,
                                            games,
                                        ] = d;
                                        const matchup: ChampionMatchupData = {
                                            championKey: championKey.toString(),
                                            games,
                                            wins: games * (winRate / 100),
                                        };

                                        return [d[0], matchup];
                                    })
                                ),
                            ];
                        })
                    ) as Record<Role, Record<string, ChampionMatchupData>>,
                    synergy: Object.fromEntries(
                        LOLALYTICS_ROLES.filter((r) => r !== role).map(
                            (synergyRole) => {
                                const data = champion2Data.team[synergyRole]!;

                                return [
                                    getRoleFromString(synergyRole),
                                    Object.fromEntries(
                                        data.map((d) => {
                                            const [
                                                championKey,
                                                winRate,
                                                ,
                                                ,
                                                ,
                                                games,
                                            ] = d;
                                            const synergy: ChampionSynergyData =
                                                {
                                                    championKey:
                                                        championKey.toString(),
                                                    games,
                                                    wins:
                                                        games * (winRate / 100),
                                                };

                                            return [d[0], synergy];
                                        })
                                    ),
                                ];
                            }
                        )
                    ) as Record<Role, Record<string, ChampionSynergyData>>,
                    damageProfile: championData.header.damage,
                    statsByTime: Array.from({ length: 5 }).map((_, i) => {
                        const t = championData.sidebar.time.time;
                        const tw = championData.sidebar.time.timeWin;
                        if (i === 0) {
                            return {
                                games: (t[1] ?? 0) + (t[2] ?? 0),
                                wins: (tw[1] ?? 0) + (tw[2] ?? 0),
                            };
                        } else if (i === 4) {
                            return {
                                games: (t[5] ?? 0) + (t[6] ?? 0),
                                wins: (tw[5] ?? 0) + (tw[6] ?? 0),
                            };
                        } else {
                            return {
                                games: t[i + 2] ?? 0,
                                wins: tw[i + 2] ?? 0,
                            };
                        }
                    }),
                };

                return [getRoleFromString(role), championRoleData];
            })
        ) as Record<Role, ChampionRoleData>,
    };

    return model;
}

