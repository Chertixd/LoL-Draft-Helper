// Tauri IPC commands exposed to the Vue frontend via invoke().
//
// get_backend_port  -- returns the port the Python sidecar listens on
// restart_backend   -- shuts down the current sidecar and spawns a fresh one

use tauri::State;

/// Returns the port the Python sidecar is listening on.
/// Called by the frontend via `invoke<number>('get_backend_port')`.
#[tauri::command]
pub async fn get_backend_port(
    state: State<'_, crate::SidecarState>,
) -> Result<u16, String> {
    let lock = state.0.lock().map_err(|e| format!("Lock poisoned: {}", e))?;
    lock.as_ref()
        .map(|h| h.port)
        .ok_or_else(|| "Sidecar not running".to_string())
}

/// Shuts down the current sidecar and spawns a fresh one with a new port.
/// Called by the frontend restart button via `invoke('restart_backend')`.
///
/// After the new sidecar starts and passes the ready-file health check,
/// emits `backend-ready` so the frontend invalidates its cached URL.
#[tauri::command]
pub async fn restart_backend(
    app: tauri::AppHandle,
    state: State<'_, crate::SidecarState>,
) -> Result<(), String> {
    log::info!("restart_backend command invoked");

    // Shut down existing sidecar
    {
        let mut lock = state.0.lock().map_err(|e| format!("Lock poisoned: {}", e))?;
        if let Some(mut handle) = lock.take() {
            let old_port = handle.port;
            crate::sidecar::shutdown_sidecar(&mut handle);
            log::info!("Old sidecar shut down (port {})", old_port);
        }
    }

    // Spawn new sidecar in a background task (same pattern as initial setup).
    // run_sidecar stores the new SidecarHandle in SidecarState, polls the
    // ready-file, shows the window, and enters the supervision loop.
    let app_clone = app.clone();
    tauri::async_runtime::spawn(async move {
        if let Err(e) = crate::sidecar::run_sidecar(app_clone).await {
            log::error!("Sidecar restart failed: {}", e);
        }
    });

    // Emit backend-ready so frontend invalidates cached URL
    // and calls get_backend_port for the new port.
    use tauri::Emitter;
    app.emit("backend-ready", serde_json::json!({}))
        .map_err(|e| format!("Failed to emit backend-ready: {}", e))?;

    log::info!("Sidecar restart initiated");
    Ok(())
}
