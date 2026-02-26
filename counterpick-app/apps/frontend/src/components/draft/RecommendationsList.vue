<script setup lang="ts">
import { computed } from 'vue';
import { useChampionStore } from '@/stores/champion';
import type { RecommendationItem, Role } from '@counterpick/core';
import { getRoleDisplayName } from '@counterpick/core';

const props = defineProps<{
    recommendations: RecommendationItem[];
    loading?: boolean;
    error?: string | null;
    maxItems?: number;
    selectedRole?: Role | null;
    pickedChampion?: string | null;
    enemyPickedChampion?: string | null;
}>();

const emit = defineEmits<{
    'refresh': [];
}>();

const championStore = useChampionStore();

const displayItems = computed(() => {
    const max = props.maxItems || 10;
    return props.recommendations.slice(0, max);
});

/**
 * Bestimmt den Status für die Anzeige
 */
const displayStatus = computed(() => {
    if (props.loading) return 'loading';
    
    // Spezielle Fehlercodes
    if (props.error === 'no_role') return 'no_role';
    if (props.error === 'already_picked') return 'already_picked';
    if (props.error) return 'error';
    
    if (displayItems.value.length === 0) return 'empty';
    
    return 'ready';
});

/**
 * Formatierte Fehlermeldung
 */
const errorMessage = computed(() => {
    if (!props.error) return '';
    if (props.error === 'no_role' || props.error === 'already_picked') return '';
    return props.error;
});

function getScoreClass(score: number): string {
    if (score >= 70) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 50) return 'average';
    return 'below-average';
}

function formatScore(score: number): string {
    return score.toFixed(1);
}
</script>

<template>
    <div class="recommendations-list">
        <div class="list-header">
            <h3 class="list-title">
                <span class="title-icon">⭐</span>
                Pick-Empfehlungen
                <span v-if="selectedRole" class="role-badge">
                    {{ getRoleDisplayName(selectedRole) }}
                </span>
            </h3>
            <button 
                class="refresh-btn" 
                @click="emit('refresh')" 
                :disabled="loading || displayStatus === 'no_role' || displayStatus === 'already_picked'"
            >
                <span :class="{ spinning: loading }">🔄</span>
                Aktualisieren
            </button>
        </div>
        
        <!-- Loading State -->
        <div v-if="displayStatus === 'loading'" class="list-loading">
            <span class="loading-spinner"></span>
            <span>Lade Empfehlungen...</span>
        </div>
        
        <!-- Keine Rolle ausgewählt -->
        <div v-else-if="displayStatus === 'no_role'" class="list-state no-role">
            <div class="state-icon">🎯</div>
            <h4 class="state-title">Keine Rolle ausgewählt</h4>
            <p class="state-description">
                Wähle oben deine Rolle aus, um personalisierte Pick-Empfehlungen zu erhalten.
            </p>
        </div>
        
        <!-- Bereits gepickt (beide Teams haben für die Rolle gepickt) -->
        <div v-else-if="displayStatus === 'already_picked'" class="list-state already-picked">
            <div class="state-icon">✅</div>
            <h4 class="state-title">Matchup komplett!</h4>
            <div class="matchup-display">
                <div class="matchup-side ally">
                    <span class="matchup-label">Dein Pick</span>
                    <strong class="matchup-champion">{{ pickedChampion || '?' }}</strong>
                </div>
                <span class="matchup-vs">vs</span>
                <div class="matchup-side enemy">
                    <span class="matchup-label">Gegner</span>
                    <strong class="matchup-champion">{{ enemyPickedChampion || '?' }}</strong>
                </div>
            </div>
            <p v-if="selectedRole" class="state-role">
                {{ getRoleDisplayName(selectedRole) }}
            </p>
            <p class="state-hint">
                Beide Teams haben für diese Rolle gepickt. Viel Erfolg!
            </p>
        </div>
        
        <!-- Fehler -->
        <div v-else-if="displayStatus === 'error'" class="list-error">
            <span class="error-icon">⚠️</span>
            {{ errorMessage }}
        </div>
        
        <!-- Keine Empfehlungen -->
        <div v-else-if="displayStatus === 'empty'" class="list-empty">
            <p>Keine Empfehlungen verfügbar.</p>
            <p class="hint">Warte auf gepickte Champions im Draft.</p>
        </div>
        
        <!-- Empfehlungen anzeigen -->
        <div v-else class="recommendations-grid">
            <div 
                v-for="(rec, index) in displayItems" 
                :key="rec.championKey"
                :class="['recommendation-card', getScoreClass(rec.score)]"
            >
                <div class="card-rank">{{ index + 1 }}</div>
                
                <img 
                    :src="championStore.getChampionIconUrl(rec.championKey)"
                    :alt="rec.championKey"
                    class="card-icon"
                />
                
                <div class="card-info">
                    <span class="card-name">{{ rec.championKey }}</span>
                    <span class="card-winrate">{{ rec.winrate.toFixed(1) }}% WR</span>
                </div>
                
                <div class="card-score">
                    <span class="score-value">{{ formatScore(rec.score) }}</span>
                    <span class="score-label">Score</span>
                </div>
                
                <div class="card-breakdown">
                    <div class="breakdown-item" title="Base Score">
                        <span class="breakdown-label">B</span>
                        <span class="breakdown-value">{{ formatScore(rec.baseScore) }}</span>
                    </div>
                    <div class="breakdown-item counter" title="Counter Score">
                        <span class="breakdown-label">C</span>
                        <span class="breakdown-value">{{ formatScore(rec.counterScore) }}</span>
                    </div>
                    <div class="breakdown-item synergy" title="Synergy Score">
                        <span class="breakdown-label">S</span>
                        <span class="breakdown-value">{{ formatScore(rec.synergyScore) }}</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div v-if="recommendations.length > 0" class="list-legend">
            <span class="legend-item">
                <strong>B</strong> = Base Score (Champion-Stärke)
            </span>
            <span class="legend-item">
                <strong>C</strong> = Counter Score (vs Gegner)
            </span>
            <span class="legend-item">
                <strong>S</strong> = Synergy Score (mit Team)
            </span>
        </div>
    </div>
