/**
 * Champion Store - Verwaltet Champion-Daten und Suche
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getChampionsList, getPrimaryRoles } from '@/api/backend';

export interface ChampionData {
    id: string;
    key: string;
    name: string;
    title?: string;
}

export const useChampionStore = defineStore('champion', () => {
    // State
    const championsList = ref<string[]>([]);
    const primaryRoles = ref<Record<string, string>>({});
    const championData = ref<Record<string, ChampionData>>({});
    const currentVersion = ref<string>('');
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    // Getters
    const championsLoaded = computed(() => championsList.value.length > 0);

    // Actions
    async function loadChampionData() {
        if (isLoading.value) return;
        isLoading.value = true;
        error.value = null;

        try {
            // Lade Champions-Liste
            const listResponse = await getChampionsList();
            if (listResponse.success) {
                championsList.value = listResponse.champions;
            }

            // Lade Primary Roles
            const rolesResponse = await getPrimaryRoles();
            if (rolesResponse.success) {
                primaryRoles.value = rolesResponse.primary_roles;
            }

            // Lade Champion-Daten von Data Dragon
            const versionResponse = await fetch('https://ddragon.leagueoflegends.com/api/versions.json');
            const versions = await versionResponse.json();
            currentVersion.value = versions[0];

            const championsUrl = `https://ddragon.leagueoflegends.com/cdn/${currentVersion.value}/data/de_DE/champion.json`;
            const championsResponse = await fetch(championsUrl);
            const championsJson = await championsResponse.json();
            championData.value = championsJson.data;

        } catch (e) {
            error.value = e instanceof Error ? e.message : 'Unbekannter Fehler';
            console.error('Fehler beim Laden der Champion-Daten:', e);
        } finally {
            isLoading.value = false;
        }
    }

    /**
     * Normalisiert Champion-Namen für Vergleiche
     */
    function normalizeChampionName(name: string): string {
        return name.toLowerCase()
            .replace(/'/g, '')
            .replace(/\s+/g, '')
            .replace(/\./g, '');
    }

    /**
     * Findet validen Champion-Namen
     */
    function getValidChampionName(input: string): string | null {
        const normalizedInput = normalizeChampionName(input);
        
        for (const champName of championsList.value) {
            if (normalizeChampionName(champName) === normalizedInput) {
                return champName;
            }
        }
        return null;
    }

    /**
     * Sucht Champions basierend auf Input
     */
    function searchChampions(input: string, limit = 8): string[] {
        if (!input || input.length < 1) return [];
        
        const normalizedInput = normalizeChampionName(input);
        const matches: string[] = [];

        for (const champName of championsList.value) {
            const normalizedChamp = normalizeChampionName(champName);
            if (normalizedChamp.includes(normalizedInput) || normalizedChamp.startsWith(normalizedInput)) {
                matches.push(champName);
                if (matches.length >= limit) break;
            }
        }

        return matches;
    }

    /**
     * Spezielle Mapping für Dateinamen (Wukong -> MonkeyKing, etc.)
     */
    const specialFileNames: Record<string, string> = {
        'wukong': 'MonkeyKing',
        'nunuwillump': 'Nunu',
        'renataglasc': 'Renata',
        'ksante': 'KSante'
    };

    /**
     * Holt Champion-Icon-URL (mit lokalem Fallback)
     */
    function getChampionIconUrl(championName: string): string {
        const normalizedInput = normalizeChampionName(championName);
        
        // Prüfe spezielle Mappings
        const specialName = specialFileNames[normalizedInput];
        if (specialName) {
            // Nutze lokale Assets
            return `/assets/champions/${specialName}.png`;
        }
        
        // Suche in Champion-Daten
        if (championData.value && Object.keys(championData.value).length > 0) {
            for (const [key, champ] of Object.entries(championData.value)) {
                const normalizedName = normalizeChampionName(champ.name);
                const normalizedId = normalizeChampionName(champ.id);
                
                if (normalizedName === normalizedInput || normalizedId === normalizedInput) {
                    // Nutze lokale Assets (schneller und offline verfügbar)
                    return `/assets/champions/${champ.id}.png`;
                }
            }
        }
        
        // Fallback: Versuche direkten Namen
        const directName = championName.split(' ').map(word => 
            word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
        ).join('').replace(/'/g, '');
        
        return `/assets/champions/${directName}.png`;
    }

    /**
     * Holt Splash-Art URL für Champion (Data Dragon, da Splashes groß sind)
     */
    function getChampionSplashUrl(championName: string): string {
        const normalizedInput = normalizeChampionName(championName);
        
        // Prüfe spezielle Mappings
        const specialName = specialFileNames[normalizedInput];
        if (specialName) {
            return `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/${specialName}_0.jpg`;
        }
        
        if (championData.value && Object.keys(championData.value).length > 0) {
            for (const [key, champ] of Object.entries(championData.value)) {
                const normalizedName = normalizeChampionName(champ.name);
                const normalizedId = normalizeChampionName(champ.id);
                
                if (normalizedName === normalizedInput || normalizedId === normalizedInput) {
                    return `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/${champ.id}_0.jpg`;
                }
            }
        }
        
        return '';
    }
    
    /**
     * Holt Rank-Icon-URL (lokal)
     */
    function getRankIconUrl(rank: string): string {
        if (!rank || rank === 'all') return '';
        const rankName = rank.charAt(0).toUpperCase() + rank.slice(1);
        return `/assets/ranks/Rank=${rankName}.png`;
    }

    /**
     * Prüft ob Champion Multi-Role ist
     */
    function isMultiRoleChampion(championName: string): boolean {
        // Champions die auf mehreren Lanes gespielt werden
        const multiRoleChamps = [
            'Akali', 'Ambessa', 'Aurora', 'Brand', 'Cassiopeia', 'Diana', 'Ekko', 
            'Elise', 'Evelynn', 'Fiddlesticks', 'Fizz', 'Gragas', 'Heimerdinger', 
            'Hwei', 'Ivern', 'Jayce', 'Karma', 'Karthus', 'Kayn', 'Kennen', 
            'Kindred', 'Lee Sin', 'Lillia', 'Lissandra', 'Lulu', 'Lux', 
            'Maokai', 'Mel', 'Morgana', 'Neeko', 'Nidalee', 'Nocturne', 'Nunu & Willump',
            'Pantheon', 'Qiyana', 'Rumble', 'Ryze', 'Seraphine', 'Sett', 'Shaco', 
            'Shen', 'Shyvana', 'Sion', 'Smolder', 'Swain', 'Sylas', 'Syndra', 
            'Tahm Kench', 'Taliyah', 'Talon', 'Taric', 'Teemo', 'Twisted Fate', 
            'Varus', 'Vel\'Koz', 'Vi', 'Viego', 'Vladimir', 'Volibear', 'Wukong', 
            'Xerath', 'Xin Zhao', 'Yasuo', 'Yone', 'Zac', 'Zed', 'Ziggs', 'Zilean', 'Zyra'
        ];
        
        return multiRoleChamps.some(champ => 
            normalizeChampionName(champ) === normalizeChampionName(championName)
        );
    }

    /**
     * Holt Primary Role für Champion
     */
    function getPrimaryRole(championName: string): string | null {
        const normalized = normalizeChampionName(championName);
        
        for (const [champ, role] of Object.entries(primaryRoles.value)) {
            if (normalizeChampionName(champ) === normalized) {
                return role;
            }
        }
        return null;
    }

    return {
        // State
        championsList,
        primaryRoles,
        championData,
        currentVersion,
        isLoading,
        error,
        
        // Getters
        championsLoaded,
        
        // Actions
        loadChampionData,
        normalizeChampionName,
        getValidChampionName,
        searchChampions,
        getChampionIconUrl,
        getChampionSplashUrl,
        getRankIconUrl,
        isMultiRoleChampion,
        getPrimaryRole
    };
});

