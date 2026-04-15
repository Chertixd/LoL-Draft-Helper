<script setup lang="ts">
import { computed } from 'vue';
import { useChampionStore } from '@/stores/champion';
import { useDraftStore } from '@/stores/draft';
import type { DraftPick, DraftBan, PickScore, Role } from '@counterpick/core';
import { getRoleDisplayName } from '@counterpick/core';
import PickRoleSelector from './PickRoleSelector.vue';

interface PickDisplayInfo {
    name: string;
    icon: string;
    status: 'empty' | 'picking' | 'hovering' | 'locked';
    scoreInfo: PickScore | null;
    role?: Role;
    cellId?: number;
    pick?: DraftPick;
    confidenceClass?: string;
    lockTypeIcon?: string;
}

const props = defineProps<{
    teamName: string;
    picks: DraftPick[];
    bans: DraftBan[];
    side: 'blue' | 'red' | 'neutral';
    isMyTeam?: boolean;
}>();

const championStore = useChampionStore();
const draftStore = useDraftStore();

/**
 * Computed property das alle Pick-Slots mit ihren Display-Informationen berechnet.
 * Reaktiv auf pickScores-Änderungen!
 */
const pickDisplaySlots = computed<PickDisplayInfo[]>(() => {
    // Explizit auf pickScores zugreifen für Reaktivität
    const scores = draftStore.pickScores;
    
    const slots: PickDisplayInfo[] = [];
    for (let i = 0; i < 5; i++) {
        const pick = props.picks[i] || null;
        slots.push(getPickDisplay(pick, scores));
    }
    return slots;
});

/**
 * Bestimmt die Confidence-Klasse basierend auf der roleConfidence
 */
function getConfidenceClass(pick: DraftPick): string {
    if (!pick.roleConfidence) return '';
    if (pick.roleConfidence >= 0.7) return 'high-confidence';
    if (pick.roleConfidence >= 0.4) return 'medium-confidence';
    return 'low-confidence';
}

/**
 * Gibt das Lock-Typ-Icon zurück
 */
function getLockTypeIcon(pick: DraftPick): string {
    switch (pick.roleLockType) {
        case 'auto': return '🔐'; // LCU Auto-Lock (unüberschreibbar)
        case 'manual': return '🔒'; // Manuell gesetzt
        case 'prediction': return '🎯'; // Prediction
        default: return '';
    }
}

function getPickDisplay(pick: DraftPick | null, scores: Record<string, PickScore>): PickDisplayInfo {
    if (!pick) {
        return { name: '', icon: '', status: 'empty', scoreInfo: null };
    }
    
    const baseInfo = {
        role: pick.role,
        cellId: pick.cellId,
        pick: pick,
        confidenceClass: getConfidenceClass(pick),
        lockTypeIcon: getLockTypeIcon(pick)
    };
    
    if (pick.isLocked && pick.champion) {
        const scoreInfo = scores[pick.champion] || null;
        return {
            name: pick.champion,
            icon: championStore.getChampionIconUrl(pick.champion),
            status: 'locked',
            scoreInfo,
            ...baseInfo
        };
    }
    
    if (pick.hoverChampion) {
        return {
            name: pick.hoverChampion,
            icon: championStore.getChampionIconUrl(pick.hoverChampion),
            status: 'hovering',
            scoreInfo: null,
            ...baseInfo
        };
    }
    
    // Zeige auch leere Slots mit Rolle an (wichtig für Rollenprediction)
    if (pick.role) {
        return { 
            name: '', 
            icon: '', 
            status: 'picking', 
            scoreInfo: null,
            ...baseInfo
        };
    }
    
    return { name: '', icon: '', status: 'empty', scoreInfo: null, ...baseInfo };
}

/**
 * Berechnet die Score-Farbe basierend auf dem Score-Wert (0-100)
 */
function getScoreColor(score: number): string {
    if (score >= 70) return 'score-high';
    if (score >= 50) return 'score-medium';
    return 'score-low';
}

/**
 * Gibt den Kurznamen einer Rolle zurück
 */
function getRoleShortName(role: string): string {
    const mapping: Record<string, string> = {
        'top': 'Top',
        'jungle': 'Jgl',
        'middle': 'Mid',
        'bottom': 'Bot',
        'support': 'Sup'
    };
    return mapping[role] || role;
}
</script>

