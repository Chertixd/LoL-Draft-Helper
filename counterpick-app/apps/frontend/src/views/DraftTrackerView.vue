<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { useChampionStore } from '@/stores/champion';
import { useDraftStore } from '@/stores/draft';
import { useSettingsStore } from '@/stores/settings';
import type { Role } from '@counterpick/core';
import { 
    getChampionMatchups, 
    getChampionSynergies,
    type MatchupData,
    type SynergyData 
} from '@/api/backend';

import DraftTeam from '@/components/draft/DraftTeam.vue';
import DraftSummaryCard from '@/components/draft/DraftSummaryCard.vue';
import RoleSelector from '@/components/draft/RoleSelector.vue';
import RecommendationsList from '@/components/draft/RecommendationsList.vue';

const championStore = useChampionStore();
const draftStore = useDraftStore();
const settingsStore = useSettingsStore();

// --- STATE FÜR ANALYSE ---
const analysisChampion = ref<string | null>(null);
const analysisRole = ref<string | null>(null);
const isAnalysisLoading = ref(false);
const analysisError = ref<string | null>(null);

// Data Container
const countersByDelta = ref<MatchupData[]>([]);
const countersByNormalized = ref<MatchupData[]>([]);
const iCounterByDelta = ref<MatchupData[]>([]);
const iCounterByNormalized = ref<MatchupData[]>([]);
const synergies = ref<SynergyData[]>([]);
const mateRole = ref<string | null>(null);
const activeTab = ref<'bad' | 'good' | 'synergy'>('bad');
const minGamesPct = ref(0.3);

// Search State
const searchInput = ref('');
const showSuggestions = ref(false);

// --- COMPUTED PROPERTIES ---
const myTeamSide = computed(() => !draftStore.myTeam ? 'neutral' : (draftStore.myTeam === 'team1' ? 'blue' : 'red'));
const enemyTeamSide = computed(() => !draftStore.myTeam ? 'neutral' : (myTeamSide.value === 'blue' ? 'red' : 'blue'));
const myTeamName = computed(() => !draftStore.myTeam ? 'Team 1' : `Mein Team (${myTeamSide.value === 'blue' ? 'Blue' : 'Red'} Side)`);
const enemyTeamName = computed(() => !draftStore.myTeam ? 'Team 2' : `Gegner Team (${enemyTeamSide.value === 'blue' ? 'Blue' : 'Red'} Side)`);

const suggestions = computed(() => {
    if (!searchInput.value || searchInput.value.length < 1) return [];
    return championStore.searchChampions(searchInput.value, 8);
});

const hasAnalysisData = computed(() => {
    return countersByDelta.value.length > 0 || 
           countersByNormalized.value.length > 0 ||
           iCounterByDelta.value.length > 0 || 
           iCounterByNormalized.value.length > 0 ||
           synergies.value.length > 0;
});

const synergiesLeft = computed(() => synergies.value.slice(0, 5));
const synergiesRight = computed(() => synergies.value.slice(5, 10));

const roleDisplayNames: Record<string, string> = {
    'top': 'Top', 'jungle': 'Jungle', 'middle': 'Mid', 'bottom': 'ADC', 'support': 'Support'
};

// --- LIFECYCLE ---
onMounted(async () => {
    try {
        if (!championStore.championsLoaded) await championStore.loadChampionData();
        await draftStore.checkLeagueClientStatus();
        await draftStore.connectWebSocket();
        
        if (draftStore.myRoleChampion) {
            analysisChampion.value = draftStore.myRoleChampion;
            searchInput.value = draftStore.myRoleChampion;
            loadAnalysisData();
        }
    } catch (error) {
        console.error('[DraftTracker] Fehler beim Initialisieren:', error);
    }
});

onUnmounted(() => {
    draftStore.disconnectWebSocket();
});

// --- METHODS ---
function onRoleChange(role: Role) {
    draftStore.setManualRole(role);
}

function refreshRecommendations() {
    draftStore.loadRecommendations();
}

async function selectAnalysisChampion(champion: string) {
    analysisChampion.value = champion;
    searchInput.value = champion;
    showSuggestions.value = false;
    await loadAnalysisData();
}

