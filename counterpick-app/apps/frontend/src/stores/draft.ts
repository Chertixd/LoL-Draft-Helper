/**
 * Draft Store - Verwaltet Draft-Daten und WebSocket-Verbindung
 */
import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import { io, Socket } from 'socket.io-client';
import {
    getLeagueClientStatus,
    getRecommendations,
    setRoleOverride,
    getBatchRoleProbabilities
} from '@/api/backend';
import { getBackendURL } from '@/api/client';
import { useSettingsStore } from '@/stores/settings';
import type { 
    DraftPick, 
    DraftBan, 
    Role,
    RoleProbabilities,
    RoleLockType,
    RecommendationRequest,
    RecommendationItem,
    PickScore
} from '@counterpick/core';

export const useDraftStore = defineStore('draft', () => {
    // State
    const team1Picks = ref<DraftPick[]>([]);
    const team2Picks = ref<DraftPick[]>([]);
    const team1Bans = ref<DraftBan[]>([]);
    const team2Bans = ref<DraftBan[]>([]);
    
    const myTeam = ref<'team1' | 'team2' | null>(null);
    const myRole = ref<Role | null>(null);
    const manualRole = ref<Role | null>(null);  // Manuelle Rollen-Überschreibung
    
    const leagueClientConnected = ref(false);
    const websocketConnected = ref(false);
    const isLoading = ref(false);
    const error = ref<string | null>(null);
    
    // Recommendations
    const recommendations = ref<RecommendationItem[]>([]);
    const recommendationsLoading = ref(false);
    const recommendationsError = ref<string | null>(null);
    
    // Pick Scores - Scores für bereits gepickte Champions
    const pickScores = ref<Record<string, PickScore>>({});
    
    // Draft-Zusammenfassung nach vollständigem Draft
    interface DraftSummary {
        myTeamSide: 'blue' | 'red';
        myTeamPicks: DraftPick[];
        enemyTeamPicks: DraftPick[];
        pickScores: Record<string, PickScore>;
        timestamp: number;
        myTeamTotalScore: number;
        enemyTeamTotalScore: number;
        scoreDifference: number;
    }
    
    const lastCompletedDraft = ref<DraftSummary | null>(null);
    const showDraftSummary = ref(true);
    
    // Manuelle Rollen-Overrides pro Pick (cellId -> Role)
    // Erlaubt das manuelle Überschreiben der automatisch erkannten Rolle
    const manualRoleOverrides = ref<Map<number, Role>>(new Map());
    
    // Cache für Rollen-Wahrscheinlichkeiten (Champion-Name -> Probabilities)
    const roleProbabilitiesCache = ref<Map<string, {
        probabilities: RoleProbabilities;
        totalGames: number;
        timestamp: number;
    }>>(new Map());
    
    // Cache TTL: 1 Stunde
    const CACHE_TTL = 60 * 60 * 1000;
    
    // WebSocket
    let socket: Socket | null = null;
    
    // Debounce für Recommendations
    let recommendationsDebounceTimer: ReturnType<typeof setTimeout> | null = null;
    let pendingRecommendationsRequest = false;

    // Getters
    const effectiveRole = computed(() => manualRole.value || myRole.value);
    
    const isInDraft = computed(() => myTeam.value !== null);
    
    const hasAnyPicks = computed(() => 
        team1Picks.value.some(p => p.isLocked) || team2Picks.value.some(p => p.isLocked)
    );

    const myTeamPicks = computed(() => 
        myTeam.value === 'team1' ? team1Picks.value : team2Picks.value
    );

    const enemyTeamPicks = computed(() => 
        myTeam.value === 'team1' ? team2Picks.value : team1Picks.value
    );

    const myTeamBans = computed(() => 
        myTeam.value === 'team1' ? team1Bans.value : team2Bans.value
    );

    const enemyTeamBans = computed(() => 
        myTeam.value === 'team1' ? team2Bans.value : team1Bans.value
    );

    /**
     * Prüft ob im eigenen Team bereits ein Champion für die ausgewählte Rolle gepickt wurde
     */
    const myTeamPickedForRole = computed(() => {
        if (!effectiveRole.value) return false;
        
        return myTeamPicks.value.some(pick => 
            pick.isLocked && 
            pick.champion && 
            pick.role === effectiveRole.value
        );
    });

    /**
     * Prüft ob im gegnerischen Team bereits ein Champion für die ausgewählte Rolle gepickt wurde
     */
    const enemyTeamPickedForRole = computed(() => {
        if (!effectiveRole.value) return false;
        
        return enemyTeamPicks.value.some(pick => 
            pick.isLocked && 
            pick.champion && 
            pick.role === effectiveRole.value
        );
    });

    /**
     * Prüft ob bereits in BEIDEN Teams für die ausgewählte Rolle gepickt wurde
     * Gibt true zurück nur wenn sowohl eigenes als auch gegnerisches Team die Rolle gepickt haben
     */
    const alreadyPickedForRole = computed(() => {
        if (!effectiveRole.value) return false;
        
        return myTeamPickedForRole.value && enemyTeamPickedForRole.value;
    });

    /**
     * Gibt den Champion zurück, der die ausgewählte Rolle im eigenen Team hat
     */
    const myRoleChampion = computed(() => {
        if (!effectiveRole.value) return null;
        
        const pick = myTeamPicks.value.find(p => 
            p.isLocked && 
            p.champion && 
            p.role === effectiveRole.value
        );
        
        return pick?.champion || null;
    });

    /**
     * Gibt den Champion zurück, der die ausgewählte Rolle im gegnerischen Team hat
     */
    const enemyRoleChampion = computed(() => {
        if (!effectiveRole.value) return null;
        
        const pick = enemyTeamPicks.value.find(p => 
            p.isLocked && 
            p.champion && 
            p.role === effectiveRole.value
        );
        
        return pick?.champion || null;
    });

    /**
     * Prüft ob Recommendations geladen werden sollten
     * true wenn: Rolle ausgewählt UND noch nicht für diese Rolle in BEIDEN Teams gepickt
     */
    const shouldLoadRecommendations = computed(() => 
        effectiveRole.value !== null && !alreadyPickedForRole.value
    );

    // Polling-Interval für League Client Status
    let statusPollingInterval: ReturnType<typeof setInterval> | null = null;
    let isCheckingStatus = false; // Verhindert mehrfache gleichzeitige Anfragen

    // Actions
    async function checkLeagueClientStatus() {
        // Verhindere mehrfache gleichzeitige Anfragen
        if (isCheckingStatus) return leagueClientConnected.value;
        
        isCheckingStatus = true;
        try {
            const response = await getLeagueClientStatus();
            leagueClientConnected.value = response.client_running;
            return response.client_running;
        } catch (e) {
            // Bei Fehler nicht sofort auf false setzen (Backend könnte kurz nicht erreichbar sein)
            console.warn('[Draft] Fehler beim Prüfen des League Client Status:', e);
            return leagueClientConnected.value;
        } finally {
            isCheckingStatus = false;
        }
    }

    /**
     * Startet regelmäßiges Polling des League Client Status
     * Standard: alle 10 Sekunden (nicht zu aggressiv)
     */
    function startStatusPolling(intervalMs = 10000) {
        if (statusPollingInterval) return;
        
        // Dann regelmäßig (nicht sofort, um doppelte Anfragen zu vermeiden)
        statusPollingInterval = setInterval(() => {
            checkLeagueClientStatus();
        }, intervalMs);
    }

    /**
     * Stoppt das Status-Polling
     */
    function stopStatusPolling() {
        if (statusPollingInterval) {
            clearInterval(statusPollingInterval);
            statusPollingInterval = null;
        }
    }

    async function connectWebSocket() {
        if (socket?.connected) return;

        const baseURL = await getBackendURL()
        // In browser dev mode, baseURL is '' — fall back to localhost:5000
        // for Socket.IO which needs an absolute URL (not the Vite proxy)
        const socketURL = baseURL || 'http://localhost:5000'

        socket = io(socketURL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionAttempts: 10
        });

        socket.on('connect', () => {
            console.log('[WebSocket] Verbunden');
            websocketConnected.value = true;
            // Prüfe einmal den League Client Status nach Verbindung
            checkLeagueClientStatus();
            // Starte Polling alle 10 Sekunden
            startStatusPolling(10000);
        });

        socket.on('disconnect', () => {
            console.log('[WebSocket] Getrennt');
            websocketConnected.value = false;
            stopStatusPolling();
        });

        socket.on('connect_error', (err) => {
            console.error('[WebSocket] Verbindungsfehler:', err);
            // Nicht sofort auf false setzen - könnte ein temporärer Fehler sein
        });

        socket.on('draft_update', (data) => {
            console.log('[WebSocket] Draft Update:', data);
            // Bei Draft-Update ist der Client definitiv verbunden
            leagueClientConnected.value = true;
            if (data?.draft) {
                updateDraftState(data.draft);
            }
        });
        
        // Draft-Reset Event (wenn Draft endet oder abgebrochen wird)
        socket.on('draft_reset', (data) => {
            console.log('[WebSocket] Draft Reset:', data);
            
            // Prüfe ob Draft vollständig war und noch keine Zusammenfassung existiert
            // (Zusammenfassung wird bereits in updateDraftState gespeichert wenn alle 10 Picks da sind)
            if (isDraftComplete() && !lastCompletedDraft.value) {
                saveDraftSummary();
                showDraftSummary.value = true;
            }
            
            clearDraft();
        });
        
        // Zusätzliche Events vom Backend
        socket.on('client_status', (data) => {
            console.log('[WebSocket] Client Status:', data);
            if (data && typeof data.connected === 'boolean') {
                leagueClientConnected.value = data.connected;
            }
        });
    }

    function disconnectWebSocket() {
        stopStatusPolling();
        if (socket) {
            socket.disconnect();
            socket = null;
            websocketConnected.value = false;
        }
    }

    /**
     * Konvertiert LCU assignedPosition zu normalisierten Rollen
     */
    function normalizeAssignedPosition(position: string): string {
        const mapping: Record<string, string> = {
            'TOP': 'top',
            'JUNGLE': 'jungle',
            'MIDDLE': 'middle',
            'BOTTOM': 'bottom',
            'UTILITY': 'support',
            'top': 'top',
            'jungle': 'jungle',
            'middle': 'middle',
            'bottom': 'bottom',
            'utility': 'support',  // Lowercase variant von UTILITY
            'support': 'support'
        };
        return mapping[position] || position?.toLowerCase() || 'middle';
    }

    /**
     * Ermittelt die finale Rolle für einen Pick (alte Version - wird durch recalculateRoleAssignments ersetzt)
     * Priorität: manualRole > predictedRole > normalizeAssignedPosition
     */
    function getFinalRole(cellId: number, predictedRole: string | undefined, assignedPosition: string): Role | undefined {
        // 1. Prüfe manuelle Override
        const manualOverride = manualRoleOverrides.value.get(cellId);
        if (manualOverride) {
            return manualOverride;
        }
        
        // 2. Nutze predicted Role vom Backend
        if (predictedRole && ['top', 'jungle', 'middle', 'bottom', 'support'].includes(predictedRole)) {
            return predictedRole as Role;
        }
        
        // 3. Fallback zu normalisierter assignedPosition
        const normalized = normalizeAssignedPosition(assignedPosition);
        if (normalized && ['top', 'jungle', 'middle', 'bottom', 'support'].includes(normalized)) {
            return normalized as Role;
        }
        
        return undefined;
    }

    /**
     * Lädt Rollen-Wahrscheinlichkeiten für mehrere Champions
     * Nutzt Cache und Batch-API für Effizienz
     */
    async function loadRoleProbabilities(champions: string[]): Promise<Map<string, RoleProbabilities>> {
        const results = new Map<string, RoleProbabilities>();
        const now = Date.now();
        const championsToFetch: string[] = [];
        
        // Hole currentPatch aus Settings Store
        const settingsStore = useSettingsStore();
        const patch = settingsStore.currentPatch || 'latest';
        
        // Prüfe Cache für jeden Champion (mit Patch-spezifischem Key)
        for (const champion of champions) {
            if (!champion) continue;
            
            const cacheKey = `${champion}:${patch}`;
            const cached = roleProbabilitiesCache.value.get(cacheKey);
            if (cached && (now - cached.timestamp) < CACHE_TTL) {
                results.set(champion, cached.probabilities);
            } else {
                championsToFetch.push(champion);
            }
        }
        
        // Lade fehlende Wahrscheinlichkeiten
        if (championsToFetch.length > 0) {
            try {
                const response = await getBatchRoleProbabilities(championsToFetch, patch || undefined);
                
                if (response.success && response.results) {
                    for (const [champion, data] of Object.entries(response.results)) {
                        if (data.probabilities) {
                            const probs: RoleProbabilities = {
                                top: data.probabilities.top ?? 0.2,
                                jungle: data.probabilities.jungle ?? 0.2,
                                middle: data.probabilities.middle ?? 0.2,
                                bottom: data.probabilities.bottom ?? 0.2,
                                support: data.probabilities.support ?? 0.2
                            };
                            
                            results.set(champion, probs);
                            
                            // Cache speichern mit Patch-spezifischem Key
                            const cacheKey = `${champion}:${patch}`;
                            roleProbabilitiesCache.value.set(cacheKey, {
                                probabilities: probs,
                                totalGames: data.totalGames ?? 0,
                                timestamp: now
                            });
                        }
                    }
                }
            } catch (e) {
                console.error('[Draft] Fehler beim Laden der Rollen-Wahrscheinlichkeiten:', e);
            }
        }
        
        return results;
    }

    /**
     * Berechnet die Lock-Priorität für einen Pick
     * Höhere Werte = höhere Priorität
     */
    function getLockPriority(pick: DraftPick, isMyTeam: boolean): number {
        // Auto-Lock (LCU assignedPosition) für eigenes Team: Höchste Priorität
        if (isMyTeam && pick.assignedPosition && pick.roleLockType === 'auto') {
            return 1000;
        }
        
        // High-Confidence Prediction (> 0.7 und viele Games)
        if (pick.roleLockType === 'prediction' && pick.roleConfidence && pick.roleConfidence > 0.7) {
            // Bonus für viele Spiele (max +50 bei 50000+ Spielen)
            const gamesBonus = Math.min(50, (pick.totalGames ?? 0) / 1000);
            return 500 + (pick.roleConfidence * 100) + gamesBonus;
        }
        
        // Manual Lock
        if (pick.roleLockType === 'manual') {
            return 300;
        }
        
        // Low-Confidence Prediction
        if (pick.roleLockType === 'prediction' && pick.roleConfidence) {
            return 100 + (pick.roleConfidence * 100);
        }
        
        return 0;
    }

    /**
     * Löst einen Rollenkonflikt zwischen zwei Picks
     * Gibt den Gewinner zurück
     */
    function resolveConflict(newPick: DraftPick, existingPick: DraftPick, isMyTeam: boolean): DraftPick {
        const newPriority = getLockPriority(newPick, isMyTeam);
        const existingPriority = getLockPriority(existingPick, isMyTeam);
        
        // Höhere Priorität gewinnt
        if (newPriority > existingPriority) {
            return newPick;
        }
        
        // Bei gleicher Priorität: Höhere Confidence gewinnt
        if (newPriority === existingPriority) {
            if (newPick.roleConfidence && existingPick.roleConfidence) {
                return newPick.roleConfidence > existingPick.roleConfidence ? newPick : existingPick;
            }
            // Neuer Pick gewinnt bei gleicher Priorität (neuere Daten)
            return newPick;
        }
        
        return existingPick;
    }

    /**
     * Berechnet Rollen-Zuweisungen für ein Team neu
     * Implementiert das Prioritätssystem mit Konfliktlösung
     */
    function recalculateRoleAssignments(
        teamPicks: DraftPick[],
        isMyTeam: boolean,
        probabilities: Map<string, RoleProbabilities>
    ): DraftPick[] {
        // Kopiere Picks für Mutation
        const picks = teamPicks.map(p => ({ ...p }));
        
        // 1. Setze roleProbabilities und initiale roleLockType
        for (const pick of picks) {
            if (pick.champion && pick.isLocked) {
                const probs = probabilities.get(pick.champion);
                if (probs) {
                    pick.roleProbabilities = probs;
                }
                
                // Bestimme Lock-Typ
                const manualOverride = manualRoleOverrides.value.get(pick.cellId ?? -1);
                if (manualOverride) {
                    pick.roleLockType = 'manual';
                    pick.role = manualOverride;
                    pick.roleConfidence = 1.0;
                } else if (isMyTeam && pick.assignedPosition) {
                    // Auto-Lock für eigenes Team basierend auf LCU
                    pick.roleLockType = 'auto';
                    pick.role = normalizeAssignedPosition(pick.assignedPosition) as Role;
                    pick.roleConfidence = 1.0;
                } else if (probs) {
                    // Prediction basierend auf Statistiken
                    pick.roleLockType = 'prediction';
                    // Finde Rolle mit höchster Wahrscheinlichkeit
                    const sortedRoles = (Object.entries(probs) as [Role, number][])
                        .sort(([, a], [, b]) => b - a);
                    if (sortedRoles.length > 0) {
                        pick.role = sortedRoles[0][0];
                        pick.roleConfidence = sortedRoles[0][1];
                    }
                } else {
                    pick.roleLockType = 'none';
                }
            } else {
                pick.roleLockType = 'none';
            }
        }
        
        // 2. Sortiere Picks nach Priorität
        const lockedPicks = picks
            .filter(p => p.champion && p.isLocked)
            .sort((a, b) => getLockPriority(b, isMyTeam) - getLockPriority(a, isMyTeam));
        
        // 3. Role-Map für Konfliktauflösung
        const roleMap = new Map<Role, DraftPick>();
        const unassignedPicks: DraftPick[] = [];
        
        // 4. Iteriere durch sortierte Picks
        for (const pick of lockedPicks) {
            const desiredRole = pick.role;
            
            if (!desiredRole) {
                unassignedPicks.push(pick);
                continue;
            }
            
            const existingPick = roleMap.get(desiredRole);
            
            if (!existingPick) {
                roleMap.set(desiredRole, pick);
            } else {
                // Konflikt! Prüfe wer gewinnt
                const winner = resolveConflict(pick, existingPick, isMyTeam);
                
                if (winner === pick) {
                    roleMap.set(desiredRole, pick);
                    existingPick.role = undefined;
                    existingPick.roleLockType = 'none';
                    unassignedPicks.push(existingPick);
                } else {
                    unassignedPicks.push(pick);
                }
            }
        }
        
        // 5. Versuche unassigned Picks zuzuweisen
        for (const pick of unassignedPicks) {
            if (!pick.roleProbabilities) continue;
            
            const sortedRoles = (Object.entries(pick.roleProbabilities) as [Role, number][])
                .sort(([, a], [, b]) => b - a);
            
            for (const [role, prob] of sortedRoles) {
                if (!roleMap.has(role)) {
                    roleMap.set(role, pick);
                    pick.role = role;
                    pick.roleLockType = 'prediction';
                    pick.roleConfidence = prob;
                    break;
                }
            }
        }
        
        return picks;
    }

    /**
     * Gibt alle gelockten Rollen für ein Team zurück
     */
    function getLockedRolesForTeam(team: 'team1' | 'team2'): Map<Role, DraftPick> {
        const teamPicks = team === 'team1' ? team1Picks.value : team2Picks.value;
        const lockedRoles = new Map<Role, DraftPick>();
        
        for (const pick of teamPicks) {
            if (pick.role && pick.isLocked && pick.roleLockType !== 'none') {
                lockedRoles.set(pick.role, pick);
            }
        }
        
        return lockedRoles;
    }

    /**
     * Prüft ob eine Rolle für einen bestimmten Pick verfügbar ist
     */
    function isRoleAvailableForPick(role: Role, cellId: number, team: 'team1' | 'team2'): boolean {
        const lockedRoles = getLockedRolesForTeam(team);
        const existingPick = lockedRoles.get(role);
        
        // Rolle ist verfügbar wenn:
        // 1. Niemand sie hat
        // 2. Der aktuelle Pick sie selbst hat
        return !existingPick || existingPick.cellId === cellId;
    }

    /**
     * Gibt den Champion zurück, der eine Rolle im Team belegt
     */
    function getChampionWithRole(role: Role, team: 'team1' | 'team2'): string | null {
        const lockedRoles = getLockedRolesForTeam(team);
        const pick = lockedRoles.get(role);
        return pick?.champion || null;
    }

    async function updateDraftState(draft: any) {
        // Speichere alte locked-pick Anzahl für Vergleich
        const oldLockedCount = 
            team1Picks.value.filter(p => p.isLocked).length + 
            team2Picks.value.filter(p => p.isLocked).length;
        
        // My Team & Role zuerst setzen (für isMyTeam-Prüfung)
        if (draft.myTeam !== undefined) {
            myTeam.value = draft.myTeam === 0 ? 'team1' : 'team2';
        } else {
            // Fallback: Wenn myTeam nicht gesetzt ist, nehme team1 als Standard
            // team1_picks ist immer myTeam aus der LCU Session
            console.warn('[Draft] myTeam nicht im draft_data gefunden, verwende team1 als Fallback');
            myTeam.value = 'team1';
        }
        if (draft.myRole) {
            myRole.value = draft.myRole as Role;
        }
        
        // Temporäre Arrays für Picks erstellen
        let tempTeam1Picks: DraftPick[] = [];
        let tempTeam2Picks: DraftPick[] = [];
        
        // Team 1 Picks - Initiale Verarbeitung
        if (draft.team1_picks) {
            tempTeam1Picks = draft.team1_picks.map((p: any) => {
                const cellId = p.cellId || 0;
                const predictedRole = p.role || normalizeAssignedPosition(p.assignedPosition || '');
                
                return {
                    champion: p.champion || '',
                    championId: p.championId,
                    role: undefined, // Wird von recalculateRoleAssignments gesetzt
                    predictedRole: predictedRole as Role | undefined,
                    assignedPosition: p.assignedPosition,
                    cellId: cellId,
                    isLocked: p.isLocked || false,
                    hoverChampion: p.hoverChampion,
                    roleLockType: 'none' as RoleLockType,
                    roleConfidence: undefined,
                    roleProbabilities: undefined,
                    totalGames: undefined
                };
            });
        }

        // Team 2 Picks - Initiale Verarbeitung
        if (draft.team2_picks) {
            tempTeam2Picks = draft.team2_picks.map((p: any) => {
                const cellId = p.cellId || 0;
                const predictedRole = p.role || normalizeAssignedPosition(p.assignedPosition || '');
                
                return {
                    champion: p.champion || '',
                    championId: p.championId,
                    role: undefined, // Wird von recalculateRoleAssignments gesetzt
                    predictedRole: predictedRole as Role | undefined,
                    assignedPosition: p.assignedPosition,
                    cellId: cellId,
                    isLocked: p.isLocked || false,
                    hoverChampion: p.hoverChampion,
                    roleLockType: 'none' as RoleLockType,
                    roleConfidence: undefined,
                    roleProbabilities: undefined,
                    totalGames: undefined
                };
            });
        }
        
        // Sammle alle Champions für Batch-Abruf der Wahrscheinlichkeiten
        const allChampions: string[] = [];
        for (const pick of [...tempTeam1Picks, ...tempTeam2Picks]) {
            if (pick.champion && pick.isLocked) {
                allChampions.push(pick.champion);
            }
        }
        
        // Lade Rollen-Wahrscheinlichkeiten (async, aber wir warten darauf)
        let probabilities = new Map<string, RoleProbabilities>();
        if (allChampions.length > 0) {
            probabilities = await loadRoleProbabilities(allChampions);
        }
        
        // Wende Smart Role Assignment an
        const isTeam1MyTeam = myTeam.value === 'team1';
        
        if (tempTeam1Picks.length > 0) {
            team1Picks.value = recalculateRoleAssignments(tempTeam1Picks, isTeam1MyTeam, probabilities);
        }
        
        if (tempTeam2Picks.length > 0) {
            team2Picks.value = recalculateRoleAssignments(tempTeam2Picks, !isTeam1MyTeam, probabilities);
        }

        // Bans
        if (draft.team1_bans) {
            team1Bans.value = draft.team1_bans;
        }
        if (draft.team2_bans) {
            team2Bans.value = draft.team2_bans;
        }

        // Berechne neue locked-pick Anzahl
        const newLockedCount = 
            team1Picks.value.filter(p => p.isLocked).length + 
            team2Picks.value.filter(p => p.isLocked).length;
        
        // Debug: Zeige Locked Counts
        const team1LockedCount = team1Picks.value.filter(p => p.isLocked && p.champion).length;
        const team2LockedCount = team2Picks.value.filter(p => p.isLocked && p.champion).length;
        console.log('[Draft] Locked Counts:', { 
            team1: team1LockedCount, 
            team2: team2LockedCount, 
            total: newLockedCount,
            isComplete: isDraftComplete() 
        });
        
        // Lade Recommendations neu wenn:
        // 1. Sich die Anzahl der locked picks geändert hat (neuer Pick)
        // 2. Oder es den ersten Pick gibt und noch keine Scores geladen wurden
        const shouldRefresh = 
            (newLockedCount !== oldLockedCount) ||
            (newLockedCount > 0 && Object.keys(pickScores.value).length === 0);
        
        if (shouldRefresh) {
            console.log(`[Draft] Picks geändert: ${oldLockedCount} -> ${newLockedCount}, lade Scores neu`);
            debouncedLoadRecommendations();
        }
        
        // Prüfe ob Draft jetzt vollständig ist (alle 10 Picks)
        // Zeige Zusammenfassung sofort an, nicht erst bei Game-Start
        if (isDraftComplete() && !lastCompletedDraft.value) {
            console.log('[Draft] Alle 10 Picks gelockt - speichere Zusammenfassung');
            saveDraftSummary();
            showDraftSummary.value = true;
        } else if (isDraftComplete() && lastCompletedDraft.value) {
            console.log('[Draft] Draft vollständig, aber Zusammenfassung existiert bereits');
        }
    }

    /**
     * Debounced Version von loadRecommendations
     * Verhindert zu viele gleichzeitige Requests bei schnellen Draft-Updates
     */
    function debouncedLoadRecommendations(delayMs = 300) {
        // Wenn bereits ein Request pending ist, nur den Timer resetten
        if (recommendationsDebounceTimer) {
            clearTimeout(recommendationsDebounceTimer);
        }
        
        // Wenn bereits ein Request läuft, markiere dass ein neuer nötig ist
        if (recommendationsLoading.value) {
            pendingRecommendationsRequest = true;
            return;
        }
        
        recommendationsDebounceTimer = setTimeout(() => {
            loadRecommendations();
            recommendationsDebounceTimer = null;
        }, delayMs);
    }

    async function setManualRole(role: Role | null) {
        manualRole.value = role;
        
        // Sync mit Backend
        try {
            await setRoleOverride(role);
            // Recommendations neu laden (sofort, ohne Debounce)
            if (hasAnyPicks.value) {
                await loadRecommendations();
            }
        } catch (e) {
            console.error('[Draft] Fehler beim Setzen der Rolle:', e);
        }
    }

    async function loadRecommendations() {
        // Prüfe ob eine Rolle ausgewählt ist
        // AUSNAHME: Wenn Draft vollständig ist, lade trotzdem Scores
        const draftComplete = isDraftComplete();
        if (!effectiveRole.value && !draftComplete) {
            recommendations.value = [];
            recommendationsError.value = 'no_role';
            console.log('[Draft] Keine Rolle ausgewählt, überspringe Empfehlungen');
            return;
        }
        
        // Prüfe ob bereits für die Rolle gepickt wurde
        // ABER: Wenn Draft vollständig ist, trotzdem Scores laden für die Zusammenfassung
        if (alreadyPickedForRole.value && !draftComplete) {
            recommendations.value = [];
            recommendationsError.value = 'already_picked';
            console.log('[Draft] Bereits für Rolle gepickt:', effectiveRole.value, {
                myTeamPicked: myTeamPickedForRole.value,
                enemyTeamPicked: enemyTeamPickedForRole.value
            });
            return;
        }

        recommendationsLoading.value = true;
        recommendationsError.value = null;

        try {
            // Bereite Request vor - auch gehoverte Champions einbeziehen
            const myTeamData = myTeamPicks.value
                .filter(p => (p.isLocked && p.champion) || (p.hoverChampion && !p.isLocked))
                .map(p => ({
                    championKey: p.isLocked ? p.champion : p.hoverChampion!,
                    role: p.role || 'middle',
                    isHovered: !p.isLocked && !!p.hoverChampion  // Flag für gehoverte Champions
                }));

            const enemyTeamData = enemyTeamPicks.value
                .filter(p => p.isLocked && p.champion)
                .map(p => ({
                    championKey: p.champion,
                    role: p.role || 'middle'
                }));

            console.log('[Draft] Lade Empfehlungen:', {
                role: effectiveRole.value,
                myTeam: myTeamData,
                enemyTeam: enemyTeamData,
                isBlindPick: enemyTeamData.length === 0,
                myTeamPicksCount: myTeamPicks.value.length,
                enemyTeamPicksCount: enemyTeamPicks.value.length,
                myTeamValue: myTeam.value
            });

            // Auch bei Blind Pick (keine Picks) Empfehlungen laden
            // Backend gibt dann nur Base-Score zurück (Counter = 50, Synergy = 50 wenn keine Teammates)
            // Bei vollständigem Draft ohne Rolle: Verwende 'middle' als Fallback für pickScores
            const roleForRequest = effectiveRole.value || 'middle';
            
            // Hole currentPatch aus Settings Store
            const settingsStore = useSettingsStore();
            const patch = settingsStore.currentPatch || undefined;
            
            const request: RecommendationRequest = {
                myRole: roleForRequest,
                myTeam: myTeamData,
                enemyTeam: enemyTeamData,
                patch: patch,
                isBlindPick: enemyTeamData.length === 0  // Blind Pick wenn keine Gegner-Picks
            };

            const response = await getRecommendations(request);

            console.log('[Draft] Backend-Antwort:', {
                success: response.success,
                recommendationsCount: response.recommendations?.length || 0,
                error: response.error,
                firstThree: response.recommendations?.slice(0, 3)?.map(r => ({ 
                    name: r.championKey, 
                    score: r.score 
                }))
            });

            if (response.success) {
                recommendations.value = response.recommendations || [];
                
                if (recommendations.value.length === 0) {
                    console.warn('[Draft] Backend gab leere Liste zurück trotz success=true');
                    recommendationsError.value = 'Keine Empfehlungen verfügbar';
                } else {
                    console.log('[Draft] Empfehlungen erfolgreich geladen:', recommendations.value.length);
                }
                
                // Extrahiere Pick Scores für gepickte Champions
                if (response.pickScores) {
                    pickScores.value = response.pickScores;
                    console.log('[Draft] Erhaltene pickScores:', response.pickScores);
                    console.log('[Draft] myTeamPicks Champions:', myTeamPicks.value.map(p => p.champion));
                    console.log('[Draft] enemyTeamPicks Champions:', enemyTeamPicks.value.map(p => p.champion));
                    
                    // Aktualisiere Zusammenfassung falls Draft vollständig und bereits gespeichert
                    if (isDraftComplete() && lastCompletedDraft.value) {
                        console.log('[Draft] Aktualisiere Zusammenfassung mit neuen Scores');
                        saveDraftSummary();
                    }
                }
            } else {
                recommendationsError.value = response.error || 'Fehler beim Laden';
                console.error('[Draft] Backend-Fehler:', response.error);
            }
        } catch (e) {
            recommendationsError.value = e instanceof Error ? e.message : 'Unbekannter Fehler';
            console.error('[Draft] Exception beim Laden der Recommendations:', e);
        } finally {
            recommendationsLoading.value = false;
            
            // Prüfe ob während des Requests ein neuer angefordert wurde
            if (pendingRecommendationsRequest) {
                pendingRecommendationsRequest = false;
                debouncedLoadRecommendations(100); // Kürzerer Delay für wartende Requests
            }
        }
    }

    function clearDraft() {
        team1Picks.value = [];
        team2Picks.value = [];
        team1Bans.value = [];
        team2Bans.value = [];
        recommendations.value = [];
        pickScores.value = {};
        myTeam.value = null;
        myRole.value = null;
        manualRoleOverrides.value.clear();
    }
    
    /**
     * Prüft ob der Draft vollständig ist (alle 10 Picks gelockt)
     */
    function isDraftComplete(): boolean {
        const team1LockedCount = team1Picks.value.filter(p => p.isLocked && p.champion).length;
        const team2LockedCount = team2Picks.value.filter(p => p.isLocked && p.champion).length;
        return team1LockedCount === 5 && team2LockedCount === 5;
    }
    
    /**
     * Speichert den vollständigen Draft als Zusammenfassung
     */
    function saveDraftSummary() {
        if (!myTeam.value) return;
        
        const myPicks = myTeamPicks.value.filter(p => p.isLocked && p.champion);
        const enemyPicks = enemyTeamPicks.value.filter(p => p.isLocked && p.champion);
        
        // Berechne Team-Scores
        let myTeamTotal = 0;
        let enemyTeamTotal = 0;
        
        for (const pick of myPicks) {
            const score = pickScores.value[pick.champion];
            if (score) {
                myTeamTotal += score.score;
            }
        }
        
        for (const pick of enemyPicks) {
            const score = pickScores.value[pick.champion];
            if (score) {
                enemyTeamTotal += score.score;
            }
        }
        
        lastCompletedDraft.value = {
            myTeamSide: myTeam.value === 'team1' ? 'blue' : 'red',
            myTeamPicks: [...myTeamPicks.value],
            enemyTeamPicks: [...enemyTeamPicks.value],
            pickScores: { ...pickScores.value },
            timestamp: Date.now(),
            myTeamTotalScore: myTeamTotal,
            enemyTeamTotalScore: enemyTeamTotal,
            scoreDifference: myTeamTotal - enemyTeamTotal
        };
        
        console.log('[Draft] Vollständiger Draft gespeichert:', {
            myTeamScore: myTeamTotal,
            enemyTeamScore: enemyTeamTotal,
            difference: myTeamTotal - enemyTeamTotal
        });
    }
    
    /**
     * Schließt die Draft-Zusammenfassung
     */
    function closeDraftSummary() {
        showDraftSummary.value = false;
    }
    
    /**
     * Holt den Pick-Score für einen Champion
     */
    function getPickScore(championName: string): PickScore | null {
        return pickScores.value[championName] || null;
    }

    /**
     * Setzt eine manuelle Rollen-Überschreibung für einen Pick
     * Löst Konflikte mit anderen Picks auf (Kick-out Prinzip)
     * @param cellId - Die CellId des Picks
     * @param role - Die Rolle oder null zum Entfernen der Überschreibung
     */
    async function setManualRoleForPick(cellId: number, role: Role | null) {
        if (role === null) {
            // Entferne manuelle Überschreibung
            manualRoleOverrides.value.delete(cellId);
        } else {
            // Setze manuelle Überschreibung
            manualRoleOverrides.value.set(cellId, role);
        }
        
        console.log(`[Draft] Manuelle Rolle für CellId ${cellId}: ${role}`);
        
        // Sammle alle Champions für Wahrscheinlichkeiten
        const allChampions: string[] = [];
        for (const pick of [...team1Picks.value, ...team2Picks.value]) {
            if (pick.champion && pick.isLocked) {
                allChampions.push(pick.champion);
            }
        }
        
        // Lade Wahrscheinlichkeiten
        const probabilities = await loadRoleProbabilities(allChampions);
        
        // Wende recalculateRoleAssignments an um Konflikte aufzulösen
        const isTeam1MyTeam = myTeam.value === 'team1';
        
        team1Picks.value = recalculateRoleAssignments(team1Picks.value, isTeam1MyTeam, probabilities);
        team2Picks.value = recalculateRoleAssignments(team2Picks.value, !isTeam1MyTeam, probabilities);
        
        // Lade Recommendations neu wenn Picks vorhanden
        if (hasAnyPicks.value) {
            debouncedLoadRecommendations();
        }
    }

    /**
     * Prüft ob eine manuelle Rollen-Überschreibung für einen Pick gesetzt ist
     */
    function hasManualRoleOverride(cellId: number): boolean {
        return manualRoleOverrides.value.has(cellId);
    }

    /**
     * Holt die manuelle Rollen-Überschreibung für einen Pick
     */
    function getManualRoleOverride(cellId: number): Role | undefined {
        return manualRoleOverrides.value.get(cellId);
    }

    // Watch auf Patch-Wechsel: Cache leeren und Recommendations neu laden
    const settingsStore = useSettingsStore();
    watch(() => settingsStore.selectedPatch, () => {
        // Cache leeren bei Patch-Wechsel
        roleProbabilitiesCache.value.clear();
        
        // Recommendations neu laden, falls Draft aktiv ist
        if (hasAnyPicks.value) {
            debouncedLoadRecommendations();
        }
    });

    return {
        // State
        team1Picks,
        team2Picks,
        team1Bans,
        team2Bans,
        myTeam,
        myRole,
        manualRole,
        manualRoleOverrides,
        roleProbabilitiesCache,
        leagueClientConnected,
        websocketConnected,
        isLoading,
        error,
        recommendations,
        recommendationsLoading,
        recommendationsError,
        pickScores,
        lastCompletedDraft,
        showDraftSummary,
        
        // Getters
        effectiveRole,
        isInDraft,
        hasAnyPicks,
        myTeamPicks,
        enemyTeamPicks,
        myTeamBans,
        enemyTeamBans,
        myTeamPickedForRole,
        enemyTeamPickedForRole,
        alreadyPickedForRole,
        myRoleChampion,
        enemyRoleChampion,
        shouldLoadRecommendations,
        
        // Actions
        checkLeagueClientStatus,
        connectWebSocket,
        disconnectWebSocket,
        updateDraftState,
        setManualRole,
        setManualRoleForPick,
        hasManualRoleOverride,
        getManualRoleOverride,
        loadRecommendations,
        loadRoleProbabilities,
        clearDraft,
        getPickScore,
        isDraftComplete,
        saveDraftSummary,
        closeDraftSummary,
        
        // Smart Role Locking
        getLockedRolesForTeam,
        isRoleAvailableForPick,
        getChampionWithRole,
        getLockPriority,
        resolveConflict,
        recalculateRoleAssignments
    };
});

