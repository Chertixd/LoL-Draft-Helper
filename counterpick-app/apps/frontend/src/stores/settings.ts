/**
 * Settings Store - Verwaltet App-Einstellungen
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { RANK_OPTIONS, DEFAULT_RANK } from '@counterpick/core';
import { getAvailablePatches } from '@/api/backend';

export const useSettingsStore = defineStore('settings', () => {
    // State
    const selectedRank = ref<string>(DEFAULT_RANK);
    const selectedPatch = ref<string>('');  // Leer = aktueller Patch
    const selectedRole = ref<string>('');   // Leer = Auto

    // Patch-Optionen (werden dynamisch aktualisiert)
    const patchOptions = ref<string[]>(['15.24', '15.23', '15.22']);
    const patchesLoading = ref(false);

    // Computed: Gibt selectedPatch zurück, oder den neuesten Patch wenn leer
    const currentPatch = computed(() => {
        if (selectedPatch.value) {
            return selectedPatch.value;
        }
        // Neuester Patch ist der erste in der Liste (sortiert DESC)
        return patchOptions.value[0] || '';
    });

    // Actions
    function setRank(rank: string) {
        selectedRank.value = rank;
    }

    function setPatch(patch: string) {
        selectedPatch.value = patch;
    }

    function setRole(role: string) {
        selectedRole.value = role;
    }

    // Lade verfügbare Patches aus Supabase
    async function loadPatches() {
        if (patchesLoading.value) return;
        patchesLoading.value = true;
        
        try {
            const response = await getAvailablePatches();
            if (response.success && response.patches) {
                patchOptions.value = response.patches;
                // Wenn kein Patch ausgewählt ist, setze automatisch den neuesten
                if (!selectedPatch.value && patchOptions.value.length > 0) {
                    selectedPatch.value = patchOptions.value[0];
                }
            } else {
                // Fallback auf hardcodierte Patches
                patchOptions.value = ['16.1', '15.24', '15.23', '15.22'];
                if (!selectedPatch.value && patchOptions.value.length > 0) {
                    selectedPatch.value = patchOptions.value[0];
                }
            }
        } catch (error) {
            console.error('Fehler beim Laden der Patches:', error);
            // Fallback auf hardcodierte Patches
            patchOptions.value = ['16.1', '15.24', '15.23', '15.22'];
            if (!selectedPatch.value && patchOptions.value.length > 0) {
                selectedPatch.value = patchOptions.value[0];
            }
        } finally {
            patchesLoading.value = false;
        }
    }

    // Rank Display Name
    function getRankDisplayName(rank: string): string {
        const option = RANK_OPTIONS.find(r => r.value === rank);
        return option?.label || rank;
    }

    // Rank Icon URL (lokale Datei)
    function getRankIconUrl(rank: string): string {
        if (!rank || rank === 'all') return '';
        const rankName = rank.charAt(0).toUpperCase() + rank.slice(1);
        // Nutzt lokale dragontail-Dateien
        return `/assets/ranks/Rank=${rankName}.png`;
    }

    return {
        // State
        selectedRank,
        selectedPatch,
        selectedRole,
        patchOptions,
        patchesLoading,
        currentPatch,
        
        // Actions
        setRank,
        setPatch,
        setRole,
        loadPatches,
        getRankDisplayName,
        getRankIconUrl
    };
});