async function loadAnalysisData() {
    if (!analysisChampion.value) return;
    const role = draftStore.effectiveRole || 'middle';
    analysisRole.value = role;
    isAnalysisLoading.value = true;
    analysisError.value = null;

    try {
        const patch = settingsStore.selectedPatch || undefined;
        const [matchupsResponse, synergiesResponse] = await Promise.all([
            getChampionMatchups(analysisChampion.value, role, patch, 10, minGamesPct.value / 100),
            getChampionSynergies(analysisChampion.value, role, patch, 10, undefined, minGamesPct.value / 100)
        ]);

        if (matchupsResponse.success) {
            countersByDelta.value = matchupsResponse.counters_by_delta || [];
            countersByNormalized.value = matchupsResponse.counters_by_normalized || [];
            iCounterByDelta.value = matchupsResponse.i_counter_by_delta || [];
            iCounterByNormalized.value = matchupsResponse.i_counter_by_normalized || [];
        }
        if (synergiesResponse.success) {
            synergies.value = synergiesResponse.synergies || [];
            mateRole.value = synergiesResponse.mate_role || null;
        }
    } catch (e) {
        analysisError.value = 'Fehler beim Laden der Analyse-Daten';
        console.error(e);
    } finally {
        isAnalysisLoading.value = false;
    }
}

// Formatting
function formatWinrate(wr: number | undefined) { return wr ? (wr * 100).toFixed(1) + '%' : '-'; }
function formatDelta(d: number | undefined) { if (d === undefined) return ''; return (d >= 0 ? '+' : '') + (d * 100).toFixed(1) + '%'; }
function formatGames(g: number | undefined) { if (!g) return '-'; return g >= 1000 ? (g/1000).toFixed(1) + 'k' : g.toString(); }
function getWinrateClass(wr: number | undefined) { if (!wr) return ''; const v = wr * 100; if (v >= 52) return 'good'; if (v <= 48) return 'poor'; return 'average'; }
function getDeltaClass(d: number | undefined) { if (d === undefined) return ''; return d > 0 ? 'positive' : 'negative'; }

function hideSuggestions() {
    setTimeout(() => {
        showSuggestions.value = false;
    }, 200);
}

watch(() => draftStore.myRoleChampion, (newChamp) => {
    if (newChamp) selectAnalysisChampion(newChamp);
});
</script>

