<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useChampionStore } from '@/stores/champion';
import { useSettingsStore } from '@/stores/settings';
import { 
    getChampionMatchups, 
    getChampionSynergies,
    getChampionRoleProbabilities,
    type MatchupData,
    type SynergyData 
} from '@/api/backend';

const championStore = useChampionStore();
const settingsStore = useSettingsStore();

// State
const searchInput = ref('');
const selectedChampion = ref<string | null>(null);
const selectedRole = ref<string | null>(null);
const showSuggestions = ref(false);

const isLoading = ref(false);
const error = ref<string | null>(null);

// Matchup data - zwei Listen pro Kategorie (nach Delta und nach Normalized Delta)
const countersByDelta = ref<MatchupData[]>([]);
const countersByNormalized = ref<MatchupData[]>([]);
const iCounterByDelta = ref<MatchupData[]>([]);
const iCounterByNormalized = ref<MatchupData[]>([]);

// Synergy data
const synergies = ref<SynergyData[]>([]);
const mateRole = ref<string | null>(null);

// Base stats for selected champion
const baseWinrate = ref<number | null>(null);
const baseGames = ref<number | null>(null);
const roleProbabilities = ref<Record<string, number>>({});

// Min-Games Threshold (als Prozent, 0.1% bis 2%)
const minGamesPct = ref(0.3);  // Standard: 0.3%

// Aktiver Tab (Standardmäßig auf 'bad', also "Counter mich")
const activeTab = ref<'bad' | 'good' | 'synergy'>('bad');

// Role mapping for display
const roleDisplayNames: Record<string, string> = {
    'top': 'Top',
    'jungle': 'Jungle',
    'middle': 'Mid',
    'bottom': 'ADC',
    'support': 'Support'
};

// Synergy role mapping for display
const synergyRoleMapping: Record<string, string> = {
    'support': 'ADCs',
    'jungle': 'Supports',
    'middle': 'Jungler',
    'bottom': 'Supports',
    'top': 'Jungler'
};

// Available roles
const roles = ['top', 'jungle', 'middle', 'bottom', 'support'];

// Computed
const suggestions = computed(() => {
    if (!searchInput.value || searchInput.value.length < 1) return [];
    return championStore.searchChampions(searchInput.value, 8);
});

const hasData = computed(() => {
    return countersByDelta.value.length > 0 || 
           countersByNormalized.value.length > 0 ||
           iCounterByDelta.value.length > 0 || 
           iCounterByNormalized.value.length > 0 ||
           synergies.value.length > 0;
});

const synergyTitle = computed(() => {
    if (!selectedRole.value) return 'Beste Synergien';
    const partnerType = synergyRoleMapping[selectedRole.value] || 'Partner';
    return `Beste ${partnerType}`;
});

// Synergies aufteilen für 2-Spalten-Layout
const synergiesLeft = computed(() => synergies.value.slice(0, 5));
const synergiesRight = computed(() => synergies.value.slice(5, 10));

// Helper für Games-Anzeige
const displayBaseGames = computed(() => {
    if (baseGames.value) return baseGames.value;
    return null;
});

// Methods
async function selectChampion(championName: string) {
    selectedChampion.value = championName;
    searchInput.value = championName;
    showSuggestions.value = false;
    
    // Get most played role for this champion
    try {
        const probabilities = await getChampionRoleProbabilities(championName);
        if (probabilities.success && probabilities.probabilities) {
            // Store role probabilities for display
            roleProbabilities.value = probabilities.probabilities;
            
            // Calculate total games from gamesByRole if available
            if (probabilities.gamesByRole) {
                let totalGames = 0;
                for (const games of Object.values(probabilities.gamesByRole)) {
                    totalGames += games || 0;
                }
                baseGames.value = totalGames;
            }
            
            // Find role with highest probability
            let maxProb = 0;
            let maxRole = 'top';
            for (const [role, prob] of Object.entries(probabilities.probabilities)) {
                if (prob > maxProb) {
                    maxProb = prob;
                    maxRole = role;
                }
            }
            selectedRole.value = maxRole;
        }
    } catch (e) {
        console.error('Error getting role probabilities:', e);
        selectedRole.value = 'top'; // Fallback
        roleProbabilities.value = {};
    }
    
    // Load matchups and synergies
    await loadData();
}

