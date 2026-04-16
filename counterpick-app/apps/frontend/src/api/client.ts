/**
 * Tauri Backend URL Discovery (FRONT-01)
 *
 * Provides getBackendURL() which resolves the sidecar's dynamic port via
 * Tauri IPC when running inside the desktop app, or falls back to
 * empty string for pure-browser dev mode (pnpm dev without Tauri).
 */

let _backendURL: string | null = null

/**
 * Returns the base URL for the Python backend (e.g. "http://127.0.0.1:51423").
 *
 * - In Tauri (window.__TAURI__ exists): calls invoke('get_backend_port')
 * - In browser dev mode: returns '' (empty string) so fetchApi uses
 *   relative '/api' paths through the Vite dev proxy at localhost:3000
 *
 * The result is cached. Call resetBackendURL() to invalidate (e.g. after
 * backend restart).
 */
export async function getBackendURL(): Promise<string> {
    if (!('__TAURI__' in window)) {
        // Pure browser dev mode (pnpm dev without Tauri) — use Vite proxy
        // Return empty string so fetchApi uses relative '/api' paths through
        // the Vite dev proxy at localhost:3000
        return ''
    }
    if (!_backendURL) {
        const { invoke } = await import('@tauri-apps/api/core')
        const port = await invoke<number>('get_backend_port')
        _backendURL = `http://127.0.0.1:${port}`
    }
    return _backendURL
}

/**
 * Invalidates the cached backend URL.
 * Called when the backend restarts (new port allocated).
 */
export function resetBackendURL(): void {
    _backendURL = null
}

/**
 * Sets up Tauri event listeners for backend lifecycle events.
 * Call once at app startup.
 */
export async function initBackendListeners(): Promise<void> {
    if (!('__TAURI__' in window)) return
    const { listen } = await import('@tauri-apps/api/event')
    // Invalidate cached URL when backend restarts with a new port
    await listen('backend-ready', () => {
        resetBackendURL()
    })
}