<template>
    <div class="draft-tracker-view">
        <div :class="['draft-container', { 'not-in-draft': !draftStore.isInDraft }]">
            <DraftTeam
                :team-name="myTeamName"
                :picks="draftStore.myTeamPicks"
                :bans="draftStore.myTeamBans"
                :side="myTeamSide"
                :is-my-team="true"
            />
            <DraftTeam
                :team-name="enemyTeamName"
                :picks="draftStore.enemyTeamPicks"
                :bans="draftStore.enemyTeamBans"
                :side="enemyTeamSide"
                :is-my-team="false"
            />
        </div>

        <RoleSelector
            :model-value="draftStore.manualRole"
            @update:model-value="onRoleChange"
        />

        <div class="content-split-layout">
            
            <div class="column-recommendations">
                <RecommendationsList
                    v-if="!draftStore.isDraftComplete()"
                    :recommendations="draftStore.recommendations"
                    :loading="draftStore.recommendationsLoading"
                    :error="draftStore.recommendationsError"
                    :selected-role="draftStore.effectiveRole"
                    :picked-champion="draftStore.myRoleChampion"
                    :enemy-picked-champion="draftStore.enemyRoleChampion"
                    @refresh="refreshRecommendations"
                />
                
                <div v-else class="draft-complete-msg">
                    Draft abgeschlossen. Viel Erfolg!
                </div>
            </div>

            <div class="column-analysis">
                <div class="analysis-section-wrapper">
                    <div class="analysis-header-bar">
                        <h3 class="analysis-main-title">Live Analyse</h3>
                        
                        <div class="analysis-search">
                            <input 
                                v-model="searchInput"
                                class="analysis-input"
                                placeholder="Champion analysieren..."
                                @focus="showSuggestions = true"
                                @blur="hideSuggestions"
                            />
                            <div v-if="showSuggestions && suggestions.length > 0" class="suggestions-popover">
                                <div 
                                    v-for="s in suggestions" 
                                    :key="s"
                                    class="suggestion-row"
                                    @mousedown="selectAnalysisChampion(s)"
                                >
                                    {{ s }}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div v-if="analysisChampion && !isAnalysisLoading && hasAnalysisData" class="analysis-content-box">
                        <div class="champion-badge">
                            <img :src="championStore.getChampionIconUrl(analysisChampion)" class="champ-icon-small"/>
                            <div class="champ-info">
                                <span class="champ-name">{{ analysisChampion }}</span>
                                <span class="champ-role">{{ roleDisplayNames[analysisRole || 'middle'] }}</span>
                            </div>
                        </div>

                        <div class="tabs-nav">
                            <button @click="activeTab = 'bad'" :class="['tab-btn', { active: activeTab === 'bad' }]">
                                ⚠️ Counter mich
                            </button>
                            <button @click="activeTab = 'good'" :class="['tab-btn', { active: activeTab === 'good' }]">
                                ✅ Ich countere
                            </button>
                            <button @click="activeTab = 'synergy'" :class="['tab-btn', { active: activeTab === 'synergy' }]">
                                🤝 Synergien
                            </button>
                        </div>

                        <div v-if="activeTab === 'bad'" class="tab-pane">
                            <div class="split-grid">
                                <div class="data-col">
                                    <h4>Statistisch</h4>
                                    <div v-for="(m, i) in countersByDelta" :key="i" class="list-item">
                                        <span class="rank">{{ i+1 }}</span>
                                        <img :src="championStore.getChampionIconUrl(m.name || '')" class="list-icon"/>
                                        <span class="name">{{ m.name }}</span>
                                        <div class="stats">
                                            <span :class="['wr', getWinrateClass(m.winrate)]">{{ formatWinrate(m.winrate) }}</span>
                                            <span :class="['delta', getDeltaClass(m.delta)]">{{ formatDelta(m.delta) }}</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="data-col">
                                    <h4>Skill</h4>
                                    <div v-for="(m, i) in countersByNormalized" :key="i" class="list-item">
                                        <span class="rank">{{ i+1 }}</span>
                                        <img :src="championStore.getChampionIconUrl(m.name || '')" class="list-icon"/>
                                        <span class="name">{{ m.name }}</span>
                                        <div class="stats">
                                            <span :class="['wr', getWinrateClass(m.winrate)]">{{ formatWinrate(m.winrate) }}</span>
                                            <span :class="['delta', getDeltaClass(m.normalized_delta)]">{{ formatDelta(m.normalized_delta) }}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div v-if="activeTab === 'good'" class="tab-pane">
                            <div class="split-grid">
                                <div class="data-col good">
                                    <h4>Statistisch</h4>
                                    <div v-for="(m, i) in iCounterByDelta" :key="i" class="list-item">
                                        <span class="rank">{{ i+1 }}</span>
                                        <img :src="championStore.getChampionIconUrl(m.name || '')" class="list-icon"/>
                                        <span class="name">{{ m.name }}</span>
                                        <div class="stats">
                                            <span :class="['wr', getWinrateClass(m.winrate)]">{{ formatWinrate(m.winrate) }}</span>
                                            <span :class="['delta', getDeltaClass(m.delta)]">{{ formatDelta(m.delta) }}</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="data-col good">
                                    <h4>Skill</h4>
                                    <div v-for="(m, i) in iCounterByNormalized" :key="i" class="list-item">
                                        <span class="rank">{{ i+1 }}</span>
                                        <img :src="championStore.getChampionIconUrl(m.name || '')" class="list-icon"/>
                                        <span class="name">{{ m.name }}</span>
                                        <div class="stats">
                                            <span :class="['wr', getWinrateClass(m.winrate)]">{{ formatWinrate(m.winrate) }}</span>
                                            <span :class="['delta', getDeltaClass(m.normalized_delta)]">{{ formatDelta(m.normalized_delta) }}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div v-if="activeTab === 'synergy'" class="tab-pane">
                            <div class="split-grid">
                                <div class="data-col synergy">
                                    <div v-for="(s, i) in synergiesLeft" :key="i" class="list-item">
                                        <span class="rank">{{ i+1 }}</span>
                                        <img :src="championStore.getChampionIconUrl(s.name || '')" class="list-icon"/>
                                        <span class="name">{{ s.name }}</span>
                                        <div class="stats">
                                            <span :class="['wr', getWinrateClass(s.winrate)]">{{ formatWinrate(s.winrate) }}</span>
                                            <span :class="['delta', getDeltaClass(s.delta)]">{{ formatDelta(s.delta) }}</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="data-col synergy">
                                    <div v-for="(s, i) in synergiesRight" :key="i" class="list-item">
                                        <span class="rank">{{ i+6 }}</span>
                                        <img :src="championStore.getChampionIconUrl(s.name || '')" class="list-icon"/>
                                        <span class="name">{{ s.name }}</span>
                                        <div class="stats">
                                            <span :class="['wr', getWinrateClass(s.winrate)]">{{ formatWinrate(s.winrate) }}</span>
                                            <span :class="['delta', getDeltaClass(s.delta)]">{{ formatDelta(s.delta) }}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div v-else-if="isAnalysisLoading" class="loading-state">
                        Lade Daten...
                    </div>
                    
                    <div v-else class="empty-analysis">
                        Wähle einen Champion aus deinen Empfehlungen oder suche manuell.
                    </div>
                </div>
            </div>
        </div>

        <DraftSummaryCard
            v-if="draftStore.lastCompletedDraft && draftStore.showDraftSummary"
            :summary="draftStore.lastCompletedDraft"
            @close="draftStore.closeDraftSummary()"
        />

        <button 
            v-if="draftStore.lastCompletedDraft && !draftStore.showDraftSummary"
            class="show-summary-btn"
            @click="draftStore.showDraftSummary = true"
        >
            Letzte Partie anzeigen
        </button>
    </div>
