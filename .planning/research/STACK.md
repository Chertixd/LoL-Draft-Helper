# Stack Research — Desktop Delivery (Tauri + PyInstaller + GitHub Pages CDN)

**Domain:** Windows desktop packaging of a Flask + Vue web app for non-technical end users
**Milestone:** v1 desktop delivery (subsequent milestone on a locked Flask/Vue/Supabase codebase)
**Researched:** 2026-04-14
**Overall Confidence:** HIGH

**Scope note:** This file documents only NEW technology for the v1 delivery milestone. The existing stack (Flask, Flask-SocketIO, Vue 3, Vite, Pinia, Supabase-as-ETL-target, pnpm monorepo) is locked per `.planning/codebase/STACK.md` and is NOT re-researched. Additions only.

---

## Recommended Stack

### Core Technologies (NEW)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Tauri** | `2.10.x` (latest: `tauri` crate `2.10.3`, `tauri-cli` `2.10.1`, released 2026-02-02) | Rust-based desktop shell — launcher, window host, auto-updater | v2 is the only supported line in 2026; v1 is EOL. Small binary (~5–10 MB host), uses system WebView2 on Windows instead of bundling Chromium. Native updater plugin with GitHub Releases support. Sidecar ("externalBin") pattern is first-class. |
| **PyInstaller** | `6.19.0` (released 2026-02-14, latest stable) | Bundle Python + Flask + Socket.IO + deps into a single `backend.exe` sidecar | De facto standard for Python-to-Windows-exe. `6.x` supports Python 3.8–3.14 out of the box. Spec-file model gives precise control over hidden imports (required for Flask-SocketIO + engineio) and UPX opt-out (required for AV-false-positive mitigation). |
| **Rust toolchain** | `stable >= 1.88` (current stable `1.86+` is sufficient; pin to `rust-toolchain.toml`) | Compile the Tauri host crate | Tauri-cli 2.9.3+ raised MSRV to 1.88 via the `home` crate dep. Using current stable avoids this gotcha. |
| **Node.js** | `>= 20.x LTS` (22.x LTS preferred) | Build the Vite bundle and drive `pnpm tauri` | Tauri v2 CLI and `@tauri-apps/cli` work on Node 18+ but Vite 5+ and modern Vue tooling target 20 LTS as the baseline in 2026. Matches the existing `packageManager` field expectations. |
| **pnpm** | `9.2.0` (already pinned in the repo) | Monorepo + Tauri build orchestration | No change from existing stack — Tauri's CLI integrates via `pnpm tauri dev` / `pnpm tauri build` without changes. |
| **WiX Toolset v3** (bundled by Tauri on Windows) | v3 (auto-downloaded) | Produce the `.msi` installer | Tauri v2 downloads WiX v3 at build time. No manual install needed on CI; `windows-latest` runner is sufficient. |

### Supporting Libraries (NEW)

**Rust (Tauri host, `src-tauri/Cargo.toml`):**

| Crate | Version | Purpose | When to Use |
|-------|---------|---------|-------------|
| `tauri` | `2.10.x` | Core framework | Always. |
| `tauri-build` | `2.x` (matching `tauri` minor) | Build-time code generation (in `build.rs`) | Always. |
| `tauri-plugin-shell` | `2.x` | Spawn the PyInstaller sidecar via `ShellExt::sidecar()` | Required for sidecar lifecycle per §5 of the spec. |
| `tauri-plugin-updater` | `2.x` | Auto-update via signed `latest.json` on GitHub Releases | Required for §4.3 / §11.11 of the spec. |
| `tauri-plugin-log` | `2.x` | Write Tauri host logs into `%APPDATA%\{bundle_id}\logs\` alongside the Python log file | Aligns with §7.2 structured-logging requirement. |
| `win32job` | `2.0.0` | Windows Job Object API — set `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` so the OS kills the Python sidecar if the Tauri host dies unexpectedly | Required for §5.2 crash-recovery guarantee. Tauri's built-in sidecar cleanup is best-effort; Job Object is the only way to guarantee orphan kill on host crash. |
| `serde` / `serde_json` | `1.x` | Serialize `get_backend_port` / `restart_backend` IPC payloads | Always. |
| `tokio` | `1.x` | Async runtime for sidecar-ready-file polling | Always (Tauri already depends on it transitively). |

**JavaScript (Vue frontend, added to existing `apps/frontend/package.json`):**

| Package | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tauri-apps/api` | `2.x` (track `tauri` minor) | `invoke()` calls into Rust host from Vue | Required for `getBackendURL()` per §4.2. |
| `@tauri-apps/plugin-updater` | `2.x` | JS-side `check()` + `downloadAndInstall()` for the updater UX | Required for the "Update available" prompt per §8 "Auto-update" criteria. |
| `@tauri-apps/plugin-shell` | `2.x` | Not needed at runtime for sidecar (sidecar is spawned by Rust), but useful if the frontend ever needs to open an external link (e.g. the AV-troubleshooting README anchor) | Optional. Add only if a README-link button is wired. |
| `@tauri-apps/cli` | `2.10.x` | The `pnpm tauri dev` / `pnpm tauri build` CLI | Required as a devDependency at the workspace root. |