<template>
    <div :class="['draft-team', side, { 'my-team': isMyTeam }]">
        <h3 class="team-header">
            {{ teamName }}
            <span v-if="isMyTeam" class="my-team-badge">Mein Team</span>
        </h3>
        
        <div class="picks-list">
            <div 
                v-for="(slot, index) in pickDisplaySlots" 
                :key="index"
                :class="['pick-slot', slot.status, slot.confidenceClass]"
            >
                <!-- Rolle Badge - links anzeigen -->
                <div 
                    v-if="slot.role" 
                    :class="['role-badge', slot.confidenceClass]" 
                    :title="`Rolle: ${getRoleDisplayName(slot.role)}${slot.pick?.roleConfidence ? ` (${Math.round(slot.pick.roleConfidence * 100)}%)` : ''}`"
                >
                    {{ getRoleShortName(slot.role) }}
                    <span v-if="slot.lockTypeIcon" class="lock-type-icon">{{ slot.lockTypeIcon }}</span>
                </div>
                <div v-else class="role-badge role-badge-empty">?</div>
                
                <template v-if="slot.status === 'locked' || slot.status === 'hovering'">
                    <img 
                        :src="slot.icon"
                        :alt="slot.name"
                        class="pick-icon"
                    />
                    <div class="pick-info">
                        <div class="pick-name-row">
                            <span class="pick-name">{{ slot.name }}</span>
                            <!-- Confidence Badge für High-Confidence -->
                            <span 
                                v-if="slot.pick?.roleConfidence && slot.pick.roleConfidence >= 0.7" 
                                class="confidence-badge high"
                                :title="`${Math.round(slot.pick.roleConfidence * 100)}% sicher`"
                            >
                                {{ Math.round(slot.pick.roleConfidence * 100) }}%
                            </span>
                        </div>
                        <span v-if="slot.status === 'hovering'" class="pick-status">
                            Hovering...
                        </span>
                        <!-- Rollen-Auswahl für gelockte/gehoverte Champions -->
                        <PickRoleSelector 
                            v-if="slot.pick && slot.cellId !== undefined"
                            :pick="slot.pick"
                            :cell-id="slot.cellId"
                            :team="side === 'blue' ? 'team1' : 'team2'"
                        />
                    </div>
                    <!-- Pick Score Badge - nur für gelockte Champions -->
                    <div 
                        v-if="slot.status === 'locked' && slot.scoreInfo"
                        :class="['pick-score-badge', getScoreColor(slot.scoreInfo.score)]"
                        :title="`Score: ${slot.scoreInfo.score} | Base: ${slot.scoreInfo.baseScore ?? '-'} | Counter: ${slot.scoreInfo.counterScore ?? '-'} | Synergy: ${slot.scoreInfo.synergyScore ?? '-'} | WR: ${slot.scoreInfo.winrate}%`"
                    >
                        {{ slot.scoreInfo.score.toFixed(0) }}
                    </div>
                </template>
                <template v-else-if="slot.status === 'picking'">
                    <div class="pick-placeholder picking">
                        <span class="picking-indicator"></span>
                    </div>
                    <div class="pick-info">
                        <span class="pick-status">Wählt...</span>
                        <!-- Rollen-Auswahl auch für pickende Spieler (falls cellId vorhanden) -->
                        <PickRoleSelector 
                            v-if="slot.pick && slot.cellId !== undefined"
                            :pick="slot.pick"
                            :cell-id="slot.cellId"
                            :team="side === 'blue' ? 'team1' : 'team2'"
                        />
                    </div>
                </template>
                <template v-else>
                    <div class="pick-placeholder empty"></div>
                    <span class="pick-status empty-text">-</span>
                </template>
            </div>
        </div>
        
        <div v-if="bans.length > 0" class="bans-section">
            <h4 class="bans-title">Bans</h4>
            <div class="bans-list">
                <div 
                    v-for="(ban, index) in bans" 
                    :key="index"
                    class="ban-item"
                    :title="ban.champion"
                >
                    <img 
                        v-if="ban.champion"
                        :src="championStore.getChampionIconUrl(ban.champion)"
                        :alt="ban.champion"
                        class="ban-icon"
                    />
                    <div v-else class="ban-placeholder"></div>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.draft-team {
    background: var(--bg-secondary);
    border-radius: var(--radius-lg);
    overflow: hidden;
}

.draft-team.blue {
    border: 2px solid #3b82f6;
}

.draft-team.red {
    border: 2px solid #ef4444;
}