async function loadData() {
    if (!selectedChampion.value || !selectedRole.value) return;
    
    isLoading.value = true;
    error.value = null;
    
    try {
        const patch = settingsStore.selectedPatch || undefined;
        
        // Load matchups and synergies in parallel
        // minGamesPct ist in Prozent (0.3), Backend erwartet Dezimal (0.003)
        const [matchupsResponse, synergiesResponse] = await Promise.all([
            getChampionMatchups(selectedChampion.value, selectedRole.value, patch, 10, minGamesPct.value / 100),
            getChampionSynergies(selectedChampion.value, selectedRole.value, patch, 10, undefined, minGamesPct.value / 100)
        ]);
        
        if (matchupsResponse.success) {
            // Zwei Listen pro Kategorie: nach Delta und nach Normalized Delta
            countersByDelta.value = matchupsResponse.counters_by_delta || [];
            countersByNormalized.value = matchupsResponse.counters_by_normalized || [];
            iCounterByDelta.value = matchupsResponse.i_counter_by_delta || [];
            iCounterByNormalized.value = matchupsResponse.i_counter_by_normalized || [];
            // Store base winrate from matchups response
            if (matchupsResponse.base_winrate !== undefined) {
                baseWinrate.value = matchupsResponse.base_winrate;
            }
        } else {
            error.value = matchupsResponse.error || 'Fehler beim Laden der Matchups';
        }
        
        if (synergiesResponse.success) {
            synergies.value = synergiesResponse.synergies || [];
            mateRole.value = synergiesResponse.mate_role || null;
        } else {
            error.value = synergiesResponse.error || 'Fehler beim Laden der Synergien';
        }
    } catch (e) {
        error.value = e instanceof Error ? e.message : 'Unbekannter Fehler';
        console.error('Error loading data:', e);
    } finally {
        isLoading.value = false;
    }
}

function onRoleChange(role: string) {
    selectedRole.value = role;
    if (selectedChampion.value) {
        loadData();
    }
}

function formatWinrate(winrate: number | null | undefined): string {
    if (winrate === undefined || winrate === null) return '-';
    return (winrate * 100).toFixed(1) + '%';
}

function formatGames(games: number | null | undefined): string {
    if (games === undefined || games === null) return '-';
    if (games >= 1000000) return (games / 1000000).toFixed(1) + 'M';
    if (games >= 1000) return (games / 1000).toFixed(1) + 'K';
    return games.toString();
}

function formatRolePct(role: string): string {
    const pct = roleProbabilities.value[role];
    if (pct === undefined) return '';
    return `(${(pct * 100).toFixed(0)}%)`;
}

function formatDelta(delta: number | undefined): string {
    if (delta === undefined) return '';
    const sign = delta >= 0 ? '+' : '';
    return sign + (delta * 100).toFixed(1) + '%';
}

function getDeltaClass(delta: number | undefined): string {
    if (delta === undefined) return '';
    if (delta > 0) return 'positive';
    if (delta < 0) return 'negative';
    return '';
}

function getWinrateClass(winrate: number | undefined): string {
    if (winrate === undefined) return '';
    const wr = winrate * 100;
    if (wr >= 55) return 'excellent';
    if (wr >= 52) return 'good';
    if (wr >= 48) return 'average';
    return 'poor';
}

function onInputFocus() {
    if (searchInput.value.length > 0) {
        showSuggestions.value = true;
    }
}

function onInputBlur() {
    // Delay to allow click on suggestion
    setTimeout(() => {
        showSuggestions.value = false;
    }, 200);
}

// Watch for input changes
watch(searchInput, (newValue) => {
    if (newValue.length > 0) {
        showSuggestions.value = true;
    } else {
        showSuggestions.value = false;
    }
});

// Load champion data on mount
onMounted(async () => {
    if (!championStore.championsLoaded) {
        await championStore.loadChampionData();
    }
});
</script>

