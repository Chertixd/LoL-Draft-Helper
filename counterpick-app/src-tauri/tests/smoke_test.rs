//! Sidecar lifecycle smoke test (TAURI-10)
//!
//! Exercises: port allocation -> spawn with Job Object -> ready-file poll -> shutdown.
//! Must pass 50x consecutively on windows-latest CI with zero flakes.
//!
//! Run: `cargo test --test smoke_test -- --test-threads=1`
//! (serial execution prevents port conflicts between concurrent test instances)

use std::path::{Path, PathBuf};
use std::time::Duration;

/// Resolve the Python backend.py path relative to the test binary location.
/// In dev mode, this is `counterpick-app/apps/backend/backend.py`.
fn resolve_backend_script() -> PathBuf {
    // CARGO_MANIFEST_DIR points to counterpick-app/src-tauri/
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .unwrap() // counterpick-app/
        .join("apps")
        .join("backend")
        .join("backend.py")
}

/// Single lifecycle: allocate -> spawn -> poll -> shutdown
fn run_one_lifecycle() -> Result<(), String> {
    let backend_script = resolve_backend_script();
    if !backend_script.exists() {
        return Err(format!(
            "Backend script not found: {}",
            backend_script.display()
        ));
    }

    // Use the sidecar module's allocate_port function
    let port = lol_draft_analyzer_lib::sidecar::allocate_port()
        .map_err(|e| format!("allocate_port failed: {}", e))?;

    let tmp_dir = std::env::temp_dir();
    let ready_file = tmp_dir.join(format!("smoke-test-{}.ready", port));
    let cache_dir = tmp_dir.join(format!("smoke-test-cache-{}", port));
    let log_dir = tmp_dir.join(format!("smoke-test-logs-{}", port));

    // Clean up any stale files
    let _ = std::fs::remove_file(&ready_file);
    std::fs::create_dir_all(&cache_dir).ok();
    std::fs::create_dir_all(&log_dir).ok();

    // Spawn using native Python (not the .exe -- this is a dev-mode test)
    let exe = "python";
    let mut handle = lol_draft_analyzer_lib::sidecar::spawn_sidecar_raw(
        Path::new(exe),
        &[
            backend_script.to_str().unwrap(),
            "--port",
            &port.to_string(),
            "--ready-file",
            ready_file.to_str().unwrap(),
            "--cache-dir",
            cache_dir.to_str().unwrap(),
            "--log-dir",
            log_dir.to_str().unwrap(),
        ],
        port,
        &ready_file,
    )
    .map_err(|e| format!("spawn failed: {}", e))?;

    // Poll for ready-file (15s timeout to account for CI runner slowness)
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();

    let result = rt.block_on(async {
        lol_draft_analyzer_lib::sidecar::poll_ready_file(&ready_file, 100, 15000).await
    });

    match result {
        Ok(value) => {
            // Verify the ready-file contains the expected port
            let reported_port = value
                .get("port")
                .and_then(|v| v.as_u64())
                .ok_or("ready-file missing 'port' field")?;
            if reported_port as u16 != port {
                return Err(format!(
                    "Port mismatch: allocated {} but ready-file says {}",
                    port, reported_port
                ));
            }
        }
        Err(e) => {
            // Kill the child before returning error
            lol_draft_analyzer_lib::sidecar::shutdown_sidecar(&mut handle);
            return Err(format!("poll_ready_file failed: {}", e));
        }
    }

    // Graceful shutdown
    lol_draft_analyzer_lib::sidecar::shutdown_sidecar(&mut handle);

    // Verify child is dead
    std::thread::sleep(Duration::from_millis(500));
    match handle.child.try_wait() {
        Ok(Some(_)) => {} // exited
        Ok(None) => return Err("Child still running after shutdown".to_string()),
        Err(e) => return Err(format!("try_wait error: {}", e)),
    }

    // Cleanup temp files
    let _ = std::fs::remove_file(&ready_file);
    let _ = std::fs::remove_dir_all(&cache_dir);
    let _ = std::fs::remove_dir_all(&log_dir);

    Ok(())
}

#[test]
fn test_sidecar_lifecycle_single() {
    run_one_lifecycle().expect("Single lifecycle test failed");
}

/// Run the lifecycle 5 times sequentially to catch TOCTOU and cleanup issues.
/// The full 50x test is run in CI with a loop in the workflow.
#[test]
fn test_sidecar_lifecycle_repeat_5() {
    for i in 1..=5 {
        if let Err(e) = run_one_lifecycle() {
            panic!("Lifecycle iteration {}/5 failed: {}", i, e);
        }
    }
}
