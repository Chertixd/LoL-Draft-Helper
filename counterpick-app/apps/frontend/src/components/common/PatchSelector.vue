<script setup lang="ts">
import { computed } from 'vue';
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();

// Optionale Props für externe Verwendung (falls benötigt)
const props = defineProps<{
    modelValue?: string;
    patches?: string[];
    horizontal?: boolean; // Horizontal Layout für Header-Integration
}>();

const emit = defineEmits<{
    'update:modelValue': [value: string];
}>();

// Nutze Settings Store, falls keine Props übergeben werden
const patchOptions = computed(() => props.patches || settingsStore.patchOptions);

const selectedPatch = computed({
    get: () => props.modelValue !== undefined ? props.modelValue : settingsStore.selectedPatch,
    set: (value: string) => {
        if (props.modelValue !== undefined) {
            emit('update:modelValue', value);
        } else {
            settingsStore.setPatch(value);
        }
    }
});
</script>

<template>
    <div :class="['patch-selector', { 'patch-selector-horizontal': horizontal }]">
        <label for="patch-select" class="selector-label">Patch:</label>
        <select 
            id="patch-select"
            v-model="selectedPatch"
            class="patch-select"
        >
            <option 
                v-for="patch in patchOptions" 
                :key="patch"
                :value="patch"
            >
                {{ patch }}
            </option>
        </select>
    </div>
</template>

<style scoped>
.patch-selector {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
}

.patch-selector-horizontal {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
}

.selector-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-secondary);
    white-space: nowrap;
}

.patch-select {
    padding: 0.75rem 1rem;
    border: 2px solid var(--border-color);
    border-radius: var(--radius-md);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 1rem;
    min-width: 120px;
    cursor: pointer;
    transition: border-color var(--transition-fast);
}

.patch-select:focus {
    outline: none;
    border-color: var(--primary);
}

.patch-select:hover {
    border-color: var(--primary-light);
}
</style>