**Python (sidecar runtime, added to existing `apps/backend/requirements.txt` and `pyproject.toml`):**

| Package | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pyinstaller` | `6.19.0` | Sidecar packaging (dev-only; not runtime) | Required; install as `pip install pyinstaller` in CI only, NOT in `requirements.txt`. |
| `requests` | `>= 2.32` (already present) | Fetch CDN JSON | Existing dep — reuse. No additional HTTP library needed. |
| — `supabase-py` | **REMOVE** | — | Delete from `requirements.txt` per §6.5. Not importable at runtime → PyInstaller won't bundle it → no Supabase credentials can leak. |

### Development Tools (NEW)

| Tool | Purpose | Notes |
|------|---------|-------|
| `tauri signer generate` (bundled in `@tauri-apps/cli`) | Generate updater keypair once | Produces `.key` + `.key.pub`. Private key → GitHub Actions secret `TAURI_PRIVATE_KEY`; passphrase → `TAURI_KEY_PASSWORD`; public key → `tauri.conf.json` `plugins.updater.pubkey`. Rotate only on key compromise (rotation breaks the update path for all existing clients). |
| GitHub Actions `windows-latest` runner | Build `.msi` + portable `.exe` | Single-platform build per spec §4.4. WiX v3 auto-provisions on this runner. |
| `actions/checkout@v4`, `actions/setup-python@v5` (Python 3.11 or 3.12), `pnpm/action-setup@v4`, `actions/setup-node@v4` (Node 22) | CI steps | Standard toolchain for the release workflow. |

---

## Tauri v2 Configuration Shape (prescriptive)

Full-fidelity skeleton for `src-tauri/tauri.conf.json`, derived from the Tauri v2 docs verified 2026-04-14:

```json
{
  "productName": "LoL Draft Analyzer",
  "version": "1.0.0",
  "identifier": "dev.till.lol-draft-analyzer",
  "build": {
    "beforeDevCommand": "pnpm --filter frontend dev",
    "devUrl": "http://localhost:5173",
    "beforeBuildCommand": "pnpm --filter frontend build",
    "frontendDist": "../apps/frontend/dist"
  },
  "app": {
    "windows": [
      {
        "title": "LoL Draft Analyzer",
        "width": 1280,
        "height": 800,
        "resizable": true,
        "visible": false
      }
    ],
    "security": {
      "csp": null
    }
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "nsis"],
    "icon": ["icons/icon.ico"],
    "externalBin": ["binaries/backend"],
    "createUpdaterArtifacts": true,
    "windows": {
      "webviewInstallMode": { "type": "downloadBootstrapper" },
      "wix": { "language": ["en-US"] },
      "nsis": { "installMode": "perUser" }
    }
  },
  "plugins": {
    "updater": {
      "pubkey": "CONTENT_OF_PUBLIC_KEY_PEM_HERE",
      "endpoints": [
        "https://github.com/<GITHUB_USER>/<REPO_NAME>/releases/latest/download/latest.json"
      ]
    }
  }
}
```

**Key decisions locked by the spec:**
- `targets: ["msi", "nsis"]` — MSI is the primary installer (spec §8 acceptance gate); NSIS `-setup.exe` doubles as the portable-ish `.exe` artifact (true "portable no-install" is not a first-class Tauri target — see "What NOT to Use" below).
- `installMode: "perUser"` — satisfies the "installer must complete without admin rights" constraint from `PROJECT.md`.
- `webviewInstallMode: "downloadBootstrapper"` — keeps installer size under 100 MB (the offlineInstaller mode adds ~127 MB which would bust the budget).
- `createUpdaterArtifacts: true` — required; without it, no `.sig` files are emitted for `latest.json`.
- `identifier: "dev.till.lol-draft-analyzer"` — this is the `{TAURI_BUNDLE_ID}` referenced in spec §6.4 and §7.2 (`%APPDATA%\{bundle_id}\`). Finalize before first release; changing later orphans the cache.

**Sidecar binary naming (critical):** `externalBin: ["binaries/backend"]` means PyInstaller must emit a file literally named `backend-x86_64-pc-windows-msvc.exe` in `src-tauri/binaries/`. Tauri appends the Rust target triple automatically at bundle time and expects the file to already have that suffix. Get this wrong and the bundle step fails with an unhelpful error.

---

## PyInstaller Spec Patterns (prescriptive)

`apps/backend/backend.spec` — minimum-viable spec for the sidecar:

```python
# backend.spec
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['backend.py'],
    pathex=[],
    binaries=[],
    datas=[],  # add any static files here (icons, cache seed, etc.)
    hiddenimports=[
        # Flask-SocketIO + engineio dynamic async driver loader
        'engineio.async_drivers.threading',
        # httpx's SOCKS support is referenced conditionally by some deps
        'httpx.socks',
        # websocket-client submodules used by league_client_websocket.py
        *collect_submodules('websocket'),
        # requests sometimes needs these on trimmed bundles
        'charset_normalizer',
        'urllib3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # EXPLICIT: never bundle Supabase — removes credential surface area
        'supabase',
        'postgrest',
        'gotrue',
        'realtime',
        'storage3',
        # optional: exclude eventlet/gevent since we use async_mode='threading'
        'eventlet',
        'gevent',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='backend-x86_64-pc-windows-msvc',  # MUST match Tauri externalBin target-triple suffix
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # CRITICAL: UPX triples the AV false-positive rate on PyInstaller stubs
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no console window for the sidecar — Tauri pipes stdout/stderr to its log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

**Spec-file contract with the rest of the milestone:**

1. **`async_mode='threading'`** in `backend.py`'s `SocketIO(...)` constructor. Do NOT rely on the default, because engineio's default fallback order (`eventlet → gevent_uwsgi → gevent → threading`) is brittle under PyInstaller. Pin it explicitly and hidden-import only that one driver.
2. **`upx=False`** — non-negotiable per `PROJECT.md` Key Decisions and spec §5.5. The Key Decision table in `PROJECT.md` calls this out as the cheapest procedural AV mitigation.
3. **`console=False`** — otherwise a black terminal flashes on every sidecar spawn, which is unacceptable UX for the target audience.
4. **`--onefile`** equivalent is implied by the single-`EXE` layout above; for `--onefile` discipline, the spec file above is already the `onefile` pattern (single `EXE(...)` without a `COLLECT(...)` step).
5. **Hidden-import surface** will almost certainly need one or two additions surfaced by the first CI build — keep the list in the spec file, not in CLI flags, so the adjustment is tracked in git.

**Reproducibility note (per spec §4.1):** PyInstaller embeds a build timestamp and occasional UUIDs, so SHA256 hashes will vary slightly build-to-build even with identical inputs. This is accepted; hashes are published per-release, not per-input.

---

## GitHub Pages CDN + Conditional-GET Client (prescriptive)

**Decision: use stdlib `requests` + a manual ETag/`If-Modified-Since` cache. Do NOT add `requests-cache`.**

**Rationale:**

| Criterion | `requests` + manual | `requests-cache` |
|-----------|---------------------|------------------|
| Dep footprint in PyInstaller bundle | 0 additional MB (already a dep) | +~3 MB + SQLite backend + `cattrs`/`platformdirs` transitive | 
| Control over cache layout | Full — `.meta.json` per file, matches spec §6.4 exactly | Opaque — uses its own SQLite/filesystem backend |
| Integrity hash per entry (spec §6.2 `__meta.sha256`) | Trivially added to `.meta.json` | Requires a custom wrapper layer anyway |
| AV false-positive surface | Smaller bundle → fewer signature matches | Larger bundle + SQLite binary → more matches |
| GitHub Pages behavior | GitHub Pages returns `ETag` and `Last-Modified` on every static file; honoring them manually is ~30 LoC | Over-engineered for 7 small JSON files |

**Concrete `json_repo.py` cache contract** (matches spec §6.3/§6.4):

```python
# apps/backend/src/lolalytics_api/json_repo.py (contract sketch)
import json, hashlib, requests
from pathlib import Path
from typing import Any

CDN_BASE = "https://<GITHUB_USER>.github.io/<REPO_NAME>/data"

def fetch_json(name: str, cache_dir: Path, timeout: int = 15) -> dict[str, Any]:
    cache_file = cache_dir / f"{name}.json"
    meta_file  = cache_dir / f"{name}.meta.json"

    headers: dict[str, str] = {}
    if meta_file.exists() and cache_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if etag := meta.get("etag"):
            headers["If-None-Match"] = etag
        if last_mod := meta.get("last_modified"):
            headers["If-Modified-Since"] = last_mod

    resp = requests.get(f"{CDN_BASE}/{name}.json", headers=headers, timeout=timeout)

    if resp.status_code == 304 and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    resp.raise_for_status()
    body_bytes = resp.content
    sha = hashlib.sha256(body_bytes).hexdigest()
    cache_file.write_bytes(body_bytes)
    meta_file.write_text(json.dumps({
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "fetched_at": resp.headers.get("Date"),
        "sha256": sha,
    }), encoding="utf-8")
    return json.loads(body_bytes)
```

**GitHub Pages-specific confirmations (HIGH confidence):**
- GitHub Pages serves `ETag` on every static response (weak ETags, format `W/"<hash>"`).
- GitHub Pages serves `Last-Modified` set to the commit timestamp of the file on the `gh-pages` branch.
- A `304 Not Modified` response from GitHub Pages has an empty body and preserves the `ETag` header, so the cache-hit path above is correct.
- GitHub Pages applies a default `Cache-Control: max-age=600` (10 min) at the edge. The spec's "one conditional GET per table at backend startup" ignores this header, which is fine — the conditional GET is the freshness mechanism, not the edge cache.

---

## Installation

**Rust / Tauri setup (one-time, per developer machine):**

```bash
# Rust (via rustup)
rustup toolchain install stable
rustup default stable

# Windows-specific Tauri prereqs (admin PowerShell)
# - Microsoft C++ Build Tools (MSVC) — installed via Visual Studio Installer
# - WebView2 Runtime — preinstalled on Windows 11; Win10 may need the evergreen installer

# Tauri CLI (already added to package.json as devDependency, but verify once)
pnpm add -D -w @tauri-apps/cli@^2.10.0
```

**New JS dependencies (workspace root or frontend):**

```bash
# Frontend-facing APIs
pnpm --filter frontend add @tauri-apps/api@^2.0.0 @tauri-apps/plugin-updater@^2.0.0

# Root devDependency
pnpm add -D -w @tauri-apps/cli@^2.10.0
```

**New Python dev dependency (CI only — do NOT add to runtime `requirements.txt`):**

```bash
# In .github/workflows/release.yml, NOT in the sidecar bundle
pip install pyinstaller==6.19.0
```

**New Rust deps (`src-tauri/Cargo.toml`):**

```toml
[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2.10", features = [] }
tauri-plugin-shell   = "2"
tauri-plugin-updater = "2"
tauri-plugin-log     = "2"
serde      = { version = "1", features = ["derive"] }
serde_json = "1"
tokio      = { version = "1", features = ["full"] }

[target.'cfg(windows)'.dependencies]
win32job = "2"
```

**Removed from the runtime bundle (per spec §6.5):**

```diff
# apps/backend/requirements.txt
- supabase>=2.4.0
```

(Delete from `pyproject.toml` optional extras as well.)

**Tauri updater keygen (one-time, then store in GitHub Secrets):**

```bash
pnpm tauri signer generate -w ~/.tauri/lol-draft-analyzer.key
# Output: private key (+ passphrase) → GitHub Secrets: TAURI_PRIVATE_KEY, TAURI_KEY_PASSWORD
#         public key → paste into tauri.conf.json > plugins.updater.pubkey
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **Tauri v2** desktop shell | Electron | If the team had deep existing Electron expertise, or if we needed Chromium-specific features (we don't). Electron would bloat the installer to ~150+ MB and exceed the 100 MB budget. |
| **Tauri v2** desktop shell | Webview2 + custom Rust shell | If we needed features Tauri plugins can't reach. Not justified — Tauri's sidecar + updater cover 100% of the spec. |
| **Tauri v2** desktop shell | PyWebView / Flaskwebgui | Only for pure-Python dev teams. Loses the signed-updater and MSI-bundle story entirely. |
| **PyInstaller 6.19** | Nuitka | If AV false-positive reports become frequent post-v1 — already parked as a backlog item per `PROJECT.md`. Nuitka compiles Python to C, producing binaries that look less like known PyInstaller stubs. Cost: longer build times, more complex build config. |
| **PyInstaller 6.19** | Briefcase / cx_Freeze / py2exe | Smaller user base in 2026 for Windows one-file Python distribution; less battle-tested with Flask-SocketIO hidden imports. |
| **Manual `requests` + ETag cache** | `requests-cache` | Only if we end up with >30 distinct CDN endpoints or need cross-session HTTP caching of third-party APIs. For the 7 known tables in spec §6.2, manual is strictly simpler. |
| **GitHub Pages as CDN** | Cloudflare R2 / S3 + CloudFront | If we later need signed URLs, per-client rate limiting, or WAF. Out of scope for v1 — GitHub Pages is free, already in the account, and returns correct conditional-GET headers. |
| **MSI + NSIS installers** | Portable `.exe` (standalone) | Tauri v2 does not ship a first-class "portable single-file exe" target. The NSIS `-setup.exe` is the closest equivalent; for a true portable binary, the user can extract the `.msi` with `lessmsi` or we can ship a ZIP of the install directory as a GitHub Release asset. Spec §4.3 references both as "~80 MB"; implementation needs to pick one concrete definition of "portable". |
| **Windows Job Object (`win32job` crate)** | Relying solely on Tauri's built-in sidecar kill | Tauri's cleanup is best-effort and fails when the host crashes ungracefully. Job Object + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` is the only OS-guaranteed way to kill the child — required for the §5.2 "App crash / force-quit" row. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **UPX compression with PyInstaller** | UPX-compressed stubs trigger ~3× the AV false-positive rate on Windows Defender and most consumer AVs. Spec §5.5 and `PROJECT.md` Key Decisions both explicitly mandate `upx=False`. | Keep `upx=False` in the spec file. Accept the larger binary (~50–70 MB → installer still ≤100 MB). |
| **Tauri v1** and any tutorial or plugin dated pre-2024-10 | v1 is EOL in 2026. Config shape is incompatible (`tauri.bundle.updater` moved to `plugins.updater`; `allowlist` replaced by `capabilities`; plugin crates split out of core). Many top Google hits for "tauri updater" still return v1 docs. | Tauri v2 docs at `v2.tauri.app` only. Verify every URL contains `/v2/` or starts with `v2.tauri.app`. |
| **`supabase-py` in the client runtime** | Any import path that touches Supabase ships Supabase credentials into the installer and re-introduces the attack surface this milestone exists to eliminate. | Remove from `requirements.txt`; add to PyInstaller `excludes=[...]` as a defense-in-depth; keep the Supabase ETL tooling in the separate `supabase-dataset-updater/` project where it belongs. |
| **`async_mode='eventlet'` or `'gevent'`** with PyInstaller | Both rely on monkey-patching and dynamic import of `engineio.async_drivers.{eventlet,gevent}` which collide with PyInstaller's bytecode analysis; frequent "Invalid async_mode specified" runtime crashes in bundled `.exe`s. | `async_mode='threading'` — explicitly set — with `engineio.async_drivers.threading` in the PyInstaller hidden-imports list. Adequate for the ~2–10 concurrent Socket.IO clients of a single-user desktop app. |
| **`requests-cache`** | Adds ~3 MB bundled dep, an embedded SQLite backend, and transitive deps that enlarge the AV-fingerprint surface — all for a problem that's 30 LoC of manual `If-None-Match`/`If-Modified-Since` handling. | Hand-written cache in `json_repo.py` per the sketch above. |
| **Hardcoded port 5000** in frontend or backend | Port conflicts with other dev tools (React, Grafana, etc.); breaks if user's corp AV reserves the port. | Dynamic port allocation in the Tauri host (`TcpListener::bind("127.0.0.1:0")`), passed to Python via `--port` CLI arg, exposed to Vue via `invoke('get_backend_port')`. |
| **`createUpdaterArtifacts: false`** (or omitting it) | Tauri v2 does NOT emit `.sig` signature files by default. Without them, the updater has nothing to verify against and the update endpoint 404s on the `.sig` URL. | Set `"createUpdaterArtifacts": true` in `bundle` explicitly. |
| **EV code-signing certificate in v1** | ~$200–400/year; requires a company entity for true EV in 2026; not justified for a non-commercial release. Carried as a backlog item per `PROJECT.md`. | Procedural AV mitigation: UPX-off + SHA256 hashes in release notes + README guidance + Microsoft false-positive submission via `submit.microsoft.com` after each release. |
| **`bundle.targets: "all"`** on `windows-latest` CI | Attempts to produce `.deb`, `.rpm`, `.appimage`, `.dmg` on a Windows runner → cryptic build failures (macOS/Linux bundlers aren't available) | Pin explicitly: `"targets": ["msi", "nsis"]`. |
| **Tauri IPC bridge** as the Vue↔Python communication channel | Would require rewriting every Flask route as a Tauri command; violates the "minimum-invasive change" constraint in `PROJECT.md`. | Keep HTTP + Socket.IO over `127.0.0.1:<dynamic-port>`. Tauri IPC is used ONLY for port discovery and for backend restart (`get_backend_port`, `restart_backend`). |
| **Offline WebView2 bootstrapper** (`webviewInstallMode: "offlineInstaller"` or `"fixedVersion"`) | Adds ~127 MB or ~180 MB to installer size — will bust the ≤100 MB budget from `PROJECT.md`. | `"downloadBootstrapper"` mode. WebView2 is preinstalled on Windows 11, and the ~2 MB bootstrapper handles the rare Windows 10 gap. |
| **`installMode: "both"`** for NSIS | "Both" triggers a UAC prompt to let the user choose per-user vs per-machine, contradicting the "no admin rights required" constraint. | `"installMode": "perUser"`. |

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `tauri@2.10.x` | `tauri-plugin-updater@2`, `tauri-plugin-shell@2` | Always match the major (`2`) line. Do NOT mix with any `1.x` plugin. |
| `@tauri-apps/cli@2.10` | `@tauri-apps/api@2.x`, `@tauri-apps/plugin-updater@2.x` | JS plugins must be `2.x`. `1.x` silently works partially and breaks on first updater call. |
| `tauri-cli@2.9.3+` | Rust stable `>= 1.88` | MSRV bumped by `home@0.5.12` dep. Pin `rust-toolchain.toml` to current stable. |
| PyInstaller `6.19.0` | Python `3.8–3.14` | Python 3.10.0 has a bootloader-incompatible bug — use 3.10.1+ or 3.11+. 3.15 beta is NOT supported yet. Pick 3.11 or 3.12 for CI stability. |
| PyInstaller `6.19.0` | Flask-SocketIO `5.3+` + python-socketio `5.9+` (both already in repo) | Requires `engineio.async_drivers.threading` in `hiddenimports`. Explicit `async_mode='threading'`. |
| `win32job@2.0.0` | Tauri `2.x` on Windows, Rust stable | `#[cfg(windows)]`-gated; no effect on a future macOS/Linux port. |
| `requests@2.32+` | Python 3.8+ | Existing dep; no change. |
| WebView2 Runtime | Windows 10 1803+ / Windows 11 | Evergreen; `downloadBootstrapper` mode handles Win10 machines that lack it. |
| WiX Toolset v3 | `windows-latest` GitHub Actions runner | Auto-provisioned by Tauri at build time. WiX v4 is NOT currently used by Tauri v2 stable — do not manually install a different version. |

---

## Stack Patterns by Variant

**If installer size starts exceeding 100 MB:**
- First, re-verify PyInstaller `excludes=[...]` — `supabase`, `postgrest`, `gevent`, `eventlet`, `tkinter`, `matplotlib`, and other heavy deps that may be pulled transitively.
- Then consider `UPX=False` is locked → cannot compress the stub.
- Last resort: switch `webviewInstallMode` down to `"downloadBootstrapper"` (already default above) or drop the NSIS target.

**If AV false positives become frequent after v1:**
- Per `PROJECT.md` and spec §5.5: migrate the sidecar from PyInstaller to **Nuitka**, keeping the Tauri host + updater unchanged.
- Nuitka produces a compiled-C binary that does not match known PyInstaller signatures.
- Or purchase an EV code-signing certificate (~$200–400/yr).

**If Windows-only constraint relaxes post-v1:**
- Tauri v2's MSI is Windows-only (WiX v3 requirement). DMG / AppImage / deb targets are available on their native platforms.
- The `win32job` crate is `#[cfg(windows)]` only — the Linux/macOS equivalent is `prctl(PR_SET_PDEATHSIG)` via the `nix` crate and `posix_spawn` process-group semantics respectively. Sidecar-kill-on-host-crash would need per-platform code.

---

## Sources

### HIGH confidence (official docs + direct version registries)

- **Tauri v2 docs** — `https://v2.tauri.app/` — verified 2026-04-14 for updater, sidecar, Windows installer, prerequisites
  - `/plugin/updater/` — updater plugin install, keygen, `latest.json` shape, GitHub Releases endpoint format
  - `/develop/sidecar/` — externalBin config, `ShellExt::sidecar()` Rust pattern, capabilities
  - `/distribute/windows-installer/` — MSI (WiX v3) + NSIS targets, WebView2 install modes, per-user install
  - `/distribute/sign/windows/` — code signing is optional; SmartScreen behavior without cert
  - `/start/prerequisites/` — Rust/Node baselines
- **crates.io / docs.rs** — `tauri-cli` 2.10.0 (2026-02-02), `tauri` 2.10.3, `tauri-bundler` 2.8.1, `win32job` 2.0.0
- **PyPI** — `pyinstaller` 6.19.0 (2026-02-14), Python 3.8–3.14 supported
- **PyInstaller docs** — `https://pyinstaller.org/en/v6.19.0/` — CHANGES.html, spec-file reference, Windows onefile notes
- **Tauri GitHub issue #14433** — confirms MSRV bump to Rust 1.88 via `home@0.5.12` for tauri-cli 2.9.3+
- **GitHub Pages docs** — confirms `ETag` + `Last-Modified` emitted on all static responses; default 10-minute edge cache

### MEDIUM confidence (widely-cited community patterns, verified across multiple sources)

- Flask-SocketIO + PyInstaller `engineio.async_drivers.*` hidden-import pattern — documented across Flask-SocketIO issues #259, #633, python-socketio #178 spanning 2020–2025; the fix is stable
- `win32job` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` for killing Tauri sidecars on host crash — pattern documented in Tauri discussion #3273 and win32job-rs README
- Tauri v2 `createUpdaterArtifacts: true` requirement — confirmed in updater plugin CHANGELOG entries and community walk-throughs (thatgurjot.com, ratulmaharaj.com TIL posts)
- AV-false-positive rate "~3×" for UPX-compressed PyInstaller stubs — widely cited in the PyInstaller community; spec §5.5 adopts this as the primary rationale for `upx=False`

### LOW confidence / flagged for validation

- Exact `@tauri-apps/plugin-updater` npm minor version tracking `tauri` 2.10 — the plugin-workspace is versioned independently and the latest may be `2.0.x` or `2.1.x`; implementation plan should `pnpm view @tauri-apps/plugin-updater version` at plan-freeze time.
- Whether Tauri v2's `"targets": ["nsis"]` produces a single-file portable `.exe` or a conventional setup wizard — treat it as a setup wizard by default; if the spec specifically needs a no-install portable, plan an extra step (e.g. ZIP of `target/release` directory as an alternative Release asset).
- Python 3.11 vs 3.12 vs 3.13 for the CI runner — all three are PyInstaller-compatible; 3.11 has the longest tail of dependency wheels; 3.12 is the current mainstream; 3.13 is newest stable. Pick 3.12 unless a transitive dep objects.

---

*Stack research for: Desktop delivery (Tauri + PyInstaller + GitHub Pages CDN) on top of a locked Flask/Vue/Supabase codebase*
*Researched: 2026-04-14*