<template>
    <div class="champion-lookup-view">
        <div class="header-toolbar">
            <div class="toolbar-search">
                <div class="search-input-wrapper compact">
                    <span class="search-icon">🔍</span>
                    <input
                        v-model="searchInput"
                        type="text"
                        class="search-input-flat"
                        placeholder="Champion..."
                        @focus="onInputFocus"
                        @blur="onInputBlur"
                    />
                </div>
                <div v-if="showSuggestions && suggestions.length > 0" class="suggestions-dropdown">
                    <div
                        v-for="champ in suggestions"
                        :key="champ"
                        class="suggestion-item"
                        @mousedown="selectChampion(champ)"
                    >
                        <img :src="championStore.getChampionIconUrl(champ)" class="suggestion-icon" />
                        <span class="suggestion-name">{{ champ }}</span>
                    </div>
                </div>
            </div>

            <div class="toolbar-divider"></div>

            <div v-if="selectedChampion" class="toolbar-info">
                <img 
                    :src="championStore.getChampionIconUrl(selectedChampion)" 
                    class="toolbar-champ-icon"
                />
                <div class="toolbar-text">
                    <div class="toolbar-name-row">
                        <span class="toolbar-name">{{ selectedChampion }}</span>
                        <div class="mini-roles">
                            <button
                                v-for="role in roles"
                                :key="role"
                                :class="['mini-role-btn', { 
                                    active: selectedRole === role, 
                                    disabled: !roleProbabilities[role] 
                                }]"
                                @click="roleProbabilities[role] ? onRoleChange(role) : null"
                                :title="roleDisplayNames[role]"
                            >
                                {{ roleDisplayNames[role].substring(0,1) }}
                            </button>
                        </div>
                    </div>
                    <div class="toolbar-stats-row">
                        <span v-if="baseWinrate !== null" :class="['stat-text', getWinrateClass(baseWinrate)]">
                            {{ formatWinrate(baseWinrate) }} Win
                        </span>
                        <span class="stat-separator">•</span>
                        <span class="stat-text muted">
                            {{ formatGames(displayBaseGames) }} Games
                        </span>
                    </div>
                </div>
            </div>

            <div class="toolbar-spacer"></div>

            <div v-if="selectedChampion" class="toolbar-settings">
                <div class="slider-compact-group">
                    <span class="slider-label-mini">Min. {{ minGamesPct.toFixed(1) }}% Games</span>
                    <input
                        v-model.number="minGamesPct"
                        type="range"
                        min="0.1"
                        max="2"
                        step="0.1"
                        class="slider-input-micro"
                        @change="loadData()"
                    />
                </div>
            </div>
        </div>

        <!-- Loading State -->
        <div v-if="isLoading" class="loading-state">
            <span class="loading-spinner"></span>
            <span>Lade Daten...</span>
        </div>

        <!-- Error State -->
        <div v-else-if="error" class="error-state">
            <span class="error-icon">⚠️</span>
            <span>{{ error }}</span>
        </div>

        <!-- Data Display -->
        <div v-else-if="hasData" class="data-container">
            
            <div class="tabs-nav">
                <button 
                    @click="activeTab = 'bad'"
                    :class="['tab-btn', { active: activeTab === 'bad' }]"
                >
                    <span class="tab-icon">⚠️</span>
                    Counter mich
                </button>
                <button 
                    @click="activeTab = 'good'"
                    :class="['tab-btn', { active: activeTab === 'good' }]"
                >
                    <span class="tab-icon">✅</span>
                    Ich countere
                </button>
                <button 
                    @click="activeTab = 'synergy'"
                    :class="['tab-btn', { active: activeTab === 'synergy' }]"
                >
                    <span class="tab-icon">🤝</span>
                    Synergien
                </button>
            </div>

            <div v-if="activeTab === 'bad'" class="data-section tab-content">
                <div class="section-header">
                    <h3 class="section-title">Gefährliche Matchups</h3>
                </div>
                
                <div class="counter-grid">
                    <div class="counter-column bad">
                        <h4 class="column-title">Nach Delta</h4>
                        <p class="column-description">Schlechteste Matchups (Statistisch)</p>
                        
                        <div class="matchup-list">
                            <div
                                v-for="(matchup, index) in countersByDelta"
                                :key="'delta-' + matchup.opponent_key"
                                class="matchup-item bad"
                            >
                                <span class="matchup-rank">{{ index + 1 }}</span>
                                <img 
                                    :src="championStore.getChampionIconUrl(matchup.name || '')" 
                                    :alt="matchup.name"
                                    class="matchup-icon"
                                />
                                <span class="matchup-name">{{ matchup.name }}</span>
                                <div class="matchup-stats">
                                    <span :class="['matchup-winrate', getWinrateClass(matchup.winrate)]">
                                        {{ formatWinrate(matchup.winrate) }}
                                    </span>
                                    <span :class="['matchup-delta', getDeltaClass(matchup.delta)]">
                                        {{ formatDelta(matchup.delta) }}
                                    </span>
                                    <span class="matchup-games">{{ formatGames(matchup.games) }}</span>
                                </div>
                            </div>
                            <div v-if="countersByDelta.length === 0" class="no-data">Keine Daten</div>
                        </div>
                    </div>

                    <div class="counter-column bad normalized">
                        <h4 class="column-title">Normalisiert (Skill)</h4>
                        <p class="column-description">Echte Counter (Unabhängig von Meta-Stärke)</p>
                        
                        <div class="matchup-list">
                            <div
                                v-for="(matchup, index) in countersByNormalized"
                                :key="'norm-' + matchup.opponent_key"
                                class="matchup-item bad"
                            >
                                <span class="matchup-rank">{{ index + 1 }}</span>
                                <img 
                                    :src="championStore.getChampionIconUrl(matchup.name || '')" 
                                    :alt="matchup.name"
                                    class="matchup-icon"
                                />
                                <span class="matchup-name">{{ matchup.name }}</span>
                                <div class="matchup-stats">
                                    <span :class="['matchup-winrate', getWinrateClass(matchup.winrate)]">
                                        {{ formatWinrate(matchup.winrate) }}
                                    </span>
                                    <span :class="['matchup-delta', getDeltaClass(matchup.normalized_delta)]">
                                        {{ formatDelta(matchup.normalized_delta) }}
                                    </span>
                                    <span class="matchup-games">{{ formatGames(matchup.games) }}</span>
                                </div>
                            </div>
                            <div v-if="countersByNormalized.length === 0" class="no-data">Keine Daten</div>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'good'" class="data-section tab-content">
                <div class="section-header">
                    <h3 class="section-title">Gute Matchups</h3>
                </div>
                
                <div class="counter-grid">
                    <div class="counter-column good">
                        <h4 class="column-title">Nach Delta</h4>
                        <p class="column-description">Beste Matchups (Statistisch)</p>
                        
                        <div class="matchup-list">
                            <div
                                v-for="(matchup, index) in iCounterByDelta"
                                :key="'delta-' + matchup.opponent_key"
                                class="matchup-item good"
                            >
                                <span class="matchup-rank">{{ index + 1 }}</span>
                                <img 
                                    :src="championStore.getChampionIconUrl(matchup.name || '')" 
                                    :alt="matchup.name"
                                    class="matchup-icon"
                                />
                                <span class="matchup-name">{{ matchup.name }}</span>
                                <div class="matchup-stats">
                                    <span :class="['matchup-winrate', getWinrateClass(matchup.winrate)]">
                                        {{ formatWinrate(matchup.winrate) }}
                                    </span>
                                    <span :class="['matchup-delta', getDeltaClass(matchup.delta)]">
                                        {{ formatDelta(matchup.delta) }}
                                    </span>
                                    <span class="matchup-games">{{ formatGames(matchup.games) }}</span>
                                </div>
                            </div>
                            <div v-if="iCounterByDelta.length === 0" class="no-data">Keine Daten</div>
                        </div>
                    </div>

                    <div class="counter-column good normalized">
                        <h4 class="column-title">Normalisiert (Skill)</h4>
                        <p class="column-description">Echte Opfer (Mechanisch unterlegen)</p>
                        
                        <div class="matchup-list">
                            <div
                                v-for="(matchup, index) in iCounterByNormalized"
                                :key="'norm-' + matchup.opponent_key"
                                class="matchup-item good"
                            >
                                <span class="matchup-rank">{{ index + 1 }}</span>
                                <img 
                                    :src="championStore.getChampionIconUrl(matchup.name || '')" 
                                    :alt="matchup.name"
                                    class="matchup-icon"
                                />
                                <span class="matchup-name">{{ matchup.name }}</span>
                                <div class="matchup-stats">
                                    <span :class="['matchup-winrate', getWinrateClass(matchup.winrate)]">
                                        {{ formatWinrate(matchup.winrate) }}
                                    </span>
                                    <span :class="['matchup-delta', getDeltaClass(matchup.normalized_delta)]">
                                        {{ formatDelta(matchup.normalized_delta) }}
                                    </span>
                                    <span class="matchup-games">{{ formatGames(matchup.games) }}</span>
                                </div>
                            </div>
                            <div v-if="iCounterByNormalized.length === 0" class="no-data">Keine Daten</div>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'synergy'" class="data-section tab-content">
                <div class="section-header">
                    <h3 class="section-title">
                        {{ synergyTitle }}
                        <span v-if="mateRole" class="mate-role-badge">{{ roleDisplayNames[mateRole] }}</span>
                    </h3>
                </div>
                
                <div class="counter-grid">
                    <div class="counter-column synergy-col">
                        <div class="matchup-list">
                            <div
                                v-for="(synergy, index) in synergiesLeft"
                                :key="synergy.mate_key"
                                class="matchup-item"
                            >
                                <span class="matchup-rank">{{ index + 1 }}</span>
                                <img 
                                    :src="championStore.getChampionIconUrl(synergy.name || '')" 
                                    class="matchup-icon"
                                />
                                <span class="matchup-name">{{ synergy.name }}</span>
                                <div class="matchup-stats">
                                    <span :class="['matchup-winrate', getWinrateClass(synergy.winrate)]">
                                        {{ formatWinrate(synergy.winrate) }}
                                    </span>
                                    <span :class="['matchup-delta', getDeltaClass(synergy.delta)]">
                                        {{ formatDelta(synergy.delta) }}
                                    </span>
                                    <span class="matchup-games">{{ formatGames(synergy.games) }}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="counter-column synergy-col">
                        <div class="matchup-list">
                            <div
                                v-for="(synergy, index) in synergiesRight"
                                :key="synergy.mate_key"
                                class="matchup-item"
                            >
                                <span class="matchup-rank">{{ index + 6 }}</span>
                                <img 
                                    :src="championStore.getChampionIconUrl(synergy.name || '')" 
                                    class="matchup-icon"
                                />
                                <span class="matchup-name">{{ synergy.name }}</span>
                                <div class="matchup-stats">
                                    <span :class="['matchup-winrate', getWinrateClass(synergy.winrate)]">
                                        {{ formatWinrate(synergy.winrate) }}
                                    </span>
                                    <span :class="['matchup-delta', getDeltaClass(synergy.delta)]">
                                        {{ formatDelta(synergy.delta) }}
                                    </span>
                                    <span class="matchup-games">{{ formatGames(synergy.games) }}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div v-if="synergies.length === 0" class="no-data">Keine Synergie-Daten verfügbar</div>
            </div>
        </div>

        <!-- Empty State -->
        <div v-else-if="!selectedChampion" class="empty-state">
            <div class="empty-icon">🔍</div>
            <h4>Wähle einen Champion</h4>
            <p>Suche nach einem Champion, um Counterpicks und Synergien zu sehen.</p>
        </div>
    </div>
