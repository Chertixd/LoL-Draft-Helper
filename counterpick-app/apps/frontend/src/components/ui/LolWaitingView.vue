<script setup lang="ts">
/**
 * LolWaitingView -- full-screen overlay when League Client is not running (FRONT-04)
 *
 * Polls /api/league-client/status every 3 seconds. When client_running
 * becomes true, emits 'lol-connected' so the parent can transition state.
 *
 * This overlays the <RouterView> content rather than removing it from the
 * DOM, so draft state is preserved if the LoL client briefly disconnects.
 */
import { onMounted, onUnmounted } from 'vue'
import { getLeagueClientStatus } from '@/api/backend'

const emit = defineEmits<{
    (e: 'lol-connected'): void
}>()

let pollTimer: ReturnType<typeof setInterval> | null = null

async function checkClient() {
    try {
        const result = await getLeagueClientStatus()
        if (result.client_running) {
            emit('lol-connected')
        }
    } catch {
        // Backend unreachable -- parent handles disconnected state
    }
}

onMounted(() => {
    // Initial check
    checkClient()
    // Poll every 3 seconds
    pollTimer = setInterval(checkClient, 3000)
})

onUnmounted(() => {
    if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
    }
})
</script>

<template>
    <div class="lol-waiting-overlay">
        <div class="lol-waiting-content">
            <div class="lol-waiting-pulse"></div>
            <h2 class="lol-waiting-title">Waiting for League of Legends...</h2>
            <p class="lol-waiting-hint">
                Start the League Client to begin analyzing your draft.
            </p>
        </div>
    </div>
</template>

<style scoped>
.lol-waiting-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.04);
    z-index: 10;
}

.lol-waiting-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    text-align: center;
    padding: 2rem;
}

.lol-waiting-pulse {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--warning);
    animation: lol-pulse 1.5s ease-in-out infinite;
}

@keyframes lol-pulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.6); opacity: 0.4; }
}

.lol-waiting-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
}

.lol-waiting-hint {
    font-size: 0.875rem;
    color: var(--text-muted);
    margin: 0;
    max-width: 300px;
}
</style>