.draft-team.neutral {
    border: 2px solid #6b7280;
}

.draft-team.my-team {
    box-shadow: 0 0 20px rgba(102, 126, 234, 0.3);
}

.team-header {
    padding: 0.75rem 1rem;
    margin: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: white;
    font-size: 1rem;
}

.draft-team.blue .team-header {
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
}

.draft-team.red .team-header {
    background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
}

.draft-team.neutral .team-header {
    background: linear-gradient(135deg, #4b5563 0%, #6b7280 100%);
}

.my-team-badge {
    font-size: 0.7rem;
    padding: 0.125rem 0.5rem;
    background: rgba(255,255,255,0.2);
    border-radius: var(--radius-full);
}

.picks-list {
    padding: 0;
}

.pick-slot {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    min-height: 56px;
}

.pick-slot:last-child {
    border-bottom: none;
}

.pick-slot.locked {
    background: var(--bg-primary);
}

.pick-slot.hovering {
    background: rgba(102, 126, 234, 0.1);
}

.pick-slot.picking {
    background: rgba(245, 158, 11, 0.1);
}

.pick-icon {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid var(--border-color);
}

.pick-slot.locked .pick-icon {
    border-color: var(--success);
}

.pick-slot.hovering .pick-icon {
    border-color: var(--primary);
    opacity: 0.7;
}

.pick-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    flex: 1;
}

.pick-name {
    font-weight: 600;
}

.pick-name-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* Role Badge */
.role-badge {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    color: white;
    font-size: 0.65rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    text-transform: uppercase;
    position: relative;
}

/* Confidence-basierte Role Badge Farben */
.role-badge.high-confidence {
    background: linear-gradient(135deg, #059669 0%, #10b981 100%);
    box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
}

.role-badge.medium-confidence {
    background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%);
}

.role-badge.low-confidence {
    background: linear-gradient(135deg, #6b7280 0%, #9ca3af 100%);
}

.role-badge-empty {
    background: var(--bg-tertiary);
    color: var(--text-muted);
    border: 2px dashed var(--border-color);
}

.lock-type-icon {
    position: absolute;
    top: -4px;
    right: -4px;
    font-size: 0.5rem;
    background: var(--bg-primary);
    border-radius: 50%;
    width: 14px;
    height: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* Confidence Badge */
.confidence-badge {
    font-size: 0.65rem;
    padding: 0.125rem 0.375rem;
    border-radius: var(--radius-full);
    font-weight: 600;
}

.confidence-badge.high {
    background: linear-gradient(135deg, #059669 0%, #10b981 100%);
    color: white;
}

/* High-Confidence Pick Slot Highlight */
.pick-slot.high-confidence {
    background: rgba(16, 185, 129, 0.08);
    border-left: 3px solid #10b981;
}

/* Pick Score Badge */
.pick-score-badge {
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-md);
    font-size: 0.75rem;
    font-weight: 700;
    min-width: 36px;
    text-align: center;
    margin-left: auto;
}

.pick-score-badge.score-high {
    background: linear-gradient(135deg, #059669 0%, #10b981 100%);
    color: white;
}

.pick-score-badge.score-medium {
    background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%);
    color: white;
}

.pick-score-badge.score-low {
    background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
    color: white;
}

.pick-status {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
}

.pick-placeholder {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--bg-tertiary);
    border: 2px dashed var(--border-color);
}

.pick-placeholder.picking {
    border-color: var(--warning);
    background: rgba(245, 158, 11, 0.2);
    position: relative;
}

.picking-indicator {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 10px;
    height: 10px;
    background: var(--warning);
    border-radius: 50%;
    animation: pulse 1s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    50% { opacity: 0.5; transform: translate(-50%, -50%) scale(0.8); }
}

.empty-text {
    color: var(--text-muted);
}

.bans-section {
    padding: 0.75rem 1rem;
    background: var(--bg-tertiary);
    border-top: 1px solid var(--border-color);
}

.bans-title {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0 0 0.5rem 0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.bans-list {
    display: flex;
    gap: 0.5rem;
}

.ban-item {
    position: relative;
}

.ban-icon {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    object-fit: cover;
    filter: grayscale(50%);
    opacity: 0.7;
}

.ban-icon::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, transparent 40%, rgba(239, 68, 68, 0.5) 50%, transparent 60%);
}

.ban-placeholder {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--bg-secondary);
    border: 1px dashed var(--border-color);
}
</style>

