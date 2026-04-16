/**
 * Auto-updater module (UPD-03, D-13).
 *
 * On app startup, checks for available updates via the Tauri updater plugin.
 * If an update is available, gates on /api/draft/active to avoid interrupting
 * champion select (UPD-04). Uses the default Tauri updater prompt (D-11).
 */
import { check } from '@tauri-apps/plugin-updater'
import { getBackendURL } from '@/api/client'

/**
 * Check for updates and prompt the user if one is available.
 * Silently defers if a draft session is active (D-13 / UPD-04).
 * Called once on app startup after backend is ready.
 */
export async function checkForUpdates(): Promise<void> {
  // Only run in Tauri context
  if (!('__TAURI__' in window)) {
    return
  }

  try {
    const update = await check()
    if (!update) return

    // Gate on draft-active state (D-13 / UPD-04)
    const backendURL = await getBackendURL()
    if (backendURL) {
      try {
        const resp = await fetch(`${backendURL}/api/draft/active`)
        const data = await resp.json()
        if (data.active) {
          console.warn('[UPDATER] Update available but draft is active -- deferring')
          return
        }
      } catch {
        // If we cannot reach the backend, proceed with update prompt
        // (backend may have crashed, update might fix it)
        console.warn('[UPDATER] Could not check draft state, proceeding with update')
      }
    }

    // Show default Tauri updater prompt (D-11)
    // downloadAndInstall() triggers the OS-level installer UI
    // which includes Install/Later buttons
    await update.downloadAndInstall()
    // If user accepts, the app will relaunch automatically
  } catch (e) {
    console.warn('[UPDATER] Update check failed:', e)
  }
}