</template>

<style scoped>
.draft-tracker-view {
    max-width: 1400px; /* Breiter, da wir jetzt 2 Spalten haben */
    margin: 0 auto;
    padding-bottom: 2rem;
}

.draft-container {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    margin: 1.5rem 0;
}

/* --- SPLIT LAYOUT (NEU) --- */
.content-split-layout {
    display: grid;
    grid-template-columns: 1fr 1fr; /* 50% 50% Split */
    gap: 1.5rem;
    align-items: start; /* Oben bündig */
    margin-top: 1.5rem;
}

/* Responsiveness: Auf kleinen Screens untereinander */
@media (max-width: 1100px) {
    .content-split-layout {
        grid-template-columns: 1fr;
    }
}
@media (max-width: 768px) {
    .draft-container { grid-template-columns: 1fr; }
}

/* Analysis Styles */
.analysis-section-wrapper {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    overflow: hidden;
    height: 100%; /* Füllt die Höhe der Spalte */
}

.analysis-header-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
}

.analysis-main-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
}

.analysis-search { position: relative; width: 180px; }
.analysis-input {
    width: 100%;
    padding: 0.35rem 0.75rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-size: 0.85rem;
}

.suggestions-popover {
    position: absolute;
    top: 100%; left: 0; right: 0;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    z-index: 50;
    max-height: 200px; overflow-y: auto;
}
.suggestion-row { padding: 0.5rem; cursor: pointer; font-size: 0.9rem; }
.suggestion-row:hover { background: var(--bg-tertiary); }

.analysis-content-box { padding: 1rem; }
.champion-badge { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }
.champ-icon-small { width: 36px; height: 36px; border-radius: 50%; border: 2px solid var(--primary); }
.champ-info { display: flex; flex-direction: column; }
.champ-name { font-weight: bold; font-size: 0.95rem; }
.champ-role { font-size: 0.75rem; color: var(--text-muted); }

.tabs-nav {
    display: flex; gap: 0.5rem;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 0.75rem;
}
.tab-btn {
    background: transparent; border: none; padding: 0.5rem 0.75rem;
    color: var(--text-secondary); cursor: pointer;
    border-bottom: 2px solid transparent; font-size: 0.9rem;
}
.tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }

.split-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
}
@media (max-width: 500px) { .split-grid { grid-template-columns: 1fr; } }

.data-col h4 { margin: 0 0 0.5rem 0; font-size: 0.8rem; color: var(--text-muted); }

.list-item {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.35rem; background: var(--bg-tertiary);
    margin-bottom: 0.25rem; border-radius: 4px; font-size: 0.85rem;
}
.list-icon { width: 20px; height: 20px; border-radius: 50%; }
.name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stats { display: flex; gap: 0.5rem; margin-left: auto; }
.wr, .delta { font-weight: 600; width: 40px; text-align: right; }
.wr.good { color: #60a5fa; }
.wr.poor { color: #f87171; }
.delta.positive { color: #4ade80; }
.delta.negative { color: #f87171; }

.empty-analysis, .loading-state { padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.9rem; }
.draft-complete-msg { padding: 2rem; text-align: center; color: var(--text-muted); background: var(--bg-secondary); border-radius: var(--radius-lg); border: 1px solid var(--border-color); }
.show-summary-btn { display: block; width: 100%; padding: 0.75rem; margin: 2rem 0; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-secondary); cursor: pointer; }
</style>