</template>

<style scoped>
.recommendations-list {
    background: var(--bg-secondary);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
}

.list-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.list-title {
    margin: 0;
    font-size: 1.125rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.title-icon {
    font-size: 1.25rem;
}

.role-badge {
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
    background: var(--primary);
    color: white;
    border-radius: var(--radius-full);
    font-weight: 500;
}

.refresh-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 0.875rem;
    cursor: pointer;
    transition: background-color var(--transition-fast);
}

.refresh-btn:hover:not(:disabled) {
    background: var(--primary-dark);
}

.refresh-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

.spinning {
    display: inline-block;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.list-loading,
.list-error,
.list-empty {
    padding: 2rem;
    text-align: center;
    color: var(--text-secondary);
}

.list-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
}

.loading-spinner {
    width: 20px;
    height: 20px;
    border: 2px solid var(--border-color);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

.list-error {
    color: var(--error);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
}

.list-empty .hint {
    font-size: 0.875rem;
    color: var(--text-muted);
    margin-top: 0.5rem;
}

/* State displays */
.list-state {
    padding: 2.5rem 1.5rem;
    text-align: center;
    border-radius: var(--radius-md);
}

.list-state.no-role {
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
    border: 1px dashed var(--primary);
}

.list-state.already-picked {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.1) 100%);
    border: 1px solid var(--success);
}

.state-icon {
    font-size: 2.5rem;
    margin-bottom: 0.75rem;
}

.state-title {
    margin: 0 0 0.5rem 0;
    font-size: 1.125rem;
    color: var(--text-primary);
}

.state-description {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.state-description strong {
    color: var(--primary);
}

.already-picked .state-description strong {
    color: var(--success);
}

.state-hint {
    margin: 0.75rem 0 0 0;
    font-size: 0.8rem;
    color: var(--text-muted);
    font-style: italic;
}

.state-role {
    margin: 0.5rem 0 0 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Matchup Display für "bereits gepickt" */
.matchup-display {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    margin: 1rem 0;
    padding: 0.75rem;
    background: rgba(0, 0, 0, 0.2);
    border-radius: var(--radius-md);
}

.matchup-side {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 1rem;
    border-radius: var(--radius-sm);
}

.matchup-side.ally {
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.2) 0%, rgba(59, 130, 246, 0.1) 100%);
    border: 1px solid rgba(59, 130, 246, 0.3);
}

.matchup-side.enemy {
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(220, 38, 38, 0.1) 100%);
    border: 1px solid rgba(239, 68, 68, 0.3);
}

.matchup-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
}

.matchup-champion {
    font-size: 1rem;
    color: var(--text-primary);
}

.matchup-side.ally .matchup-champion {
    color: #60a5fa;
}

.matchup-side.enemy .matchup-champion {
    color: #f87171;
}

.matchup-vs {
    font-size: 1.25rem;
    font-weight: bold;
    color: var(--text-muted);
    text-transform: uppercase;
}

.recommendations-grid {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.recommendation-card {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--bg-primary);
    border-radius: var(--radius-md);
    border-left: 4px solid var(--border-color);
    transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}

.recommendation-card:hover {
    transform: translateX(4px);
    box-shadow: var(--shadow-sm);
}

.recommendation-card.excellent {
    border-left-color: #22c55e;
}

.recommendation-card.good {
    border-left-color: #3b82f6;
}

.recommendation-card.average {
    border-left-color: #f59e0b;
}

.recommendation-card.below-average {
    border-left-color: var(--text-muted);
}

.card-rank {
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

.card-icon {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid var(--border-color);
}

.card-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
}

.card-name {
    font-weight: 600;
}

.card-winrate {
    font-size: 0.75rem;
    color: var(--text-secondary);
}

.card-score {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 50px;
}

.score-value {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--primary);
}

.score-label {
    font-size: 0.625rem;
    color: var(--text-muted);
    text-transform: uppercase;
}

.card-breakdown {
    display: flex;
    gap: 0.375rem;
}

.breakdown-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0.25rem 0.375rem;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    min-width: 32px;
}

.breakdown-item.counter .breakdown-value {
    color: #ef4444;
}

.breakdown-item.synergy .breakdown-value {
    color: #22c55e;
}

.breakdown-label {
    font-size: 0.625rem;
    color: var(--text-muted);
    font-weight: 600;
}

.breakdown-value {
    font-size: 0.75rem;
    font-weight: 600;
}

.list-legend {
    display: flex;
    gap: 1rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
    font-size: 0.75rem;
    color: var(--text-muted);
    flex-wrap: wrap;
}
</style>
