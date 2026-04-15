<script setup lang="ts">
import { computed } from 'vue';
import { useChampionStore } from '@/stores/champion';
import type { DraftPick, PickScore, Role } from '@counterpick/core';
import { getRoleDisplayName } from '@counterpick/core';

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

const props = defineProps<{
    summary: DraftSummary;
}>();

const emit = defineEmits<{
    (e: 'close'): void;
}>();

const championStore = useChampionStore();

/**
 * Formatiert Timestamp als deutsches Datum
 */
const formattedDate = computed(() => {
    const date = new Date(props.summary.timestamp);
    return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
});

/**
 * Durchschnittlicher Score pro Team
 */
const myTeamAverage = computed(() => {
    const lockedCount = props.summary.myTeamPicks.filter(p => p.isLocked && p.champion).length;
    return lockedCount > 0 ? (props.summary.myTeamTotalScore / lockedCount).toFixed(1) : '0';
});

const enemyTeamAverage = computed(() => {
    const lockedCount = props.summary.enemyTeamPicks.filter(p => p.isLocked && p.champion).length;
    return lockedCount > 0 ? (props.summary.enemyTeamTotalScore / lockedCount).toFixed(1) : '0';
});

/**
 * Score-Differenz pro Pick
 */
const scoreDifferencePerPick = computed(() => {
    return (props.summary.scoreDifference / 5).toFixed(1);
});

/**
 * Bestimmt die Klasse für die Score-Differenz
 */
const scoreDifferenceClass = computed(() => {
    if (props.summary.scoreDifference > 10) return 'advantage';
    if (props.summary.scoreDifference < -10) return 'disadvantage';
    return 'neutral';
});

/**
 * Gibt den Kurznamen einer Rolle zurück
 */
function getRoleShortName(role: Role | undefined): string {
    if (!role) return '?';
    const mapping: Record<string, string> = {
        'top': 'Top',
        'jungle': 'Jgl',
        'middle': 'Mid',
        'bottom': 'Bot',
        'support': 'Sup'
    };
    return mapping[role] || role;
}

/**
 * Holt den Score für einen Champion
 */
function getChampionScore(champion: string): number | null {
    const score = props.summary.pickScores[champion];
    return score ? score.score : null;
}

/**
 * Gibt die Score-Farbe zurück
 */
function getScoreColor(score: number | null): string {
    if (score === null) return '';
    if (score >= 70) return 'score-high';
    if (score >= 50) return 'score-medium';
    return 'score-low';
}
</script>

