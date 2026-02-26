<script setup lang="ts">
import { computed } from 'vue';
import type { Role } from '@counterpick/core';
import { getRoleDisplayName } from '@counterpick/core';

const props = defineProps<{
    modelValue: Role | null;
}>();

const emit = defineEmits<{
    'update:modelValue': [value: Role];
}>();

const roles: { id: Role; label: string; short: string }[] = [
    { id: 'top', label: 'Top', short: 'Top' },
    { id: 'jungle', label: 'Jungle', short: 'Jgl' },
    { id: 'middle', label: 'Mid', short: 'Mid' },
    { id: 'bottom', label: 'Bot', short: 'Bot' },
    { id: 'support', label: 'Support', short: 'Sup' }
];

const selectedRole = computed(() => props.modelValue);

function selectRole(role: Role) {
    emit('update:modelValue', role);
}

function isRoleActive(role: Role): boolean {
    return selectedRole.value === role;
}
</script>

<template>
    <div class="role-selector">
        <span class="selector-label">Meine Rolle:</span>
        <div class="role-buttons">
            <button
                v-for="role in roles"
                :key="role.id"
                :class="['role-btn', { active: isRoleActive(role.id) }]"
                :title="`${role.label} auswählen`"
                @click="selectRole(role.id)"
            >
                {{ role.short }}
            </button>
        </div>
        <span v-if="!selectedRole" class="hint-text">
            Wähle eine Rolle für Pick-Empfehlungen
        </span>
    </div>
</template>

<style scoped>
.role-selector {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    flex-wrap: wrap;
}

.selector-label {
    font-weight: 500;
    color: var(--text-secondary);
    white-space: nowrap;
}

.role-buttons {
    display: flex;
    gap: 0.375rem;
}

.role-btn {
    padding: 0.5rem 0.875rem;
    border: 2px solid var(--border-color);
    border-radius: var(--radius-md);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-weight: 500;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all var(--transition-fast);
    display: flex;
    align-items: center;
    gap: 0.25rem;
}

.role-btn:hover {
    border-color: var(--primary);
    color: var(--primary);
}

.role-btn.active {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    color: white;
    border-color: transparent;
}

.hint-text {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
}
</style>
