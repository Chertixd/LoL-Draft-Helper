<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { RouterView, RouterLink } from 'vue-router';
import { checkBackendHealth, getLeagueClientStatus } from '@/api/backend';
import { initBackendListeners } from '@/api/client';
import { checkForUpdates } from '@/updater';
import { useDraftStore } from '@/stores/draft';
import { useSettingsStore } from '@/stores/settings';
import { useAppStatusStore } from '@/stores/appStatus';
import PatchSelector from '@/components/common/PatchSelector.vue';
import DisconnectedBanner from '@/components/ui/DisconnectedBanner.vue';
import LolWaitingView from '@/components/ui/LolWaitingView.vue';
import StalenessIndicator from '@/components/ui/StalenessIndicator.vue';
import CdnProgressView from '@/components/ui/CdnProgressView.vue';

const draftStore = useDraftStore();
const settingsStore = useSettingsStore();
const appStatus = useAppStatusStore();

// Legacy backend status (retained for footer badge display)
const backendStatus = ref<'checking' | 'online' | 'offline'>('checking');

// League Client Status aus dem draftStore
const leagueClientStatus = computed(() => {
    if (!draftStore.websocketConnected) return 'offline';
    if (draftStore.leagueClientConnected) return 'online';
    return 'waiting';
});

/** Handle transition when CDN download finishes */
async function onCdnReady() {
    try {
        const lcStatus = await getLeagueClientStatus();
        if (lcStatus.client_running) {
            appStatus.setRunning();
        } else {
            appStatus.setWaitingForLol();
        }
    } catch {
        appStatus.setWaitingForLol();
    }
}

/** Handle transition when LoL client connects */
function onLolConnected() {
    appStatus.setRunning();
}

onMounted(async () => {
    // Initialize Tauri event listeners (backend-ready, backend-disconnected)
    await initBackendListeners();

    // Check for updates after backend is ready (2s delay for sidecar startup)
    setTimeout(() => {
        checkForUpdates();
    }, 2000);

    // Set up backend-disconnected handler for Tauri
    if ('__TAURI__' in window) {
        const { listen } = await import('@tauri-apps/api/event');
        await listen('backend-disconnected', () => {
            appStatus.setDisconnected();
            backendStatus.value = 'offline';
        });
    }

    try {
        const response = await checkBackendHealth();
        if (response.status === 'ok') {
            backendStatus.value = 'online';
            appStatus.setConnected();

            // Check cache staleness from health response
            const cached = (response as Record<string, unknown>).cached;
            if (cached && typeof cached === 'object') {
                const entries = Object.values(cached as Record<string, unknown>);
                // stale_status returns Dict[str, bool] -- count stale vs total
                const staleCount = entries.filter(v => v === true).length;
                // Estimate age: if any table is stale, mark > 48h as a heuristic
                const oldestHours = staleCount > 0 ? 72 : 0;
                appStatus.updateCacheStatus({
                    oldest_fetch_hours: oldestHours,
                    newest_fetch_iso: null,
                });
            }

            // Check status endpoint for CDN warm-up phase
            try {
                const { getBackendURL } = await import('@/api/client');
                const statusResp = await fetch(
                    (await getBackendURL()) + '/api/status'
                );
                if (statusResp.ok) {
                    const statusData = await statusResp.json();
                    if (statusData.phase === 'warming') {
                        appStatus.setLoading(statusData.done ?? 0, statusData.total ?? 9);
                        // CdnProgressView will take over polling
                        settingsStore.loadPatches();
                        return;
                    }
                }
            } catch {
                // /api/status not reachable; proceed to LoL check
            }

            // Check League Client status
            const lcStatus = await getLeagueClientStatus();
            if (lcStatus.client_running) {
                appStatus.setRunning();
            } else {
                appStatus.setWaitingForLol();
            }
        } else {
            backendStatus.value = 'offline';
            appStatus.setDisconnected();
        }
    } catch {
        backendStatus.value = 'offline';
        appStatus.setDisconnected();
    }

    settingsStore.loadPatches();
});
</script>

