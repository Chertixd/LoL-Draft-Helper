<script setup lang="ts">
/**
 * DisconnectedBanner -- non-modal banner shown when backend exits unexpectedly (FRONT-03)
 *
 * Appears when:
 *  - Tauri 'backend-disconnected' event fires, OR
 *  - Socket.IO fails to reconnect after 3 attempts
 *
 * In non-Tauri mode (browser dev), the Restart button is hidden since the
 * user must manually restart `python backend.py`.
 */
import { ref, onMounted } from 'vue'

const isTauri = ref(false)
const restarting = ref(false)

onMounted(() => {
    isTauri.value = '__TAURI__' in window
})

async function restart() {
    if (!('__TAURI__' in window)) return
    restarting.value = true
    try {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('restart_backend')
        // Frontend state will reset via the 'backend-ready' event listener
    } catch (err) {
        console.error('[DisconnectedBanner] Restart failed:', err)
        restarting.value = false
    }
}
</script>

<template>
    <div class="disconnected-banner" role="alert">
        <span class="banner-icon">!</span>
        <span class="banner-text">Backend stopped unexpectedly.</span>
        <button
            v-if="isTauri"
            class="banner-restart-btn"
            :disabled="restarting"
            @click="restart"
        >
            {{ restarting ? 'Restarting...' : 'Restart' }}
        </button>
        <span v-else class="banner-hint">
            Please restart the backend manually.
        </span>
    </div>
</template>

<style scoped>
.disconnected-banner {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.625rem 1.25rem;
    background: rgba(239, 68, 68, 0.15);
    border-bottom: 2px solid var(--error);
    color: var(--text-primary);
    font-size: 0.875rem;
}

.banner-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--error);
    color: #fff;
    font-size: 0.75rem;
    font-weight: 700;
    flex-shrink: 0;
}

.banner-text {
    font-weight: 600;
}

.banner-hint {
    color: var(--text-secondary);
    font-size: 0.8rem;
}

.banner-restart-btn {
    margin-left: auto;
    padding: 0.3rem 0.75rem;
    background: var(--error);
    color: #fff;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity var(--transition-fast);
}

.banner-restart-btn:hover:not(:disabled) {
    opacity: 0.85;
}

.banner-restart-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}
</style>
