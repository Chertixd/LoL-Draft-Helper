// Sidecar lifecycle management: port allocation, Job Object spawn,
// ready-file polling, graceful shutdown, child exit supervision.
//
// The sidecar is the Python Flask backend (`backend.py` / `backend.exe`).
// Tauri spawns it on a dynamically-allocated localhost port and manages
// the full lifecycle: spawn -> health probe -> show window -> supervision
// -> graceful shutdown -> hard kill. A Win32 Job Object with
// KILL_ON_JOB_CLOSE provides the OS-level safety net if Tauri crashes.

use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use tauri::Manager;

#[cfg(windows)]
use win32job::Job;

// ---------------------------------------------------------------------------
// SidecarHandle
// ---------------------------------------------------------------------------

/// Handle to the running sidecar process and its containment Job Object.
pub struct SidecarHandle {
    pub port: u16,
    pub child: Child,
    #[cfg(windows)]
    pub job: Job,
}

// ---------------------------------------------------------------------------
// Port allocation
// ---------------------------------------------------------------------------

/// Allocate a free port by binding to 127.0.0.1:0, reading the assigned
/// port, and dropping the listener. The OS will reuse the port for the
/// next bind on the same address within a short window (TOCTOU race is
/// mitigated by retry logic in run_sidecar). (TAURI-02)
pub fn allocate_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

// ---------------------------------------------------------------------------
// Sidecar exe and args resolution
// ---------------------------------------------------------------------------

/// Resolve the sidecar executable path.
///
/// - Debug mode: returns `python` (spawns `backend.py` natively per D-15).
/// - Release mode: resolves the bundled `backend.exe` next to the Tauri binary.
fn resolve_sidecar_exe(app: &tauri::AppHandle) -> Result<PathBuf> {
    if cfg!(debug_assertions) {
        // Dev mode: use the system Python interpreter.
        // The actual script path is prepended to args by resolve_sidecar_args.
        Ok(PathBuf::from("python"))
    } else {
        // Release mode: backend.exe lives in the resource directory.
        let resource_dir = app
            .path()
            .resource_dir()
            .context("failed to resolve resource_dir")?;
        let exe = resource_dir.join("backend.exe");
        if exe.exists() {
            Ok(exe)
        } else {
            anyhow::bail!(
                "backend.exe not found at {}",
                exe.display()
            );
        }
    }
}

/// Build CLI args for the sidecar process.
///
/// In debug mode the first arg is the path to `backend.py` (since we spawn
/// `python` rather than `backend.exe`). Both modes pass `--port`,
/// `--ready-file`, `--cache-dir`, and `--log-dir`.
fn resolve_sidecar_args(
    app: &tauri::AppHandle,
    port: u16,
    ready_file: &std::path::Path,
) -> Result<Vec<String>> {
    let data_dir = app
        .path()
        .app_data_dir()
        .context("failed to resolve app_data_dir")?;
    let cache_dir = data_dir.join("cache");
    let log_dir = data_dir.join("logs");

    // Ensure directories exist
    std::fs::create_dir_all(&cache_dir).ok();
    std::fs::create_dir_all(&log_dir).ok();

    let mut args: Vec<String> = Vec::new();

    if cfg!(debug_assertions) {
        // Resolve backend.py relative to the Tauri project root.
        // In dev mode, the working directory is counterpick-app/src-tauri/,
        // and backend.py is at ../apps/backend/backend.py.
        let backend_script = std::env::current_dir()
            .unwrap_or_default()
            .join("../apps/backend/backend.py");
        args.push(
            backend_script
                .canonicalize()
                .unwrap_or(backend_script)
                .to_string_lossy()
                .into_owned(),
        );
    }

    args.extend([
        "--port".to_string(),
        port.to_string(),
        "--ready-file".to_string(),
        ready_file.to_string_lossy().into_owned(),
        "--cache-dir".to_string(),
        cache_dir.to_string_lossy().into_owned(),
        "--log-dir".to_string(),
        log_dir.to_string_lossy().into_owned(),
    ]);

    Ok(args)
}

