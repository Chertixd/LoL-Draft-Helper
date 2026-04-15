/**
 * Backend API Client
 * Kommunikation mit dem Python Flask Backend
 */

import type {
    RecommendationRequest,
    RecommendationResponse
} from '@counterpick/core';

const API_BASE_URL = '/api';

/**
 * Wartet für eine bestimmte Zeit
 */
function delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Generische Fetch-Funktion mit Error Handling und Retry-Logik
 */
async function fetchApi<T>(
    endpoint: string,
    options?: RequestInit,
    retries = 2,
    retryDelay = 500
): Promise<T> {
    let lastError: Error | null = null;
    
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options?.headers
                },
                ...options
            });

            // Bei 5xx Fehlern: Retry
            if (response.status >= 500 && attempt < retries) {
                console.warn(`[API] Server-Fehler ${response.status} bei ${endpoint}, Retry ${attempt + 1}/${retries}`);
                await delay(retryDelay * (attempt + 1)); // Exponential backoff
                continue;
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return response.json();
        } catch (error) {
            lastError = error instanceof Error ? error : new Error(String(error));
            
            // Bei Netzwerkfehlern: Retry
            if (attempt < retries) {
                console.warn(`[API] Fehler bei ${endpoint}, Retry ${attempt + 1}/${retries}:`, lastError.message);
                await delay(retryDelay * (attempt + 1));
                continue;
            }
        }
    }
    
    throw lastError || new Error('Unbekannter Fehler');
}

/**
 * Health Check - Prüft Backend-Status
 */
export async function checkBackendHealth(): Promise<{ status: string }> {
    return fetchApi('/health', undefined, 1, 300);
}

/**
 * Champion-Liste abrufen
 */
export async function getChampionsList(): Promise<{
    success: boolean;
    champions: string[];
}> {
    return fetchApi('/champions/list');
}

/**
 * Primary Roles abrufen
 */
export async function getPrimaryRoles(): Promise<{
    success: boolean;
    primary_roles: Record<string, string>;
}> {
    return fetchApi('/primary-roles');
}

/**
 * Verfügbare Patches aus Supabase abrufen
 */
export async function getAvailablePatches(): Promise<{
    success: boolean;
    patches?: string[];
    error?: string;
}> {
    return fetchApi('/patches');
}

/**
 * Recommendations abrufen (Recommendation Engine)
 * Mit mehr Retries wegen gelegentlicher Supabase-Verbindungsprobleme
 */
export async function getRecommendations(
    request: RecommendationRequest
): Promise<RecommendationResponse> {
    return fetchApi('/recommendations', {
        method: 'POST',
        body: JSON.stringify(request)
    }, 3, 800); // 3 Retries mit 800ms Delay für Recommendations
}

/**
 * League Client Status prüfen
 */
export async function getLeagueClientStatus(): Promise<{
    success: boolean;
    client_running: boolean;
}> {
    return fetchApi('/league-client/status', undefined, 1, 300);
}

/**
 * League Client Draft-Daten abrufen
 */
export async function getLeagueClientDraft(): Promise<{
    success: boolean;
    draft?: Record<string, unknown>;
    error?: string;
}> {
    return fetchApi('/league-client/draft');
}

/**
 * Rolle manuell setzen
 */
export async function setRoleOverride(role: string | null): Promise<{
    success: boolean;
    role: string | null;
}> {
    return fetchApi('/set-role', {
        method: 'POST',
        body: JSON.stringify({ role })
    });
}

/**
 * Rollen-Wahrscheinlichkeiten für einen Champion abrufen
 */
export async function getChampionRoleProbabilities(champion: string): Promise<{
    success: boolean;
    champion_key?: string;
    champion_name?: string;
    probabilities?: Record<string, number>;
    totalGames?: number;
    gamesByRole?: Record<string, number>;
    error?: string;
}> {
    return fetchApi(`/champion/${encodeURIComponent(champion)}/role-probabilities`);
}

/**
 * Batch-Abruf von Rollen-Wahrscheinlichkeiten für mehrere Champions
 */
export async function getBatchRoleProbabilities(
    champions: string[],
    patch?: string
): Promise<{
    success: boolean;
    results?: Record<string, {
        probabilities: Record<string, number>;
        totalGames: number;
        gamesByRole?: Record<string, number>;
        error?: string;
    }>;
    error?: string;
}> {
    return fetchApi('/champions/role-probabilities', {
        method: 'POST',
        body: JSON.stringify({ champions, patch })
    });
}

/**
 * Matchup-Daten für einen Champion abrufen
 */
export interface MatchupData {
    champion_key?: string;
    opponent_key?: string;
    name?: string;
    role?: string;
    opponent_role?: string;
    games?: number;
    wins?: number;
    winrate?: number;
    delta?: number;
    wilson_score?: number;
    opponent_pickrate?: number;
    opponent_base_wr?: number;
    normalized_delta?: number;
}

export interface ChampionMatchupsResponse {
    success: boolean;
    champion?: string;
    role?: string;
    patch?: string;
    base_winrate?: number;
    base_wilson?: number;
    // Zwei Listen pro Kategorie: sortiert nach Delta und nach Normalized Delta
    counters_by_delta?: MatchupData[];
    counters_by_normalized?: MatchupData[];
    i_counter_by_delta?: MatchupData[];
    i_counter_by_normalized?: MatchupData[];
    error?: string;
}

export async function getChampionMatchups(
    champion: string,
    role?: string,
    patch?: string,
    limit?: number,
    minGamesPct?: number
): Promise<ChampionMatchupsResponse> {
    const params = new URLSearchParams();
    if (role) params.append('role', role);
    if (patch) params.append('patch', patch);
    if (limit) params.append('limit', limit.toString());
    if (minGamesPct !== undefined) params.append('min_games_pct', minGamesPct.toString());
    
    const queryString = params.toString();
    const endpoint = `/champion/${encodeURIComponent(champion)}/matchups${queryString ? '?' + queryString : ''}`;
    
    return fetchApi(endpoint);
}

/**
 * Synergie-Daten für einen Champion abrufen
 */
export interface SynergyData {
    champion_key?: string;
    mate_key?: string;
    name?: string;
    role?: string;
    mate_role?: string;
    games?: number;
    wins?: number;
    winrate?: number;
    delta?: number;
    wilson_score?: number;
}

export interface ChampionSynergiesResponse {
    success: boolean;
    champion?: string;
    role?: string;
    mate_role?: string;
    patch?: string;
    base_winrate?: number;
    base_wilson?: number;
    synergies?: SynergyData[];
    error?: string;
}

export async function getChampionSynergies(
    champion: string,
    role?: string,
    patch?: string,
    limit?: number,
    mateRole?: string,
    minGamesPct?: number
): Promise<ChampionSynergiesResponse> {
    const params = new URLSearchParams();
    if (role) params.append('role', role);
    if (patch) params.append('patch', patch);
    if (limit) params.append('limit', limit.toString());
    if (mateRole) params.append('mate_role', mateRole);
    if (minGamesPct !== undefined) params.append('min_games_pct', minGamesPct.toString());
    
    const queryString = params.toString();
    const endpoint = `/champion/${encodeURIComponent(champion)}/synergies${queryString ? '?' + queryString : ''}`;
    
    return fetchApi(endpoint);
}