</template>

<style scoped>
.champion-lookup-view {
    max-width: 1200px;
    margin: 0 auto;
}

.view-title {
    margin: 0 0 0.5rem 0;
    color: var(--primary);
}

.view-description {
    margin: 0 0 1.5rem 0;
    color: var(--text-secondary);
}

/* --- NEW TOOLBAR STYLES --- */
.header-toolbar {
    display: flex;
    align-items: center;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 0.5rem 1rem;
    margin-bottom: 1.5rem;
    height: 60px;
    gap: 1rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.toolbar-divider {
    width: 1px;
    height: 32px;
    background: var(--border-color);
}

.toolbar-spacer {
    flex: 1;
}

/* 1. Search */
.toolbar-search {
    position: relative;
    width: 220px;
}

.search-input-wrapper {
    position: relative;
}

.search-input-flat {
    width: 100%;
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-size: 0.95rem;
    padding: 0.5rem 0 0.5rem 2rem;
}

.search-input-flat:focus {
    outline: none;
}

.search-input-wrapper .search-icon {
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.suggestions-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-top: none;
    border-radius: 0 0 var(--radius-md) var(--radius-md);
    max-height: 300px;
    overflow-y: auto;
    z-index: 100;
}

.suggestion-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 1rem;
    cursor: pointer;
    transition: background-color var(--transition-fast);
}

