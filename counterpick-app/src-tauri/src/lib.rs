mod sidecar;

use std::sync::Mutex;
use tauri::Manager;

/// Holds the running sidecar's handle so other parts of the app
/// (IPC commands, shutdown hooks) can access the child process.
pub struct SidecarState(pub Mutex<Option<sidecar::SidecarHandle>>);

pub fn run() {
    tauri::Builder::default()
        // MUST be first plugin (Pitfall #5 -- single-instance check
        // must run before any other state initialization)
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        // Log plugin will be fully wired in Plan 04 (LOG-02).
        // For now the setup closure creates the log dir for future use
        // and sidecar.rs logs to stdout in debug builds.
        .manage(SidecarState(Mutex::new(None)))
        .setup(|app| {
            // Create log directory at %APPDATA%\dev.till.lol-draft-analyzer\logs\
            let log_dir = app
                .path()
                .app_data_dir()
                .expect("failed to resolve app_data_dir")
                .join("logs");
            std::fs::create_dir_all(&log_dir).ok();

            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::run_sidecar(app_handle).await {
                    log::error!("Sidecar failed: {}", e);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![])
        .run(tauri::generate_context!())
        .expect("error running tauri application");
}
