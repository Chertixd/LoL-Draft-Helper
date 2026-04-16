<script setup lang="ts">
/**
 * CdnProgressView -- full-screen view during first-run CDN data download (UX-01, UX-02)
 *
 * Polls /api/status every 1 second during the loading phase. When phase
 * becomes "ready", emits 'cdn-ready' so the parent can transition state.
 *
 * If the app is in 'offline-no-cache' state, shows an error with a Retry
 * button that reloads the page.
 */
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useAppStatusStore } from '@/stores/appStatus'
import { checkBackendHealth } from '@/api/backend'

const appStatus = useAppStatusStore()

const emit = defineEmits<{
    (e: 'cdn-ready'): void
}>()

const isOffline = computed(() => appStatus.state === 'offline-no-cache')
const progressPercent = computed(() => {
    const total = appStatus.cdnProgress.total
    if (total <= 0) return 0
    return Math.round((appStatus.cdnProgress.done / total) * 100)
})

let pollTimer: ReturnType<typeof setInterval> | null = null

async function pollStatus() {
    try {
        // Use the /api/status endpoint for CDN progress
        const response = await fetch(
            (await getApiBase()) + '/status'
        )
        if (!response.ok) return
        const data = await response.json()

        if (data.phase === 'warming') {
            appStatus.setLoading(data.done ?? 0, data.total ?? 9)
        } else if (data.phase === 'ready' || data.phase === 'idle') {
            appStatus.cdnProgress.done = data.total ?? 9
            appStatus.cdnProgress.total = data.total ?? 9
            emit('cdn-ready')
            stopPolling()
        } else if (data.phase === 'error') {
            appStatus.setOffline(false)
            stopPolling()
        }
    } catch {
        // Backend not reachable yet -- keep polling
    }
}

/** Resolve base URL once for polling */
let _apiBase: string | null = null
async function getApiBase(): Promise<string> {
    if (!_apiBase) {
        const { getBackendURL } = await import('@/api/client')
        _apiBase = await getBackendURL()
    }
    return _apiBase + '/api'
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
    }
}

function retry() {
    window.location.reload()
}

onMounted(() => {
    pollStatus()
    pollTimer = setInterval(pollStatus, 1000)
})

onUnmounted(() => {
    stopPolling()
})
</script>

<template>
    <div class="cdn-progress-view">
        <div class="cdn-progress-content">
            <!-- Error state: offline with no cache -->
            <template v-if="isOffline">
                <div class="cdn-error-icon">!</div>
                <h2 class="cdn-progress-title">Cannot load champion data</h2>
                <p class="cdn-progress-hint">
                    Check your internet connection and try again.
                </p>
                <button class="cdn-retry-btn" @click="retry">Retry</button>
            </template>

            <!-- Loading state: CDN download in progress -->
            <template v-else>
                <div class="cdn-spinner"></div>
                <h2 class="cdn-progress-title">Downloading champion data...</h2>
                <div class="cdn-progress-bar-container">
                    <div
                        class="cdn-progress-bar-fill"
                        :style="{ width: progressPercent + '%' }"
                    ></div>
                </div>
                <p class="cdn-progress-count">
                    {{ appStatus.cdnProgress.done }} / {{ appStatus.cdnProgress.total }} tables
                </p>
            </template>
        </div>
    </div>
</template>

<style scoped>
.cdn-progress-view {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 50vh;
}

.cdn-progress-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    text-align: center;
    padding: 2rem;
    max-width: 360px;
}

.cdn-spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: cdn-spin 0.8s linear infinite;
}

@keyframes cdn-spin {
    to { transform: rotate(360deg); }
}

.cdn-error-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--error);
    color: #fff;
    font-size: 1.25rem;
    font-weight: 700;
}

.cdn-progress-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
}

.cdn-progress-hint {
    font-size: 0.875rem;
    color: var(--text-muted);
    margin: 0;
}

.cdn-progress-bar-container {
    width: 100%;
    height: 6px;
    background: var(--bg-tertiary);
    border-radius: 3px;
    overflow: hidden;
}

.cdn-progress-bar-fill {
    height: 100%;
    background: var(--primary);
    border-radius: 3px;
    transition: width 0.3s ease;
}

.cdn-progress-count {
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin: 0;
}

.cdn-retry-btn {
    padding: 0.5rem 1.5rem;
    background: var(--primary);
    color: #fff;
    border: none;
    border-radius: var(--radius-md);
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity var(--transition-fast);
}

.cdn-retry-btn:hover {
    opacity: 0.85;
}
</style>
