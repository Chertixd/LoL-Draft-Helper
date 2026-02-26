<script setup lang="ts">
import { computed } from 'vue';
import { useDraftStore } from '@/stores/draft';
import type { DraftPick, Role, RoleLockType } from '@counterpick/core';
import { getRoleDisplayName } from '@counterpick/core';

const props = defineProps<{
    pick: DraftPick;
    cellId: number;
    team: 'team1' | 'team2';
}>();

const draftStore = useDraftStore();

const roles: Role[] = ['top', 'jungle', 'middle', 'bottom', 'support'];

// Prüft ob dies das Gegner-Team ist
const isEnemyTeam = computed(() => {
    if (!draftStore.myTeam) return false;
    return props.team !== draftStore.myTeam;
});

// Prüft ob eine manuelle Rolle gesetzt ist
const hasManualOverride = computed(() => draftStore.hasManualRoleOverride(props.cellId));

// Aktuelle Rolle (manuell oder predicted)
const currentRole = computed(() => props.pick.role);

// Predicted Rolle vom Backend
const predictedRole = computed(() => props.pick.predictedRole);

// Lock-Typ für den Pick
const lockType = computed(() => props.pick.roleLockType || 'none');

// Gelockte Rollen im Team
const lockedRoles = computed(() => draftStore.getLockedRolesForTeam(props.team));

/**
 * Gibt die Wahrscheinlichkeit für eine Rolle zurück (0-100%)
 */
function getRoleProbability(role: Role): number {
    if (!props.pick.roleProbabilities) return 0;
    return Math.round((props.pick.roleProbabilities[role] || 0) * 100);
}

/**
 * Bestimmt die Confidence-Klasse basierend auf der Wahrscheinlichkeit
 */
function getConfidenceClass(role: Role): string {
    const prob = getRoleProbability(role);
    if (prob >= 70) return 'high-confidence';
    if (prob >= 40) return 'medium-confidence';
    return 'low-confidence';
}

/**
 * Prüft ob eine Rolle für diesen Pick verfügbar ist
 */
function isRoleAvailable(role: Role): boolean {
    // Gegner-Team: Rollen sind immer aenderbar (wir kennen ihre echten Rollen nicht)
    if (isEnemyTeam.value) {
        return true;
    }
    
    // Eigenes Team: Normale Pruefung
    return draftStore.isRoleAvailableForPick(role, props.cellId, props.team);
}

/**
 * Gibt den Champion zurück, der eine Rolle blockiert
 */
function getBlockingChampion(role: Role): string | null {
    if (isRoleAvailable(role)) return null;
    return draftStore.getChampionWithRole(role, props.team);
}

/**
 * Setzt oder entfernt eine manuelle Rolle
 */
function toggleRole(role: Role) {
    // Prüfe ob Rolle verfügbar ist
    if (!isRoleAvailable(role)) {
        console.log(`[PickRoleSelector] Rolle ${role} ist nicht verfügbar (belegt von ${getBlockingChampion(role)})`);
        return;
    }
    
    if (hasManualOverride.value && currentRole.value === role) {
        // Entferne manuelle Überschreibung wenn bereits gesetzt
        draftStore.setManualRoleForPick(props.cellId, null);
    } else {
        // Setze manuelle Rolle
        draftStore.setManualRoleForPick(props.cellId, role);
    }
}

/**
 * Bestimmt ob eine Rolle aktiv/ausgewählt ist
 */
function isRoleActive(role: Role): boolean {
    return currentRole.value === role;
}

/**
 * Bestimmt ob eine Rolle die predicted Rolle ist (aber nicht manuell gesetzt)
 */
function isPredictedRole(role: Role): boolean {
    return !hasManualOverride.value && predictedRole.value === role;
}

/**
 * Generiert den Tooltip-Text für eine Rolle
 */
function getRoleTooltip(role: Role): string {
    const prob = getRoleProbability(role);
    const blocking = getBlockingChampion(role);
    
    if (blocking) {
        return `Rolle von ${blocking} belegt`;
    }
    
    if (hasManualOverride.value && isRoleActive(role)) {
        return 'Klicken zum Entsperren';
    }
    
    if (prob > 0) {
        return `${getRoleDisplayName(role)} (${prob}%)`;
    }
    
    return `${getRoleDisplayName(role)} setzen`;
}