.suggestion-item:hover {
    background: var(--bg-tertiary);
}

.suggestion-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    object-fit: cover;
}

.suggestion-name {
    font-weight: 500;
}

/* 2. Info Section */
.toolbar-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.toolbar-champ-icon {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: 2px solid var(--primary);
}

.toolbar-text {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.toolbar-name-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.toolbar-name {
    font-weight: 700;
    font-size: 1rem;
    line-height: 1;
}

/* Mini Roles */
.mini-roles {
    display: flex;
    gap: 2px;
}

.mini-role-btn {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    font-weight: 700;
    background: var(--bg-tertiary);
    border: 1px solid transparent;
    border-radius: 4px;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0;
}

.mini-role-btn:hover:not(.disabled) {
    background: var(--bg-primary);
}

.mini-role-btn.active {
    background: var(--primary);
    color: white;
}

.mini-role-btn.disabled {
    opacity: 0.2;
    cursor: default;
    background: transparent;
}

/* Stats Row */
.toolbar-stats-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
    margin-top: 2px;
}

.stat-text.excellent { color: #4ade80; }
.stat-text.good { color: #60a5fa; }
.stat-text.average { color: #fbbf24; }
.stat-text.poor { color: #f87171; }
.stat-text.muted { color: var(--text-muted); }

.stat-separator {
    color: var(--border-color);
}

/* 3. Settings Slider */
.slider-compact-group {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
}

.slider-label-mini {
    font-size: 0.65rem;
    color: var(--text-secondary);
}

.slider-input-micro {
    width: 80px;
    height: 4px;
    appearance: none;
    background: var(--bg-tertiary);
    border-radius: 2px;
}

.slider-input-micro::-webkit-slider-thumb {
    appearance: none;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--primary);
    cursor: pointer;
}

.slider-input-micro::-moz-range-thumb {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--primary);
    cursor: pointer;
    border: none;
}

/* Synergy Specific Adjustments */
.synergy-col {
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    padding: 1rem;
}

/* Mobile Responsive */
@media (max-width: 768px) {
    .header-toolbar {
        height: auto;
        flex-direction: column;
        align-items: stretch;
        padding: 1rem;
        gap: 1rem;
    }
    
    .toolbar-divider, .toolbar-spacer {
        display: none;
    }
    
    .toolbar-search {
        width: 100%;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 0.5rem;
    }
    
    .toolbar-info {
        justify-content: space-between;
    }
    
    .slider-compact-group {
        align-items: center;
        width: 100%;
        flex-direction: row;
        justify-content: space-between;
    }
}

/* Loading & Error States */
.loading-state,
.error-state,
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    text-align: center;
    color: var(--text-secondary);
}

.loading-spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.error-state {
    color: var(--error);
}

.error-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
}