// ---------------------------------------------------------------------------
// Spawn with Job Object (Windows)
// ---------------------------------------------------------------------------

/// Spawn the sidecar process inside a Win32 Job Object with
/// KILL_ON_JOB_CLOSE. The Job Object is the OS-level safety net: if
/// Tauri crashes or is killed via Task Manager, the OS auto-kills the
/// sidecar. (TAURI-03, TAURI-11)
#[cfg(windows)]
pub fn spawn_sidecar(
    exe_path: &std::path::Path,
    args: &[String],
    port: u16,
) -> Result<SidecarHandle> {
    use std::os::windows::process::CommandExt;

    const CREATE_NEW_PROCESS_GROUP: u32 = 0x00000200;
    const CREATE_NO_WINDOW: u32 = 0x08000000;

    let child = Command::new(exe_path)
        .args(args)
        .creation_flags(CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)
        .spawn()
        .context("failed to spawn sidecar process")?;

    // Create Job Object and configure KILL_ON_JOB_CLOSE BEFORE assigning
    // the child. The win32job 2.0 API: create() -> query -> limit -> set
    // -> assign. (Pitfall #1: assign_process takes isize, not &Child.)
    let job = Job::create().context("failed to create Job Object")?;
    let mut info = job
        .query_extended_limit_info()
        .context("failed to query Job Object limits")?;
    info.limit_kill_on_job_close();
    job.set_extended_limit_info(&mut info)
        .context("failed to set KILL_ON_JOB_CLOSE on Job Object")?;

    // Assign child to Job Object. Requires AsRawHandle for as_raw_handle().
    use std::os::windows::io::AsRawHandle;
    job.assign_process(child.as_raw_handle() as isize)
        .context("failed to assign child to Job Object")?;

    log::info!(
        "[SIDECAR] spawned pid={} port={} with Job Object",
        child.id(),
        port
    );

    Ok(SidecarHandle { port, child, job })
}

/// Stub for non-Windows platforms (keeps crate compilable for development).
#[cfg(not(windows))]
pub fn spawn_sidecar(
    _exe_path: &std::path::Path,
    _args: &[String],
    _port: u16,
) -> Result<SidecarHandle> {
    anyhow::bail!("sidecar spawn is only supported on Windows")
}

// ---------------------------------------------------------------------------
// Raw spawn for integration tests (TAURI-10)
// ---------------------------------------------------------------------------

/// Spawn the sidecar process inside a Win32 Job Object, accepting raw
/// `&[&str]` args so integration tests can pass an arbitrary command line
/// (e.g. `python backend.py --port ...`) without constructing `Vec<String>`.
///
/// This is the test-facing counterpart of [`spawn_sidecar`] which takes
/// `&[String]` args from the Tauri host's arg builder.
#[cfg(windows)]
pub fn spawn_sidecar_raw(
    exe: &std::path::Path,
    args: &[&str],
    port: u16,
    _ready_file: &std::path::Path,
) -> Result<SidecarHandle> {
    let owned: Vec<String> = args.iter().map(|s| s.to_string()).collect();
    spawn_sidecar(exe, &owned, port)
}

/// Stub for non-Windows platforms.
#[cfg(not(windows))]
pub fn spawn_sidecar_raw(
    _exe: &std::path::Path,
    _args: &[&str],
    _port: u16,
    _ready_file: &std::path::Path,
) -> Result<SidecarHandle> {
    anyhow::bail!("sidecar spawn is only supported on Windows")
}

// ---------------------------------------------------------------------------
// Ready-file poll
// ---------------------------------------------------------------------------