/**
 * Gibt Lock-Icon basierend auf Lock-Typ zurück
 */
function getLockIcon(): string {
    switch (lockType.value) {
        case 'auto': return '🔐'; // LCU Auto-Lock
        case 'manual': return '🔒'; // Manuell gesetzt
        case 'prediction': return ''; // Prediction - kein Icon
        default: return '';
    }
}

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
    <div class="pick-role-selector">
        <button
            v-for="role in roles"
            :key="role"
            :class="[
                'role-btn',
                getConfidenceClass(role),
                { 
                    'active': isRoleActive(role),
                    'predicted': isPredictedRole(role) && !isRoleActive(role),
                    'manual': lockType === 'manual' && isRoleActive(role),
                    'auto-lock': lockType === 'auto' && isRoleActive(role),
                    'disabled': (lockType === 'auto' && !isEnemyTeam) || (!isRoleAvailable(role) && !isEnemyTeam)
                }
            ]"
            :disabled="(lockType === 'auto' && !isEnemyTeam) || (!isRoleAvailable(role) && !isEnemyTeam)"
            :title="getRoleTooltip(role)"
            @click="toggleRole(role)"
        >
            <span class="role-content">
                <span class="role-icon">{{ getRoleShortName(role) }}</span>
                <span 
                    v-if="pick.roleProbabilities && getRoleProbability(role) > 0" 
                    class="role-prob"
                >
                    {{ getRoleProbability(role) }}%
                </span>
            </span>
            <span v-if="isRoleActive(role) && getLockIcon()" class="lock-icon">
                {{ getLockIcon() }}
            </span>
        </button>
    </div>
</template>

<style scoped>
.pick-role-selector {
    display: flex;
    gap: 0.25rem;
    padding: 0.25rem;
}

.role-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.125rem;
    padding: 0.25rem 0.4rem;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--bg-tertiary);
    color: var(--text-muted);
    font-size: 0.65rem;
    font-weight: 500;
    cursor: pointer;
    transition: all var(--transition-fast);
    opacity: 0.6;
    min-width: 2.5rem;
    position: relative;
}

.role-btn:hover:not(.disabled) {
    opacity: 1;
    border-color: var(--primary);
    color: var(--text-primary);
}

/* Disabled - Rolle von anderem Champion belegt */
.role-btn.disabled {
    opacity: 0.3;
    cursor: not-allowed;
    background: var(--bg-tertiary);
}

/* Confidence-basierte Farben für nicht-aktive Buttons */
.role-btn.high-confidence:not(.active):not(.disabled) {
    border-color: var(--success);
    color: var(--success);
}

.role-btn.medium-confidence:not(.active):not(.disabled) {
    border-color: var(--warning);
    color: var(--warning);
}

.role-btn.low-confidence:not(.active):not(.disabled) {
    border-color: var(--text-muted);
    color: var(--text-muted);
    opacity: 0.5;
}

/* Predicted Rolle (nicht manuell gesetzt) */
.role-btn.predicted {
    opacity: 0.9;
    border-color: var(--primary);
    color: var(--primary);
    background: rgba(102, 126, 234, 0.1);
}

/* Aktive/ausgewählte Rolle */
.role-btn.active {
    opacity: 1;
    background: var(--primary);
    border-color: var(--primary);
    color: white;
}

/* Manuell gesetzte Rolle */
.role-btn.manual {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    border-color: transparent;
    box-shadow: 0 2px 4px rgba(102, 126, 234, 0.3);
}

/* Auto-Lock (LCU) - höchste Priorität */
.role-btn.auto-lock {
    background: linear-gradient(135deg, var(--success) 0%, #059669 100%);
    border-color: transparent;
    box-shadow: 0 2px 4px rgba(16, 185, 129, 0.3);
    cursor: default;
}

.role-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.0625rem;
}

.role-icon {
    font-weight: 600;
    font-size: 0.7rem;
}

.role-prob {
    font-size: 0.55rem;
    opacity: 0.8;
}

.role-btn.active .role-prob {
    opacity: 1;
}

.lock-icon {
    position: absolute;
    top: -0.25rem;
    right: -0.25rem;
    font-size: 0.5rem;
    background: var(--bg-primary);
    border-radius: 50%;
    padding: 0.0625rem;
}
</style>