.empty-state .empty-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
}

.empty-state h4 {
    margin: 0 0 0.5rem 0;
    color: var(--text-primary);
}

.empty-state p {
    margin: 0;
}

/* Data Container */
.data-container {
    display: flex;
    flex-direction: column;
    gap: 0;
}

/* --- TABS NAVIGATION --- */
.tabs-nav {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 1px;
}

.tab-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    color: var(--text-secondary);
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-fast);
    font-size: 1rem;
}

.tab-btn:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
    border-top-left-radius: var(--radius-md);
    border-top-right-radius: var(--radius-md);
}

.tab-btn.active {
    color: var(--primary);
    border-bottom-color: var(--primary);
}

.tab-icon {
    font-size: 1.1rem;
}

/* Tab Content Box */
.tab-content {
    background: var(--bg-secondary);
    border-top-right-radius: var(--radius-lg);
    border-bottom-left-radius: var(--radius-lg);
    border-bottom-right-radius: var(--radius-lg);
    padding: 1.5rem;
    min-height: 400px;
    border: 1px solid var(--border-color);
    border-top: none;
}

.data-section {
    background: var(--bg-secondary);
    border-radius: var(--radius-lg);
    padding: 1.5rem;
}

.section-header {
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border-color);
}

.section-subtitle {
    margin: 0;
    color: var(--text-muted);
    font-size: 0.9rem;
}

