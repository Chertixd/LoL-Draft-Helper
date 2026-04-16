mod commands;
pub mod sidecar;

use std::sync::Mutex;
use tauri::Manager;

/// Holds the running sidecar's handle so other parts of the app
/// (IPC commands, shutdown hooks) can access the child process.
pub struct SidecarState(pub Mutex<Option<sidecar::SidecarHandle>>);

pub fn run() {
    // Resolve log directory from %APPDATA% (Pitfall #2: TargetKind::LogDir
    // resolves to %LOCALAPPDATA%, but Python logs go to %APPDATA%.
    // Use TargetKind::Folder with explicit path to guarantee co-location.)
    let log_path = {
        let appdata = std::env::var("APPDATA").unwrap_or_else(|_| ".".to_string());
        std::path::PathBuf::from(appdata)
            .join("dev.till.lol-draft-analyzer")
            .join("logs")
    };
    std::fs::create_dir_all(&log_path).ok();

    tauri::Builder::default()
        // MUST be first plugin (Pitfall #5 -- single-instance check
        // must run before any other state initialization) (TAURI-09)
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        // Rust host logging to %APPDATA%\dev.till.lol-draft-analyzer\logs\ (LOG-02)
        .plugin(
            tauri_plugin_log::Builder::new()
                .clear_targets()
                .target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::Folder {
                        path: log_path,
                        file_name: Some("tauri".into()),
                    },
                ))
                .level(log::LevelFilter::Info)
                .build(),
        )
        // Auto-updater plugin (UPD-01): checks gh-pages CDN for latest.json
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(SidecarState(Mutex::new(None)))
        .setup(|app| {
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::run_sidecar(app_handle).await {
                    log::error!("Sidecar failed: {}", e);
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                log::info!("Window close requested -- shutting down sidecar");
                let app = window.app_handle();
                let state: tauri::State<'_, SidecarState> = app.state();
                let mut lock = state.0.lock().unwrap();
                if let Some(mut handle) = lock.take() {
                    sidecar::shutdown_sidecar(&mut handle);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_backend_port,
            commands::restart_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error running tauri application");
}