/// Poll for the ready-file at `interval_ms` intervals, timing out after
/// `timeout_ms`. The ready-file is written atomically by `backend.py`
/// after Flask confirms it can accept TCP connections. Its JSON shape is:
/// `{"port": N, "pid": N, "ready_at": "..."}`. (TAURI-04)
pub async fn poll_ready_file(
    path: &std::path::Path,
    interval_ms: u64,
    timeout_ms: u64,
) -> std::result::Result<serde_json::Value, String> {
    let start = Instant::now();
    loop {
        if path.exists() {
            let content = tokio::fs::read_to_string(path)
                .await
                .map_err(|e| format!("failed to read ready-file: {}", e))?;
            let value: serde_json::Value =
                serde_json::from_str(&content).map_err(|e| format!("invalid JSON in ready-file: {}", e))?;
            return Ok(value);
        }
        if start.elapsed().as_millis() as u64 >= timeout_ms {
            return Err(format!(
                "ready-file did not appear within {}ms at {}",
                timeout_ms,
                path.display()
            ));
        }
        tokio::time::sleep(Duration::from_millis(interval_ms)).await;
    }
}

// ---------------------------------------------------------------------------
// Graceful shutdown ladder
// ---------------------------------------------------------------------------

/// Shut down the sidecar gracefully:
/// 1. Send CTRL_BREAK_EVENT to the process group (requires
///    CREATE_NEW_PROCESS_GROUP at spawn time). (TAURI-06)
/// 2. Poll try_wait() every 50ms for up to 2000ms.
/// 3. If still alive, call child.kill() (TerminateProcess). (TAURI-06)
/// 4. The Job Object's KILL_ON_JOB_CLOSE is the final safety net. (TAURI-11)
#[cfg(windows)]
pub fn shutdown_sidecar(handle: &mut SidecarHandle) {
    use windows_sys::Win32::System::Console::GenerateConsoleCtrlEvent;

    const CTRL_BREAK_EVENT: u32 = 1;

    let child_pid = handle.child.id();
    log::info!("[SIDECAR] sending CTRL_BREAK_EVENT to pid={}", child_pid);

    // Step 1: Graceful CTRL+BREAK to process group
    // (process group ID = child PID when CREATE_NEW_PROCESS_GROUP is set)
    unsafe {
        GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, child_pid);
    }

    // Step 2: Wait up to 2000ms for clean exit
    let deadline = Instant::now() + Duration::from_millis(2000);
    loop {
        match handle.child.try_wait() {
            Ok(Some(status)) => {
                log::info!(
                    "[SIDECAR] exited gracefully pid={} status={}",
                    child_pid,
                    status
                );
                return;
            }
            Ok(None) => {
                if Instant::now() >= deadline {
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(e) => {
                log::error!("[SIDECAR] try_wait error: {}", e);
                break;
            }
        }
    }

    // Step 3: TerminateProcess
    log::warn!(
        "[SIDECAR] pid={} did not exit within 2s, calling TerminateProcess",
        child_pid
    );
    let _ = handle.child.kill();
    let _ = handle.child.wait(); // reap the zombie
}

/// Stub for non-Windows platforms.
#[cfg(not(windows))]
pub fn shutdown_sidecar(handle: &mut SidecarHandle) {
    let _ = handle.child.kill();
    let _ = handle.child.wait();
}

// ---------------------------------------------------------------------------
// Main orchestrator
// ---------------------------------------------------------------------------

/// Main orchestrator async function called from lib.rs setup():
/// 1. Allocate port with retry (up to 3 attempts on bind failure).
/// 2. Create temp ready-file path.
/// 3. Resolve exe path and args.
/// 4. Spawn sidecar inside Job Object.
/// 5. Store handle in SidecarState.
/// 6. Poll ready-file; on timeout show error dialog and exit.
/// 7. On success: show the main window.
/// 8. Enter supervision loop: emit backend-disconnected on child exit.
pub async fn run_sidecar(app_handle: tauri::AppHandle) -> Result<()> {
    use tauri::Emitter;

    // Step 1: Allocate port with retry (TOCTOU mitigation, Pitfall #6)
    let mut port = 0u16;
    let mut last_err = None;
    for attempt in 1..=3 {
        match allocate_port() {
            Ok(p) => {
                port = p;
                log::info!("[SIDECAR] allocated port {} (attempt {})", port, attempt);
                break;
            }
            Err(e) => {
                log::warn!(
                    "[SIDECAR] port allocation attempt {} failed: {}",
                    attempt,
                    e
                );
                last_err = Some(e);
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
    if port == 0 {
        anyhow::bail!(
            "failed to allocate port after 3 attempts: {}",
            last_err.unwrap()
        );
    }

    // Step 2: Create temp ready-file path
    let ready_file = std::env::temp_dir().join(format!(
        "counterpick-{}.ready",
        std::process::id()
    ));
    // Clean up any stale ready-file from a previous crash
    let _ = std::fs::remove_file(&ready_file);

    // Step 3: Resolve exe path and args
    let exe_path = resolve_sidecar_exe(&app_handle)?;
    let args = resolve_sidecar_args(&app_handle, port, &ready_file)?;

    log::info!(
        "[SIDECAR] launching {} {}",
        exe_path.display(),
        args.join(" ")
    );

    // Step 4: Spawn sidecar inside Job Object
    let handle = spawn_sidecar(&exe_path, &args, port)?;
    let child_pid = handle.child.id();

    // Step 5: Store handle in SidecarState
    {
        let state = app_handle.state::<crate::SidecarState>();
        let mut lock = state.0.lock().expect("SidecarState lock poisoned");
        *lock = Some(handle);
    }

    // Step 6: Poll ready-file (100ms interval, 10s timeout per TAURI-04)
    match poll_ready_file(&ready_file, 100, 10_000).await {
        Ok(value) => {
            // Validate that the ready-file port matches our allocated port
            if let Some(file_port) = value.get("port").and_then(|v| v.as_u64()) {
                if file_port as u16 != port {
                    log::warn!(
                        "[SIDECAR] ready-file port {} does not match allocated port {}",
                        file_port,
                        port
                    );
                }
            }
            log::info!(
                "[SIDECAR] ready-file received: {}",
                serde_json::to_string(&value).unwrap_or_default()
            );
        }
        Err(e) => {
            log::error!("[SIDECAR] startup timeout: {}", e);

            // Show error dialog (TAURI-07)
            // Use a simple message dialog via the native dialog API
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.show();
            }
            // Emit an error event the frontend can display, then exit
            let _ = app_handle.emit(
                "backend-startup-failed",
                serde_json::json!({
                    "error": format!(
                        "Backend could not start within 10 seconds.\n\n\
                         Your antivirus may have quarantined the file.\n\
                         See README for troubleshooting.\n\n\
                         Details: {}", e
                    )
                }),
            );
            // Clean up
            {
                let state = app_handle.state::<crate::SidecarState>();
                let mut lock = state.0.lock().expect("SidecarState lock poisoned");
                if let Some(mut h) = lock.take() {
                    shutdown_sidecar(&mut h);
                }
            }
            let _ = std::fs::remove_file(&ready_file);
            // Give the frontend a moment to display the error before exiting
            tokio::time::sleep(Duration::from_secs(5)).await;
            std::process::exit(1);
        }
    }

    // Clean up the ready-file (no longer needed)
    let _ = std::fs::remove_file(&ready_file);

    // Step 7: Show the main window (TAURI-04)
    if let Some(window) = app_handle.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
        log::info!("[SIDECAR] main window shown");
    }

    // Step 8: Supervision loop -- poll child every 500ms
    // If the child exits unexpectedly, emit backend-disconnected. (TAURI-08)
    loop {
        tokio::time::sleep(Duration::from_millis(500)).await;

        let exited = {
            let state = app_handle.state::<crate::SidecarState>();
            let mut lock = state.0.lock().expect("SidecarState lock poisoned");
            if let Some(ref mut handle) = *lock {
                match handle.child.try_wait() {
                    Ok(Some(_status)) => true,
                    Ok(None) => false,
                    Err(e) => {
                        log::error!("[SIDECAR] supervision try_wait error: {}", e);
                        true // treat errors as exits
                    }
                }
            } else {
                // Handle was taken (e.g. by restart_backend command)
                break;
            }
        };

        if exited {
            log::warn!(
                "[SIDECAR] child pid={} exited unexpectedly, emitting backend-disconnected",
                child_pid
            );
            let _ = app_handle.emit(
                "backend-disconnected",
                serde_json::json!({}),
            );
            break;
        }
    }

    Ok(())
}
