// Sidecar lifecycle management: port allocation, Job Object spawn,
// ready-file polling, graceful shutdown, child exit supervision.
// Full implementation in Task 2.

use std::process::Child;

#[cfg(windows)]
use win32job::Job;

/// Handle to the running sidecar process and its containment Job Object.
pub struct SidecarHandle {
    pub port: u16,
    pub child: Child,
    #[cfg(windows)]
    pub job: Job,
}

/// Main orchestrator -- spawns the backend sidecar and manages its lifecycle.
/// Called from lib.rs setup() closure via tauri::async_runtime::spawn.
pub async fn run_sidecar(_app_handle: tauri::AppHandle) -> anyhow::Result<()> {
    // Stub -- full implementation in Task 2.
    Ok(())
}
