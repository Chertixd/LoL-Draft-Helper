/**
 * App Status Store -- tracks application connectivity state (D-07)
 *
 * Four UX states:
 * 1. waiting-for-lol: backend connected, LCU not detected
 * 2. disconnected: backend exited or unreachable
 * 3. loading: first-run CDN download in progress
 * 4. running: normal operation (with optional staleness indicator)
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type AppState =
    | 'initializing'      // app just started
    | 'loading'           // first-run CDN download
    | 'waiting-for-lol'   // backend ok, LCU absent
    | 'running'           // normal operation
    | 'disconnected'      // backend exited
    | 'offline-no-cache'  // CDN unreachable, no cache
    | 'offline-stale'     // CDN unreachable, using stale cache

export interface CacheStatus {
    oldest_fetch_hours: number | null
    newest_fetch_iso: string | null
}

export const useAppStatusStore = defineStore('appStatus', () => {
    const state = ref<AppState>('initializing')
    const cacheStatus = ref<CacheStatus>({ oldest_fetch_hours: null, newest_fetch_iso: null })
    const cdnProgress = ref<{ done: number; total: number }>({ done: 0, total: 0 })
    const disconnectCount = ref(0)

    const isStale = computed(() => {
        if (cacheStatus.value.oldest_fetch_hours === null) return false
        return cacheStatus.value.oldest_fetch_hours > 48
    })

    const staleSeverity = computed((): 'none' | 'amber' | 'red' => {
        const hours = cacheStatus.value.oldest_fetch_hours
        if (hours === null || hours <= 48) return 'none'
        if (hours > 168) return 'red'  // 7 days
        return 'amber'  // 48h - 7 days
    })

    function setDisconnected() {
        state.value = 'disconnected'
        disconnectCount.value++
    }

    function setConnected() {
        disconnectCount.value = 0
    }

    function setLoading(done: number, total: number) {
        state.value = 'loading'
        cdnProgress.value = { done, total }
    }

    function setWaitingForLol() {
        state.value = 'waiting-for-lol'
    }

    function setRunning() {
        state.value = 'running'
    }

    function setOffline(hasCache: boolean) {
        state.value = hasCache ? 'offline-stale' : 'offline-no-cache'
    }

    function updateCacheStatus(status: CacheStatus) {
        cacheStatus.value = status
    }

    return {
        state,
        cacheStatus,
        cdnProgress,
        disconnectCount,
        isStale,
        staleSeverity,
        setDisconnected,
        setConnected,
        setLoading,
        setWaitingForLol,
        setRunning,
        setOffline,
        updateCacheStatus,
    }
})