<template>
    <div class="draft-summary-card">
        <div class="summary-header">
            <h3 class="summary-title">Letzte Partie</h3>
            <span class="summary-date">{{ formattedDate }}</span>
            <button class="close-button" @click="emit('close')" title="Schließen">
                ×
            </button>
        </div>
        
        <div class="teams-container">
            <!-- Mein Team -->
            <div :class="['team-column', summary.myTeamSide]">
                <h4 class="team-title">
                    Mein Team ({{ summary.myTeamSide === 'blue' ? 'Blue' : 'Red' }} Side)
                </h4>
                <div class="picks-list">
                    <div 
                        v-for="(pick, index) in summary.myTeamPicks.filter(p => p.isLocked && p.champion)" 
                        :key="index"
                        class="pick-row"
                    >
                        <img 
                            v-if="pick.champion"
                            :src="championStore.getChampionIconUrl(pick.champion)"
                            :alt="pick.champion"
                            class="champion-icon"
                        />
                        <div class="pick-info">
                            <span class="champion-name">{{ pick.champion }}</span>
                            <span class="role-badge">{{ getRoleShortName(pick.role) }}</span>
                        </div>
                        <span 
                            v-if="getChampionScore(pick.champion) !== null"
                            :class="['pick-score', getScoreColor(getChampionScore(pick.champion))]"
                        >
                            {{ getChampionScore(pick.champion)?.toFixed(0) }}
                        </span>
                    </div>
                </div>
                <div class="team-total">
                    <span>Gesamt: {{ summary.myTeamTotalScore.toFixed(0) }}</span>
                    <span class="average">(Ø {{ myTeamAverage }})</span>
                </div>
            </div>
            
            <!-- Gegner Team -->
            <div :class="['team-column', summary.myTeamSide === 'blue' ? 'red' : 'blue']">
                <h4 class="team-title">
                    Gegner Team ({{ summary.myTeamSide === 'blue' ? 'Red' : 'Blue' }} Side)
                </h4>
                <div class="picks-list">
                    <div 
                        v-for="(pick, index) in summary.enemyTeamPicks.filter(p => p.isLocked && p.champion)" 
                        :key="index"
                        class="pick-row"
                    >
                        <img 
                            v-if="pick.champion"
                            :src="championStore.getChampionIconUrl(pick.champion)"
                            :alt="pick.champion"
                            class="champion-icon"
                        />
                        <div class="pick-info">
                            <span class="champion-name">{{ pick.champion }}</span>
                            <span class="role-badge">{{ getRoleShortName(pick.role) }}</span>
                        </div>
                        <span 
                            v-if="getChampionScore(pick.champion) !== null"
                            :class="['pick-score', getScoreColor(getChampionScore(pick.champion))]"
                        >
                            {{ getChampionScore(pick.champion)?.toFixed(0) }}
                        </span>
                    </div>
                </div>
                <div class="team-total">
                    <span>Gesamt: {{ summary.enemyTeamTotalScore.toFixed(0) }}</span>
                    <span class="average">(Ø {{ enemyTeamAverage }})</span>
                </div>
            </div>
        </div>
        
        <!-- Score-Differenz -->
        <div :class="['score-difference', scoreDifferenceClass]">
            <template v-if="summary.scoreDifference > 0">
                Draft-Vorteil: +{{ summary.scoreDifference.toFixed(0) }} (+{{ scoreDifferencePerPick }} pro Pick)
            </template>
            <template v-else-if="summary.scoreDifference < 0">
                Draft-Nachteil: {{ summary.scoreDifference.toFixed(0) }} ({{ scoreDifferencePerPick }} pro Pick)
            </template>
            <template v-else>
                Draft ausgeglichen
            </template>
        </div>
    </div>
</template>

<style scoped>
.draft-summary-card {
    background: var(--bg-secondary);
    border-radius: var(--radius-lg);
    overflow: hidden;
    border: 2px solid var(--border-color);
}

.summary-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 1rem;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
}

.summary-title {
    margin: 0;
    font-size: 1rem;
    color: var(--text-primary);
}

.summary-date {
    color: var(--text-muted);
    font-size: 0.875rem;
    flex: 1;
}

.close-button {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0;
    line-height: 1;
    transition: color 0.2s;
}

.close-button:hover {
    color: var(--text-primary);
}

.teams-container {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: var(--border-color);
}

.team-column {
    background: var(--bg-secondary);
    padding: 1rem;
}

.team-column.blue {
    border-top: 3px solid #3b82f6;
}

.team-column.red {
    border-top: 3px solid #ef4444;
}

.team-title {
    margin: 0 0 0.75rem 0;
    font-size: 0.875rem;
    color: var(--text-secondary);
    text-align: center;
}

.picks-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.pick-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem;
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
}

.champion-icon {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    object-fit: cover;
}

.pick-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
}

.champion-name {
    font-size: 0.875rem;
    font-weight: 500;
}

.role-badge {
    font-size: 0.65rem;
    padding: 0.125rem 0.375rem;
    background: var(--bg-primary);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
}

.pick-score {
    font-size: 0.75rem;
    font-weight: 700;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-sm);
    min-width: 32px;
    text-align: center;
}

.pick-score.score-high {
    background: linear-gradient(135deg, #059669 0%, #10b981 100%);
    color: white;
}

.pick-score.score-medium {
    background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%);
    color: white;
}

.pick-score.score-low {
    background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
    color: white;
}

.team-total {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-color);
    text-align: center;
    font-weight: 600;
    font-size: 0.875rem;
}

.team-total .average {
    color: var(--text-muted);
    font-weight: 400;
    margin-left: 0.25rem;
}

.score-difference {
    padding: 1rem;
    text-align: center;
    font-weight: 600;
    font-size: 1rem;
    border-top: 1px solid var(--border-color);
}

.score-difference.advantage {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.1) 100%);
    color: #10b981;
}

.score-difference.disadvantage {
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.1) 100%);
    color: #ef4444;
}

.score-difference.neutral {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
}

@media (max-width: 768px) {
    .teams-container {
        grid-template-columns: 1fr;
    }
}
</style>