.section-title {
    margin: 0 0 0.5rem 0;
    font-size: 1.125rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* Matchup Stats Container */
.matchup-stats {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-left: auto;
    justify-content: flex-end;
}

/* Synergien Grid */
.synergy-grid {
    max-width: 800px;
}

.synergy-list.full-width {
    width: 100%;
}

.mate-role-badge {
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
    background: var(--primary);
    color: white;
    border-radius: var(--radius-full);
    font-weight: 500;
}

/* Counter Grid */
.counter-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
}

@media (max-width: 768px) {
    .counter-grid {
        grid-template-columns: 1fr;
    }
}

.counter-column {
    background: var(--bg-primary);
    border-radius: var(--radius-md);
    padding: 1rem;
}

.counter-column.bad {
    border-left: 4px solid var(--error);
}

.counter-column.good {
    border-left: 4px solid var(--success);
}

.counter-column.normalized {
    opacity: 0.95;
    background: var(--bg-tertiary);
}

.title-icon {
    font-size: 1.25rem;
}

.column-title {
    margin: 0 0 0.25rem 0;
    font-size: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.column-description {
    margin: 0 0 1rem 0;
    font-size: 0.8rem;
    color: var(--text-muted);
}

/* Matchup List */
.matchup-list,
.synergy-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.matchup-item,
.synergy-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem;
    background: var(--bg-secondary);
    border-radius: var(--radius-sm);
    transition: background-color var(--transition-fast);
}

.matchup-item:hover,
.synergy-item:hover {
    background: var(--bg-tertiary);
}

.matchup-rank,
.synergy-rank {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary);
    border-radius: var(--radius-full);
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--text-secondary);
}

.matchup-icon,
.synergy-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    object-fit: cover;
}

.matchup-name,
.synergy-name {
    flex: 1;
    font-weight: 500;
}

.matchup-winrate,
.synergy-winrate {
    font-weight: 700;
    width: 50px;
    text-align: right;
}

.matchup-winrate.excellent,
.synergy-winrate.excellent {
    color: #22c55e;
}

.matchup-winrate.good,
.synergy-winrate.good {
    color: #3b82f6;
}

.matchup-winrate.average,
.synergy-winrate.average {
    color: #f59e0b;
}

.matchup-winrate.poor,
.synergy-winrate.poor {
    color: #ef4444;
}

.matchup-delta {
    font-size: 0.85rem;
    font-weight: 600;
    width: 50px;
    text-align: right;
}

.matchup-delta.positive {
    color: #22c55e;
}

.matchup-delta.negative {
    color: #ef4444;
}

.matchup-games,
.synergy-games {
    font-size: 0.75rem;
    color: var(--text-muted);
    width: 40px;
    text-align: right;
    opacity: 0.7;
}

.no-data {
    padding: 1rem;
    text-align: center;
    color: var(--text-muted);
    font-style: italic;
}

/* Mobile Responsive Tabs */
@media (max-width: 600px) {
    .tabs-nav {
        flex-direction: column;
        gap: 0;
        border-bottom: none;
    }
    
    .tab-btn {
        width: 100%;
        border-bottom: 1px solid var(--border-color);
        border-left: 3px solid transparent;
    }
    
    .tab-btn.active {
        border-bottom-color: var(--border-color);
        border-left-color: var(--primary);
        background: var(--bg-tertiary);
    }
    
    .tab-content {
        border-top: 1px solid var(--border-color);
        border-radius: var(--radius-lg);
    }
}
</style>
