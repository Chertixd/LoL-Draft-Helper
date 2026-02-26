<script setup lang="ts">
import { computed, ref } from 'vue';
import { RANK_OPTIONS } from '@counterpick/core';

const props = defineProps<{
    modelValue: string;
}>();

const emit = defineEmits<{
    'update:modelValue': [value: string];
}>();

const rankOptions = RANK_OPTIONS;

const selectedRank = computed({
    get: () => props.modelValue,
    set: (value: string) => emit('update:modelValue', value)
});

// Rank Icon URL (lokale Dateien)
function getRankIconUrl(rank: string): string {
    if (!rank || rank === 'all') return '';
    const rankName = rank.charAt(0).toUpperCase() + rank.slice(1);
    return `/assets/ranks/Rank=${rankName}.png`;
}

const currentRankIcon = computed(() => getRankIconUrl(selectedRank.value));

// Fehlerhandling für Bilder
const imageError = ref(false);
function onImageError() {
    imageError.value = true;
}
</script>

<template>
    <div class="rank-selector">
        <label for="rank-select" class="selector-label">Elo/Rank:</label>
        <div class="selector-wrapper">
            <select 
                id="rank-select"
                v-model="selectedRank"
                class="rank-select"
            >
                <option 
                    v-for="option in rankOptions" 
                    :key="option.value"
                    :value="option.value"
                >
                    {{ option.label }}
                </option>
            </select>
            <img 
                v-if="currentRankIcon && !imageError"
                :src="currentRankIcon"
                :alt="selectedRank"
                class="rank-icon"
                @error="onImageError"
            />
        </div>
    </div>
</template>

<style scoped>
.rank-selector {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
}

.selector-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-secondary);
}

.selector-wrapper {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.rank-select {
    padding: 0.75rem 1rem;
    border: 2px solid var(--border-color);
    border-radius: var(--radius-md);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 1rem;
    min-width: 180px;
    cursor: pointer;
    transition: border-color var(--transition-fast);
}

.rank-select:focus {
    outline: none;
    border-color: var(--primary);
}

.rank-select:hover {
    border-color: var(--primary-light);
}

.rank-icon {
    width: 40px;
    height: 40px;
    object-fit: contain;
}
</style>
