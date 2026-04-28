#!/usr/bin/env node
// Build the PyInstaller backend sidecar and stage it for Tauri.
// Cross-platform — works in cmd, PowerShell, and Git Bash.
// Assumes Python deps are already installed (see README sidecar setup).

import { spawnSync } from "node:child_process";
import { mkdirSync, copyFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");
const backendDir = join(repoRoot, "apps", "backend");
const distExe = join(backendDir, "dist", "backend-x86_64-pc-windows-msvc.exe");
const targetDir = join(repoRoot, "src-tauri", "binaries");
const targetExe = join(targetDir, "backend-x86_64-pc-windows-msvc.exe");

console.log("[sidecar] Running PyInstaller in", backendDir);
const py = spawnSync(
  "pyinstaller",
  ["--clean", "--noconfirm", "backend.spec"],
  { cwd: backendDir, stdio: "inherit", shell: true },
);

if (py.status !== 0) {
  console.error(
    "[sidecar] PyInstaller failed (exit " + py.status + "). " +
      "Did you run the one-time setup? See backend README.",
  );
  process.exit(py.status ?? 1);
}

if (!existsSync(distExe)) {
  console.error("[sidecar] Expected build output missing:", distExe);
  process.exit(1);
}

mkdirSync(targetDir, { recursive: true });
copyFileSync(distExe, targetExe);
console.log("[sidecar] Staged:", targetExe);
