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
    const [championData, champion2Data] = await Promise.all([
        getLolalyticsQwikChampion(version, champion.id),
        getLolalyticsQwikChampion2(version, champion.id),
    ]);

    // If data is not available, throw
    if (!championData.skill6) {
        return undefined;
        //throw new Error("No data available for this champion and patch");
    }

    const mainRole = championData.header.lane as LolalyticsRole;
    const remainingRoles = LOLALYTICS_ROLES.filter(
        (role) => role !== championData.header.lane
    );

    const rolePromises = remainingRoles.map((role) =>
        Promise.all([
            getLolalyticsQwikChampion(version, champion.id, role),
            getLolalyticsQwikChampion2(version, champion.id, role),
        ])
    );
    const roleDataResults = await Promise.allSettled(rolePromises);

    let roleData = roleDataResults.map((result, i) => {
        if (result.status === "fulfilled") {
            return [remainingRoles[i], result.value] as const;
        }

        console.log(
            `No data for ${champion.id} in role ${remainingRoles[i]}`,
            result.reason
        );

        return [remainingRoles[i], undefined] as const;
    });
    roleData = [[mainRole, [championData, champion2Data]], ...roleData];

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
                        if (i === 0) {
                            return {
                                games:
                                    championData.sidebar.time.time[1] +
                                    championData.sidebar.time.time[2],
                                wins:
                                    championData.sidebar.time.timeWin[1] +
                                    championData.sidebar.time.timeWin[2],
                            };
                        } else if (i === 4) {
                            return {
                                games:
                                    championData.sidebar.time.time[5] +
                                    championData.sidebar.time.time[6],
                                wins:
                                    championData.sidebar.time.timeWin[5] +
                                    championData.sidebar.time.timeWin[6],
                            };
                        } else {
                            return {
                                games: championData.sidebar.time.time[i + 2],
                                wins: championData.sidebar.time.timeWin[i + 2],
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