<template>
    <div class="app-container">
        <!-- Disconnected banner at top (non-modal) -->
        <DisconnectedBanner v-if="appStatus.state === 'disconnected'" />

        <header class="app-header">
            <div class="header-content">
                <div class="header-row">
                    <div class="header-left">
                        <h1 class="app-title">
                            <span class="title-gradient">Counterpick</span>
                            <span class="title-subtitle">Draft Analyzer</span>
                        </h1>

                        <div class="nav-divider"></div>

                        <nav class="app-nav">
                            <RouterLink to="/draft" class="nav-link">Draft Tracker</RouterLink>
                            <RouterLink to="/lookup" class="nav-link">Champion Lookup</RouterLink>
                        </nav>
                    </div>

                    <div class="header-right">
                        <PatchSelector :horizontal="true" />
                    </div>
                </div>
            </div>
        </header>

        <main class="app-content">
            <!-- Full-screen states -->
            <CdnProgressView
                v-if="appStatus.state === 'loading' || appStatus.state === 'offline-no-cache'"
                @cdn-ready="onCdnReady"
            />
            <template v-else-if="appStatus.state === 'waiting-for-lol'">
                <LolWaitingView @lol-connected="onLolConnected" />
                <!-- Keep RouterView in DOM so draft state is preserved -->
                <div style="display: none;">
                    <RouterView />
                </div>
            </template>
            <!-- Normal content -->
            <template v-else>
                <RouterView />
            </template>
        </main>

        <footer class="app-footer">
            <StalenessIndicator
                v-if="appStatus.staleSeverity !== 'none'"
                :severity="appStatus.staleSeverity"
                :lastFetchDate="appStatus.cacheStatus.newest_fetch_iso"
            />
            <span :class="['status-badge', backendStatus]">
                <span class="status-dot"></span>
                Backend: {{
                    backendStatus === 'checking' ? 'Checking...' :
                    backendStatus === 'online' ? 'Online' : 'Offline'
                }}
            </span>
            <span :class="['status-badge', leagueClientStatus]">
                <span class="status-dot"></span>
                League Client: {{
                    leagueClientStatus === 'online' ? 'Online' :
                    leagueClientStatus === 'waiting' ? 'Waiting...' : 'Offline'
                }}
            </span>
        </footer>
    </div>
</template>

<style scoped>
.app-container {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

/* --- HEADER STYLES --- */
.app-header {
    /* Viel weniger Padding für kompakten Look */
    padding: 0.75rem 2rem;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    height: 64px; /* Fixierte Höhe verhindert Springen */
    display: flex;
    align-items: center;
}

.header-content {
    width: 100%;
    max-width: 1400px; /* Breiter für mehr Platz */
    margin: 0 auto;
}

.header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 1.5rem; /* Abstand zwischen Logo und Nav */
}

/* Logo Bereich */
.app-title {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin: 0;
    line-height: 1;
}

.title-gradient {
    font-size: 1.25rem; /* Deutlich kleiner */
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.title-subtitle {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Trennlinie */
.nav-divider {
    width: 1px;
    height: 24px;
    background: var(--border-color);
}

/* Navigation */
.app-nav {
    display: flex;
    gap: 0.5rem;
}

.nav-link {
    padding: 0.4rem 0.8rem;
    border-radius: var(--radius-md);
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-secondary);
    text-decoration: none;
    transition: all var(--transition-fast);
}

.nav-link:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
}

.nav-link.router-link-active {
    color: var(--primary);
    background: rgba(102, 126, 234, 0.1);
    font-weight: 600;
}

/* Mobile Responsive */
@media (max-width: 768px) {
    .app-header {
        height: auto;
        padding: 1rem;
    }

    .header-row {
        flex-direction: column;
        align-items: stretch;
        gap: 1rem;
    }

    .header-left {
        flex-direction: column;
        align-items: center;
        gap: 0.75rem;
    }

    .nav-divider {
        display: none;
    }

    .header-right {
        display: flex;
        justify-content: center;
    }
}

/* --- MAIN & FOOTER --- */
.app-content {
    flex: 1;
    padding: 1.5rem 2rem;
    max-width: 1400px; /* Passend zum Header */
    width: 100%;
    margin: 0 auto;
    position: relative;
}

.app-footer {
    padding: 0.5rem 2rem;
    border-top: 1px solid var(--border-color);
    display: flex;
    justify-content: center;
    gap: 1.5rem;
    background: var(--bg-secondary); /* Footer auch dunkel abgesetzt */
}

.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem; /* Kleinerer Footer Text */
    color: var(--text-secondary);
}

.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-muted);
}

.status-badge.online .status-dot { background: var(--success); }
.status-badge.offline .status-dot { background: var(--error); }
.status-badge.checking .status-dot,
.status-badge.waiting .status-dot {
    background: var(--warning);
    animation: pulse 1s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
</style>
