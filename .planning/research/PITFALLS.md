# Pitfalls Research — Packaging & Distribution

**Domain:** Tauri v2 desktop app + PyInstaller Flask/Socket.IO sidecar + GitHub Pages CDN + Tauri updater, delivered to non-technical Windows users without code signing.
**Researched:** 2026-04-14
**Confidence:** HIGH for PyInstaller and Tauri-lifecycle pitfalls (Context7-grade docs + confirmed issue trackers). MEDIUM for GitHub Pages edge-cache behavior and SmartScreen reputation thresholds (community-sourced). LOW only where explicitly flagged.

Scope: every pitfall below is specific to the stack locked in `.planning/PROJECT.md` and the delivery-form spec (2026-04-14). Generic advice ("write tests", "use source control") is omitted.

---

## Critical Pitfalls

### Pitfall 1: Orphaned Python sidecar on Tauri crash (zombie `backend.exe`)

**What goes wrong:**
PyInstaller `--onefile` bootloader spawns two processes: the bootloader parent (`backend.exe`) unpacks to `%TEMP%\_MEIxxxxxx` and re-execs the real Python interpreter as a child. If the Tauri host calls `child.kill()` on the bootloader only, the Python child survives. On a hard Tauri crash (panic, force-quit, Task-Manager kill), both sidecar processes remain in Task Manager, continue holding `%TEMP%` files, and the `%APPDATA%\...\logs\` file handle stays open. Next app start then races against the orphan on port allocation and log writes.

**Why it happens:**
`child.kill()` in Rust's `std::process::Child` only signals the direct child PID. Tauri's `tauri-plugin-shell` documents this limitation — it cannot recursively reap a process tree. PyInstaller's two-process architecture is invisible to Tauri. Windows has no POSIX process-group primitive.

**How to avoid:**
1. In `src-tauri/main.rs`, wrap the sidecar spawn in a **Windows Job Object** with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. When Tauri dies for any reason (graceful exit, panic, SIGKILL equivalent), the kernel reaps every process in the job. Use the `windows-sys` or `win32job` crate.
2. Apply `CREATE_SUSPENDED | CREATE_BREAKAWAY_FROM_JOB`-aware flags so the child does not escape the job.
3. Back this up with a two-step shutdown: send `CTRL_BREAK_EVENT` via `GenerateConsoleCtrlEvent` (2 s grace), then `TerminateProcess`.
4. Add a one-line Python `atexit` hook that deletes the ready-file so a new instance can detect crashed predecessors.

**Warning signs:**
- Task Manager shows `backend.exe` processes lingering after app close.
- `%TEMP%\_MEIxxxxxx` directories accumulate across app restarts.
- Second app launch fails with `PermissionError` on the log file.
- Integration test `test_backend_cli.py` flakes when run repeatedly.

**Phase to address:** **Lifecycle** (must ship in v1 — the Job Object is cheap and the alternative is user-visible bugs).

---

### Pitfall 2: Missing PyInstaller hidden imports — Socket.IO silently starts in a broken mode

**What goes wrong:**
Flask-SocketIO dynamically imports `engineio.async_drivers.<mode>` at runtime. PyInstaller's static analyzer never sees the import and omits the module. The bundled `backend.exe` boots, prints nothing abnormal, binds to the dynamic port, writes the ready-file — and then raises `ValueError: Invalid async_mode specified` the moment the first Socket.IO client connects. Frontend sees a 400 on WebSocket upgrade, falls back to polling, or shows "backend-disconnected" after three reconnects. QA on a dev box with a Python virtualenv never reproduces it.

**Why it happens:**
PyInstaller only follows `import X` statements it can parse statically. `importlib.import_module(f"engineio.async_drivers.{mode}")` is invisible. `httpx.socks`, `engineio.async_drivers.threading` (default for Flask-SocketIO without eventlet/gevent), and `dns.*` (if any dependency pulls it) are known offenders. This is the #1 cause of "works with `python backend.py`, broken as `.exe`".

**How to avoid:**
1. In `backend.spec` `hiddenimports` list, include at minimum:
   ```python
   hiddenimports=[
       'engineio.async_drivers.threading',
       'engineio.async_drivers',
       'engineio',
       'socketio',
       'flask_socketio',
       'httpx.socks',
   ]
   ```
2. Run `pyi-archive_viewer dist/backend.exe` after build and grep for `engineio/async_drivers/threading.pyc` — if absent, the spec is wrong.
3. Add a CI smoke test that starts the built `.exe`, opens a Socket.IO client against the dynamic port, and asserts a round-trip within 5 s. Fail the build if not.
4. Do not silently catch startup exceptions in `backend.py` — let them surface.

**Warning signs:**
- `python backend.py` works; `dist/backend.exe` "works" until Socket.IO connects.
- Frontend logs `socket.io` 400s on upgrade, falls back to long-polling, or shows `transport close` loops.
- Backend log shows `Invalid async_mode specified` exactly once, then a silent crash loop.

**Phase to address:** **Packaging** (belongs in Phase 1 of the roadmap — the Socket.IO smoke test is the single cheapest regression-catcher for the entire delivery).

---

### Pitfall 3: UPX-compressed sidecar triggers mass AV quarantine on first user install

**What goes wrong:**
PyInstaller default `upx=True` (where UPX is installed on the build machine) produces a packed bootloader whose entry-point stub matches signatures shared with several packer-based malware families. Windows Defender, Kaspersky, Avast, and Norton quarantine the binary on extraction or on first execution. User sees "Backend stopped unexpectedly" with no actionable fix. For non-technical users, this is unrecoverable — they uninstall and the project loses a user.

**Why it happens:**
UPX itself is benign; AV vendors flag UPX-packed Python binaries on prior-art heuristics, because most UPX-packed PE files in the wild are actually malware. PyInstaller's generic bootloader compounds the problem (the bootloader is shared across every PyInstaller user in the world, so any one malware author poisoning a vendor's signature poisons everyone).

**How to avoid:**
1. **Hard rule** in `backend.spec`: `upx=False`. Also set `EXCLUDE_BINARIES` for any UPX-compressible DLLs if PyInstaller tries anyway. (Already in §5.5 of the spec — enforce with a CI grep.)
2. Pin PyInstaller to a recent minor version (>= 6.8) and **rebuild the bootloader from source** in CI. A freshly-compiled bootloader has unique byte sequences that don't match AV signature caches for ~2–6 weeks. Document the rebuild in the release checklist.
3. Prefer `--onedir` if installer-size budget allows (both the spec and §5.5 keep `--onefile`; revisit if AV reports exceed threshold).
4. Submit each release's SHA256 to `submit.microsoft.com` as a false positive within 24 h of tagging.
5. Publish SHA256 hashes of both `.msi` and portable `.exe` in release notes and README.
6. Add an error-dialog branch for "child exited within 2 s of spawn" → "Your antivirus may have quarantined the file. See README."

**Warning signs:**
- VirusTotal scan of `backend.exe` on a fresh build shows >3 vendor flags.
- A single user report of "the installer disappeared after I downloaded it" (Defender quarantines on extract).
- `backend.exe` spawn observed to exit with code `0xC0000409` or silent exit < 2 s on a clean Windows VM.

**Phase to address:** **Packaging** (the `upx=False` is a one-liner but the CI rebuild and VirusTotal check belong in Phase 1 gates). Distribution phase documents the user recovery path.

---

### Pitfall 4: Ready-file / webview-show race → frontend 404 storm on cold start

**What goes wrong:**
Tauri polls a ready-file at 100 ms intervals and shows the Webview when it appears. Python writes the file after `socketio.init_app(app)` but **before** `socketio.run()` actually binds the port. Between the file appearing and the port accepting TCP, the webview loads, Vue fires its first `/api/champions` request, and the OS returns `ECONNREFUSED`. Frontend interprets this as "backend unreachable", shows the red banner, and user's first impression is a broken app — even though the backend is up 50 ms later.

**Why it happens:**
Writing the ready-file before the server is listening is the obvious mistake. The subtle one is that `socketio.run()` spawns a threaded server which itself takes a few ms to enter `accept()`. Even a correct ordering can lose the race on cold HDDs.

**How to avoid:**
1. Write the ready-file **only after** `socketio.run()` has entered its serve loop. The simplest pattern: start `socketio.run()` on a thread, then from the main thread attempt a real TCP connection to `127.0.0.1:<port>` and a `GET /api/health` returning 200 — only then write the ready-file.
2. Tauri side: treat "ready-file present" as necessary-but-not-sufficient. After reading it, perform one `reqwest` probe to `/api/health`. Retry 3× at 50 ms before showing the window.
3. Frontend: first `getBackendURL()` call retries with exponential backoff (50/100/250 ms, cap 5 s) before surfacing "backend-disconnected". Silent retries during cold-start do not surface UI errors.
4. Alternatively replace the ready-file with a **handshake-over-stdout**: Tauri reads `backend.exe`'s stdout, Python prints `READY <port>` after the health check passes. Eliminates the file-based race entirely.

**Warning signs:**
- Red "backend-disconnected" banner flashes for 1–2 s on cold start, then clears.
- Integration test `test_backend_cli.py` passes, but the Tauri e2e smoke test is flaky.
- User reports "I had to click Restart once, then it worked."

**Phase to address:** **Lifecycle** — this is the single most common source of "first-run UX feels broken" reports in Tauri+sidecar apps.

---

### Pitfall 5: Port allocation TOCTOU — dev servers or Socket.IO rebind collides with the spawned sidecar

**What goes wrong:**
Tauri binds `127.0.0.1:0`, reads `.local_addr().port()`, drops the `TcpListener`, then spawns Python with `--port N`. Between drop and bind, another process can grab port N (Vite dev server, another Tauri instance, browser-extension helper, antivirus scanner). Python fails to bind with `OSError: [Errno 10048]`, exits, and Tauri shows "backend failed to start" after the 10 s timeout. On a dev machine with Vite hot-reload, this is reproducible enough to waste hours.

**Why it happens:**
Classic TOCTOU: the check (bind-0) and the use (spawn-with-port) are not atomic. On Windows the race window is ~1–10 ms. `SO_REUSEADDR` on the original listener does not help because the listener is dropped — there's no socket to share.

**How to avoid:**
1. **Inherit the socket** instead of handing over a port number. Bind the listener in Rust, set `SO_REUSEADDR`, pass the raw handle to the child via `STARTUPINFOEX` inheritance, and have Python read `fd 3` (or equivalent) as a pre-bound socket. Flask-SocketIO's `socketio.run(app, sock=...)` can accept a pre-bound socket with minor work; or use `werkzeug.serving.make_server(fd=...)`.
2. Cheaper alternative with acceptable residual risk: retry the allocate-and-spawn sequence up to 3 times on `WSAEADDRINUSE`. For v1, this is probably sufficient given single-user, single-instance usage.
3. Enforce single-instance via Tauri's `tauri-plugin-single-instance` so two app copies don't fight for ports.
4. Document the dev-mode fallback port in `tauri.conf.json` so developers can manually set a non-5000/5173/8080 fixed port for debugging.

**Warning signs:**
- "Backend failed to start" dialog appears after ~10 s on 1–2 % of cold starts.
- Log shows `[Errno 10048] Only one usage of each socket address`.
- Problem concentrates on machines running many dev tools simultaneously.

**Phase to address:** **Lifecycle**. Socket inheritance can be deferred to v1.1 if TOCTOU retries are good enough; document the decision.

---

### Pitfall 6: PyInstaller path resolution — `__file__` vs `sys._MEIPASS` mistakes for bundled resources

**What goes wrong:**
The repo contains data files (`cache_data.json`, any bundled JSON schemas, the initial champion list) referenced by paths like `Path(__file__).parent / "cache_data.json"`. In onefile mode PyInstaller extracts resources to `sys._MEIPASS` (a `%TEMP%\_MEIxxxxxx` directory). `__file__` of the entry script resolves correctly since PyInstaller 4.3, but **modules imported from a bundled zip** may have `__file__` pointing inside the extracted `_MEIPASS` tree, and writing next to `__file__` writes into `%TEMP%` which is wiped on process exit. Developers then find "my cache disappeared" bugs that only appear in the bundled build.

**Why it happens:**
Two different paths: `sys._MEIPASS` (read-only bundled resources) vs. a writable user directory (the real cache). Mixing them is the classic onefile trap. Additionally, `os.getcwd()` in a Tauri-spawned child inherits from Tauri, not from the `backend.exe` location — absolute paths via `__file__` are mandatory.

**How to avoid:**
1. A single `resources.py` module with two helpers:
   ```python
   def bundled_resource(name: str) -> Path:
       base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
       return base / name
   def user_data_dir() -> Path:
       return Path(os.environ['APPDATA']) / TAURI_BUNDLE_ID  # writable
   def cache_dir() -> Path:
       return user_data_dir() / 'cache'
   def log_dir() -> Path:
       return user_data_dir() / 'logs'
   ```
   Every read of a bundled file routes through `bundled_resource()`. Every write routes through `cache_dir()` / `log_dir()`. No `__file__` / `cwd()` usage anywhere else.
2. Remove `cache_data.json` from the git-tracked `apps/backend/` tree — it's already flagged in CONCERNS.md. The CDN + `cache/` directory replaces it.
3. Pass `APPDATA` path explicitly from Tauri to Python via `--cache-dir` CLI arg so Python never has to guess the Tauri bundle-id.
4. Write a unit test that asserts `cache_dir() != bundled_resource('.')` — trivial to add, catches regressions.

**Warning signs:**
- "Cache disappears after app restart" user reports.
- `_MEI` temp directories grow across reboots (cleanup hook missing).
- Tests pass with `python backend.py` but fail when run against `dist/backend.exe` via subprocess.

**Phase to address:** **Packaging** (the resource helper), **Lifecycle** (the `--cache-dir` CLI plumb-through).

---

### Pitfall 7: `requests` / `httpx` SSL cert verification fails in the bundled sidecar

**What goes wrong:**
`json_repo.py` fetches CDN JSONs via `requests.get(...)`. `requests` relies on `certifi` for the CA bundle; `certifi` ships its CA bundle as a `.pem` data file. PyInstaller's `certifi` hook pre-dates some certifi layout changes and may or may not collect `certifi/cacert.pem` depending on versions. Bundled app raises `SSLCertVerificationError: unable to get local issuer certificate` on the first HTTPS call. User sees "Cannot load champion data" with no usable diagnostic, even on a known-good network.

**Why it happens:**
`pyinstaller-hooks-contrib` has historically regressed certifi collection. `_ssl.c` looks for the OS cert store first; on Windows it doesn't find one; certifi should be the fallback but the `.pem` isn't on disk because it's inside the PyInstaller archive.

**How to avoid:**
1. In `backend.spec`, add `datas=collect_data_files('certifi')` (from `PyInstaller.utils.hooks`).
2. In `json_repo.py`, explicitly point `requests` at certifi at module load:
   ```python
   import certifi
   os.environ.setdefault('REQUESTS_CA_BUNDLE', certifi.where())
   os.environ.setdefault('SSL_CERT_FILE', certifi.where())
   ```
3. CI smoke test: `dist/backend.exe` must successfully `GET https://{USER}.github.io/{REPO}/data/champion_stats.json` within 10 s of spawn, on a fresh `windows-latest` runner with no dev tooling.
4. Pin `certifi` and `requests` in `requirements.txt` to avoid hook/library version drift.

**Warning signs:**
- First-run error banner: "Cannot load champion data. Check internet connection." — but network actually works.
- Log shows `ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]`.
- Works fine on developer's Python install but not in the bundle.

**Phase to address:** **Packaging** (spec datas + env var). **CDN** phase's integration test is the verification gate.

---

### Pitfall 8: SmartScreen "Unknown publisher" blocks the installer on first launch for every user

**What goes wrong:**
Without code signing, Windows SmartScreen displays a blue "Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting" full-screen takeover. The "Run anyway" button is hidden behind a "More info" link. Non-technical users click "Don't run" or close the dialog and the install is abandoned. This applies to both the `.msi` and the portable `.exe` on first run after download (Mark-of-the-Web attached).

**Why it happens:**
SmartScreen evaluates reputation based on publisher certificate identity and download volume. An unsigned binary has **no** publisher identity and **starts with zero reputation**. Reputation accrues with installs on different machines over days/weeks — but since SmartScreen blocks before the first install, building reputation is a chicken-and-egg problem for unsigned apps. Signing with a standard OV cert also starts at zero; only EV certs start with instant reputation.

**How to avoid (given "no code signing in v1"):**
1. **README front-loads the workaround** with screenshots: "More info → Run anyway". Place this above the download link, not buried at the bottom.
2. Link the README directly from the GitHub Release body.
3. Publish SHA256 hashes so technically-literate users can verify and blog-post the hashes.
4. Consider renaming the portable to `LoL-Draft-Analyzer-Portable.exe` (vs. generic `backend.exe`) — SmartScreen's reputation model uses the filename; unique-per-project names accumulate reputation faster.
5. Do not re-tag releases with the same version — every new binary hash restarts reputation. Bump version for every user-distributed build.
6. Log the SmartScreen decision boundary: if AV + SmartScreen friction dominates bug reports, trigger the "buy EV cert" backlog item. Set a concrete threshold (e.g., >10 % of issues mention SmartScreen) and track it.

**Warning signs:**
- GitHub issue reports "the download won't open" or "Windows says it's a virus".
- Download counter on the Release page far exceeds app telemetry (but we have no telemetry — inference must come from Discord/issue traffic).
- Cold-start logs show zero new connections after a release.

**Phase to address:** **Distribution** (README content, filename choice, release-notes format). Continuous monitoring via the "AV friction dashboard" concept in the backlog.

---

### Pitfall 9: Lost Tauri updater private key = permanently abandon installed user base

**What goes wrong:**
Tauri's updater verifies each `latest.json` signature against the public key baked into the installed app. The matching private key must sign every future release. If the private key is lost (developer leaves, laptop dies, password manager corrupted, `TAURI_PRIVATE_KEY` secret accidentally deleted from repo secrets), **no installed client can receive another update**. They continue running forever on the last signed version. The only recovery is to ship a new build with a new public key under a new bundle identifier and ask every user to manually uninstall and reinstall — which for a non-technical audience means >50 % churn.

**Why it happens:**
Tauri updater's trust anchor is the embedded public key. Rotation requires the new build to be signed with the **old** key so existing clients accept it; rotation from "no key" is impossible.

**How to avoid:**
1. Generate the key pair locally once via `tauri signer generate`. Store the **private key** in (a) 1Password / Bitwarden shared vault, (b) the repo's GitHub Actions secret `TAURI_PRIVATE_KEY`, (c) an offline backup (encrypted USB, printed paper wallet with QR code). Three independent copies minimum.
2. Document the key-recovery procedure in `docs/RELEASE.md` so a future-you or a collaborator can find it.
3. After first release, do **one** key rotation exercise in staging (fake tag, verify flow) so the procedure is known before it's needed.
4. Set the updater password (`TAURI_KEY_PASSWORD`) to something non-trivial and back it up alongside the key; the key is useless without it.
5. Beware the known Tauri advisory (GHSA-2rcp-jvr4-r259) about Vite accidentally bundling `TAURI_PRIVATE_KEY` into the frontend if it's exposed as a `VITE_` env var. Never prefix the secret with `VITE_`.

**Warning signs:**
- The first release ships but no one on the team can locate the private key afterwards. Fix this *before* release.
- `latest.json` updates intermittently get `UnexpectedKeyId` errors from installed clients.

**Phase to address:** **Auto-update / Distribution**. This is a process gate: no release tag until the key is verified present in three locations.

---

### Pitfall 10: `latest.json` pointing to a yanked or broken release

**What goes wrong:**
A release ships, users auto-update, a critical regression is discovered. The natural reaction is to delete the GitHub Release. But `latest.json` (usually an asset of the same release, or a file on the gh-pages branch) now 404s, and every app on startup sees a failed update check. Worse, if `latest.json` stays valid but points to deleted artifacts, the updater downloads return 404 mid-stream and leave installed apps in an inconsistent partial-update state.

**Why it happens:**
Tauri's updater pattern documents "always update `latest.json` with the new version" but not "never delete a release without first rolling `latest.json` back to the prior version". The update-forward and the rollback paths are asymmetric.

**How to avoid:**
1. Publish `latest.json` as a **separate file on the `gh-pages` branch**, not as a release asset. Roll-back becomes `git revert` on that branch, independent of GitHub Release state.
2. Include a `pub_date` field and reject client updates older than what's installed (Tauri does this by default on version compare, but log the decision).
3. Include a yank-procedure in `docs/RELEASE.md`: step 1, revert `latest.json` to previous version; step 2, mark release as prerelease (not deleted); step 3, optionally publish a `1.0.2-hotfix` over `1.0.1-broken`.
4. Never force-overwrite artifact names within a tagged release — rename or bump the patch version.
5. Tag `latest.json` with ETag + explicit `Cache-Control: max-age=60` in the workflow (GitHub Pages respects short max-age for the origin, though the CDN edge may cache longer — see Pitfall 15).

**Warning signs:**
- Updater logs `404 on https://.../latest.json` for users.
- Partial-update reports ("app won't start after update").
- Multiple versions of the `.msi` coexist for the same tag.

**Phase to address:** **Auto-update / CDN** — the `gh-pages`-hosted `latest.json` pattern is the load-bearing decision.

---

### Pitfall 11: Mid-draft force-update — user loses champion-select state

**What goes wrong:**
Tauri updater defaults to "install on next app restart" but many implementations call `Update.installAndRelaunch()` as soon as the user clicks "Install". If that prompt appears while the user is in champion select (i.e., the exact moment the app is useful), the relaunch loses the draft tracker state, the websocket reconnects into a now-missed draft, and the user's game has already started with no recommendations. This is the single worst UX failure possible for this app.

**Why it happens:**
The updater runs on a schedule unrelated to LCU draft state. Nothing in Tauri knows "user is mid-draft, don't interrupt".

**How to avoid:**
1. Gate `installAndRelaunch()` on a Rust-side "is-draft-active" query exposed by the Python backend (`GET /api/draft/active → {active: bool}`).
2. Defer the update prompt entirely when the LCU reports champion-select is in progress. Retry on app next idle.
3. Default updater to **ask-on-next-app-start**, not "install immediately". Show the prompt in the waiting-view only.
4. Add an "Install on next start" button alongside "Install now" in the update dialog so the user keeps control.
5. Persist draft state to `%APPDATA%\.../draft_session.json` on every pick event, so that if a crash-or-update does happen, state is recoverable on relaunch.

**Warning signs:**
- User reports "the app updated during a ranked game and I had no recommendations for the rest of draft".
- Updater timing telemetry would show updates during 2–5 PM local peak (there is no telemetry; rely on issue reports).

**Phase to address:** **Auto-update** + **Lifecycle** (the draft-active API and persistence).

---

### Pitfall 12: `json_repo.py` signature drift from `supabase_repo.py` breaks Flask routes silently

**What goes wrong:**
`json_repo.py` is meant to be a drop-in replacement for `supabase_repo.py`. The old module returns `list[dict]` with keys `championId`, `role`, `winrate`, etc. The new CDN JSON format uses `champion_id`, `role`, `wr`. Or: old returns `get_matchups(champion: int)` but new accepts `get_matchups(champion_id: int)`. Flask route handlers import from the new module, parameter name change slips through, linter doesn't catch it (both are valid identifiers), and at runtime every `/api/recommendations` call returns 500. Tests pass because they mock the repo layer. Users see "Recommendations unavailable" across the board.

**Why it happens:**
Python duck-typing hides shape mismatches. The spec says "preserve the public API surface" but there's no enforcement. The existing codebase has 444 lines in `supabase_repo.py` across ~20 public functions — the drift surface is large.

**How to avoid:**
1. **Define the shared contract in `packages/core`** — TypedDict / dataclass for each returned row (`ChampionStatRow`, `MatchupRow`, etc.) and a Protocol for the repo interface. Both `supabase_repo.py` (if kept for ETL/debug) and `json_repo.py` implement the same Protocol. Run `mypy --strict` on the backend in CI; drift becomes a build error.
2. Ship the `json_repo` behind a feature flag first, in dev mode only, with a "compare to supabase" assertion: both are queried, results diffed, any mismatch logs a warning and fails the test suite. Remove after one green release.
3. Add a contract test per public function that exercises the real CDN-served JSON against the expected shape. These are 20 tiny tests but they catch every drift.
4. The `__meta` field in each exported JSON file should include a `schema_version`. Client refuses to parse newer versions than it knows.

**Warning signs:**
- Specific endpoints return 500 while others work.
- `/api/recommendations` returns `null` rows silently (KeyError caught by a broad handler).
- Post-migration manual QA of "blind pick recommendations across all 5 roles" surfaces one role that works differently.

**Phase to address:** **CDN** (the export script must commit to a schema; `json_repo.py` consumes the same schema).

---

### Pitfall 13: Cache corruption is not auto-recoverable — app never starts again

**What goes wrong:**
Conditional-GET writes a JSON blob to `%APPDATA%\...\cache\champion_stats.json`. Power loss during write produces a truncated file. Next app start, `json_repo.fetch_json` reads cache-first for perceived speed, `json.loads()` raises `JSONDecodeError`, backend exits with an unhandled exception, Tauri shows "backend stopped unexpectedly" → user clicks Restart → same crash. The spec §7 says "Cache file deleted, fresh download triggered" but there's no code path for "invalid JSON in cache on startup" as distinct from "invalid JSON mid-session".

**Why it happens:**
Happy-path code assumes cache is either absent or valid. Cache writes are not atomic (no temp-file-rename pattern). JSON parse errors are raised higher than the "maybe fall back to re-download" logic.

**How to avoid:**
1. **Write-then-rename** atomicity: write to `champion_stats.json.tmp`, `fsync`, then `os.replace`. Interrupted writes never leave a partial file in the final path.
2. Wrap every `json.loads(cache_file.read_text())` in a try/except that deletes the corrupt file and falls through to the HTTP path. Log the corruption event.
3. On startup, validate cache against a lightweight schema (row count > 0, `__meta` present, `sha256` matches). Any failure → delete → re-download.
4. As a last resort, a `--reset-cache` CLI flag that wipes `%APPDATA%\...\cache\` and starts fresh. Expose via an in-app "Reset Data" button for users.

**Warning signs:**
- `JSONDecodeError` in logs right before app exit.
- A recurring "app won't start" report that resolves only when the user manually deletes `%APPDATA%\cache\`.
- CI test: kill `backend.exe` with SIGKILL during cache write, restart, assert graceful recovery.

**Phase to address:** **CDN** (atomic writes in `json_repo.py`) + **Lifecycle** (fallback UX).

---

### Pitfall 14: Offline first-run — no cache, no network, dead-end UX

**What goes wrong:**
User installs the app on a laptop without internet, opens it, cache is empty, CDN call fails. The spec §7 says "Error banner with retry button — exponential backoff". But if the user never regains network in-session, the app is just an empty shell; if the user closes it, next launch repeats the same error. There's no bundled minimal dataset to demonstrate the app works at all. First-impression lost.

**Why it happens:**
Cold-start is designed as "download on first run". The assumption that first run always has network is natural but wrong ~5 % of the time (dorm wifi captive portal, airline laptop, locked corporate network).

**How to avoid:**
1. **Bundle a minimal seed dataset** inside the sidecar (`bundled_resource('seed/champion_stats.json')`) dated at build time. It's stale but functional. On first run: use seed data immediately, fire CDN fetch in the background, replace seed with CDN data on success. Installer grows by ~1–5 MB — well within the 100 MB budget.
2. UI indicator "Using bundled data from YYYY-MM-DD; fetching latest…" during the upgrade.
3. Captive-portal detection: if the CDN fetch returns a redirect-to-HTML page (not JSON), show "Looks like you're on a captive portal — please accept the terms in your browser."
4. Offline mode is explicit: app runs, recommendations are computed, banner persists "Offline — data from YYYY-MM-DD". Retry every 10 min silently.

**Warning signs:**
- "I installed it and it just shows an error" reports from hotel-wifi users.
- CDN fetch latency histogram would show the >60 s tail but we don't have telemetry; rely on issue reports.
- QA script: install on a Windows VM with network disabled, verify app still opens and shows something useful.

**Phase to address:** **CDN** (seed dataset, captive detection) and **Distribution** (QA script).

---

### Pitfall 15: Browser/CDN cache serves stale JSON after a fresh ETL export

**What goes wrong:**
GitHub Actions runs the ETL, commits fresh `champion_stats.json` to the `gh-pages` branch. Client starts, sends conditional GET with `If-None-Match: <old etag>`. Depending on GitHub Pages' Fastly CDN edge state, one of three things happens:
1. Origin honors ETag → 304 Not Modified → client keeps old cache. But the origin *has* new data — propagation was slow. Client is stale for up to ~10 minutes.
2. Edge serves a stale cached response directly without revalidating. Client gets 200 with old body + old ETag. Client thinks it's up-to-date.
3. ETag on the edge doesn't match origin's ETag (because a redeploy re-minted the ETag) → client's cache is discarded even though data is identical → full re-download, wasted bandwidth.

Net effect: users see last-patch champion data on a day when a patch dropped 6 hours ago.

**Why it happens:**
GitHub Pages uses Fastly as a CDN. Fastly's edge caches GitHub Pages responses with TTLs Github controls indirectly (`Cache-Control: max-age=600` is a common default). Conditional GET is honored but the 304/200 decision happens at the edge, not origin. Purge is not under user control for free GitHub Pages.

**How to avoid:**
1. Include `__meta.exported_at` in every JSON. Client compares `exported_at` to last-known and surfaces staleness age to user (spec already says this).
2. **Cache-bust by filename**: export to `data/champion_stats-YYYYMMDD-<sha>.json` and also write a small `data/manifest.json` pointing to current filenames. `manifest.json` itself stays small (cache misses cheap), and data files are content-addressed (immutable, cache forever). This pattern is robust to any CDN weirdness.
3. If (2) is too much plumbing for v1, fall back to a version-bumped query string: `?v=<exported_at>` from the client, varies the CDN cache key, bypasses stale edges. Still cheap.
4. Client always logs `exported_at` from the response body so user-reported "why is this stale" bugs are triageable.
5. Set a CI canary: every 30 min after export, a GitHub Action fetches `data/champion_stats.json` from the public URL and asserts `exported_at` matches the expected timestamp. Alarm on drift > 1 hour.

**Warning signs:**
- Release-day reports: "new champion X isn't showing up even though it was added".
- Different users see different data on the same day.
- CI canary reports stale data.

**Phase to address:** **CDN** (manifest-based versioning is a Phase-1 decision).

---

### Pitfall 16: Race between ETL completion and JSON export — partial data published

**What goes wrong:**
GitHub Actions workflow: ETL step writes rows, then immediately the export step queries Supabase and commits JSON. If the ETL uses multi-transaction batching (matchups table has millions of rows), the export may snapshot the DB mid-batch. Published JSON is internally inconsistent: `champion_stats` references champion IDs that don't appear in `champion_stats_by_role` yet. Client recommendation engine receives mismatched data, silently skips some champions, scores look wrong.

**Why it happens:**
ETL + export share no transactional boundary. Supabase doesn't expose "ETL is done" as a signal. A job-step dependency in GitHub Actions enforces order, not atomicity.

**How to avoid:**
1. ETL writes to a **staging schema** (e.g., `staging.matchups`). On ETL success, a single atomic step renames/copies `staging.*` → `public.*` (inside one transaction). Export reads from `public.*` only. Concern already flagged in CONCERNS.md ("Data Pipeline Coupling") as MEDIUM — the migration elevates it to needed-before-release for correctness.
2. Alternatively (cheaper for v1): have the ETL write a row to a `etl_runs(status, finished_at)` table. Export refuses to run unless the last row is `status='ok'` and `finished_at > 1 minute ago`. Not perfectly atomic but closes the obvious race.
3. Export computes integrity checks: every champion_id in `matchups` must exist in `champion_stats`. Any violation = abort, do not commit JSON, alert maintainer. This is a 10-line validator.
4. Export commits all JSON files in a **single git commit** so the CDN either has all-new or all-old, never half-new.

**Warning signs:**
- Sporadic "champion X missing recommendation" reports on the day after an ETL run.
- CI validator fails intermittently.
- Diff between consecutive `gh-pages` commits shows some tables updated, others not.

**Phase to address:** **CDN** (ETL/export coordination).

---

### Pitfall 17: Committing large JSON to `gh-pages` bloats repo history forever

**What goes wrong:**
Every daily ETL commits ~5–10 MB of JSON diff to `gh-pages`. After 1 year that's ~3 GB of git history. `git clone` gets painful, GitHub may throttle, `gh-pages` branch becomes unfetchable on low-bandwidth CI runners, export Action times out on the push step.

**Why it happens:**
Git is designed for source code, not datasets. JSON diffs of tabular data are dense and do not compress well with git's delta algorithm.

**How to avoid:**
1. **Force-push** the `gh-pages` branch every export: each deploy is a single commit with no history. Loses the audit trail but the ETL is the audit trail.
2. Alternative: use a GitHub Release as the CDN backing instead of a branch (upload JSON as release assets). GitHub Releases don't count against repo size the same way. But the URLs are less stable — not recommended for v1.
3. Use `actions/deploy-pages` with a `keep-files: false` option (see GitHub docs) which handles the orphan-branch dance.
4. If history *is* desired, `.gitattributes` with `*.json binary` prevents delta chaos but doesn't solve size growth.

**Warning signs:**
- `.git/objects` size on the deploy runner exceeds 500 MB.
- Daily export Action runtime climbs linearly month-over-month.
- `git push` to `gh-pages` takes > 1 minute.

**Phase to address:** **CDN** (initial deploy-branch strategy).

---

### Pitfall 18: MSI vs portable-exe user confusion

**What goes wrong:**
Release page lists both `LoL-Draft-Analyzer-1.0.0-setup.msi` and `LoL-Draft-Analyzer-1.0.0-portable.exe`. Non-technical user downloads whichever is on top, may not understand the difference, picks portable, runs it from `%USERPROFILE%\Downloads\`, closes it, later deletes Downloads → no Start Menu entry → "where did the app go?". Or installs the MSI, then also downloads the portable, runs both, both try to spawn sidecars on the same user config, one corrupts the other.

**Why it happens:**
Power users expect a choice. Casual users want one button. Mixed audience = both are confused.

**How to avoid:**
1. Release notes body: put the MSI **first**, above the portable, with "Recommended for most users — creates Start Menu entry, auto-updates."
2. Portable section labelled "Advanced: Portable (no installer, no auto-update)".
3. Different Tauri bundle IDs for MSI and portable (e.g., `.lol-draft-analyzer` and `.lol-draft-analyzer-portable`) so their `%APPDATA%` directories don't collide if a user installs both.
4. Single-instance lock at the binary level so running two at once shows "already running" and focuses the existing window.
5. README: "Which should I download?" section answering in ≤3 sentences.

**Warning signs:**
- Issues reporting "updates don't work" (from portable users thinking they're on MSI).
- Cache-corruption reports from mixed-install machines.
- Analytics (if we had any) would show double-digit portable downloads but single-digit MSI installs — inverted from expectation.

**Phase to address:** **Distribution** (release notes, README). **Lifecycle** (single-instance lock, distinct bundle IDs).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Ship with `upx=False` but no bootloader rebuild | One-line config change in PyInstaller spec | AV signatures catch up within ~4 weeks; false-positive rate climbs post-release | Only for v1.0.0; schedule bootloader rebuild in CI for v1.1.0 |
| Ready-file instead of stdout handshake | Simple file-watch loop in Rust | Race conditions between ready-file write and actual port-listening (Pitfall 4) | Only if combined with a post-ready HTTP health probe |
| TOCTOU port-bind retry loop instead of socket inheritance | ~10 lines of Rust | Flaky cold-start on busy dev machines (Pitfall 5) | For v1 as documented fallback; socket inheritance is the v1.1 fix |
| Force-push `gh-pages` without keeping history | No bloat, simple workflow | Lose the ability to post-mortem "when did this data go bad" | Acceptable for v1 because ETL logs provide the audit trail |
| No atomic staging in ETL → export | Skip schema changes to Supabase | Pitfall 16 (partial-data publishing) can ship wrong recommendations for hours | Never acceptable at release; staging-table migration is a pre-v1 requirement |
| README-only SmartScreen workaround | Zero build-time cost | User-facing friction, lost installs, chicken-and-egg reputation | Acceptable for v1 by explicit constraint ("no code signing"); reconsider at first friction threshold |
| `supabase-py` still in `requirements.txt` during v1 dev | Backend dev retains DB access via repo | Pitfall 12 (signature drift); supabase client bloats PyInstaller bundle | Dev-only optional dep; enforce exclusion via `--exclude-module supabase` in production spec |
| Single `backend.py` at 1,751 lines | No refactor now | Hides dependencies; makes PyInstaller hidden-imports audit harder | Acceptable if refactor deferred to post-v1, but mark as CONCERNS-MEDIUM |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| PyInstaller × Flask-SocketIO | Assume `--onefile` auto-detects `engineio.async_drivers.threading` | Explicit `hiddenimports` list; CI smoke test that opens a Socket.IO connection |
| PyInstaller × `requests`/`httpx` | Ship without `certifi` data | `collect_data_files('certifi')` + set `REQUESTS_CA_BUNDLE` env var at startup |
| PyInstaller × `cryptography` (pulled by httpx[http2] if enabled) | Binary wheels missing at runtime | `--collect-submodules cryptography` in spec |
| Tauri v2 × PyInstaller onefile | `child.kill()` on bootloader PID | Windows Job Object with `KILL_ON_JOB_CLOSE` wraps the whole tree |
| Tauri v2 updater × GitHub Releases | Store `latest.json` as a release asset | Host `latest.json` on `gh-pages` as a separate file; decouples rollback from release state |
| Tauri v2 updater × Vite build | `TAURI_PRIVATE_KEY` exposed as `VITE_*` env var | Never prefix updater secret with `VITE_`; Vite only bundles `VITE_*` into frontend (known advisory GHSA-2rcp-jvr4-r259) |
| Vue frontend × Tauri IPC | Assume `invoke` is available on first render | Lazy-load backend URL discovery, retry on initial failures (Tauri IPC can take 50–200 ms post-mount) |
| GitHub Actions × `gh-pages` branch | Push on every workflow (huge history) | Force-push with `peaceiris/actions-gh-pages@v4` using `force_orphan: true`, or migrate to `actions/deploy-pages@v4` |
| Supabase × JSON export | Query large tables without pagination | Service-role key + explicit `.range()` chunking; else timeouts in CI |
| LCU WebSocket × Python sidecar | Reconnect forever after LoL closes | Bounded reconnect with backoff, surface "LoL client waiting" view at 3 s (spec §7 has this) |
| Windows Defender × Tauri MSI | Ship MSI without hash publication | SHA256 in release notes; Microsoft false-positive submission per release (spec §5.5) |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Cache JSON re-parsed on every `/api/recommendations` call | p99 latency climbs proportional to dataset size | Load JSONs once at backend startup into in-memory dicts; refresh on CDN change only | ~150 ms per request once dataset exceeds ~10 MB |
| Synchronous `requests.get` on startup blocks ready-file write | Cold-start delay > 5 s | Kick off CDN fetches in a background thread; write ready-file once Flask is listening; data-fetch completion is its own event | Noticeable on slow networks day one |
| Socket.IO default `threading` async_mode with many connections | Fine for single-user local, degrades with WebSocket spam | For v1 (single-user local), threading is correct; if we ever expose to LAN, switch to eventlet | Only if spec is violated by LAN exposure — not in v1 scope |
| `gh-pages` branch grows unbounded with daily commits | `git push` slows, Actions time out | Force-push / orphan deploy strategy | ~6 months post-release |
| Conditional GET pessimism (always fetches full body) | Pointless bandwidth use on every start | Implement 304 handling in `json_repo.py` per spec §6.3, verify with real CDN responses in integration test | Bandwidth cost is trivial on day one but user-perceivable cold-start latency adds up |
| Orphaned `_MEI` temp directories accumulate | Disk fills on long-running installs | Job Object reaping (Pitfall 1) + a cleanup step on startup that deletes `_MEI*` older than 1 day | Within ~100 crashed-app sessions |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| `SUPABASE_SERVICE_ROLE_KEY` accidentally bundled into `backend.exe` | Any user with a hex editor can extract the key → full DB write access | CI check: `strings dist/backend.exe | grep -i supabase` must return empty; enforce `supabase` in `--exclude-module` in PyInstaller spec |
| Tauri updater private key exposed via `VITE_` env var | Attacker publishes malicious "update" to all installed users | Never prefix with `VITE_`; review `import.meta.env.*` usage in `apps/frontend/src` before every release (GHSA-2rcp-jvr4-r259) |
| Flask backend bound to `0.0.0.0` instead of `127.0.0.1` | LAN-accessible API leaks LCU session data (Riot auth tokens) to any device on user's Wi-Fi | Hardcode `host='127.0.0.1'` in `socketio.run()`; assertion at startup if binding non-loopback |
| Sidecar reads Riot LCU lockfile → credentials in-memory → logs it | Riot LCU password written to log file; user uploads log for bug report; password leaked | Redact LCU auth from all log statements via a logging filter; test that `grep -i riot /path/to/log` never returns an auth-like pattern |
| CDN URL is public → dataset discoverable → scrape-of-a-scrape (Lolalytics → us → scraper) | Arguably fine (data is already public from Lolalytics). Still, document this in README so it's not a surprise | Explicit note in README and spec that the CDN is public by design; no ToS expectation of privacy |
| `%APPDATA%\...\logs\` with verbose output includes LCU Riot PUUID and summoner name | PII in local logs; user uploads without realizing | Log rotation + README "what's in the logs" section + optional log sanitizer CLI before upload |
| MSI installed per-user → other local users can read the installed binary and `%APPDATA%` | Low risk single-user home PC; higher risk shared family/school PC | Rely on Windows ACLs (default per-user install = user-only ACL); document |
| Auto-updater fetches HTTPS but TLS cert store is the bundled certifi | `certifi` bundle goes stale over years → expired root → update failures → lost users | Pin `certifi` in `requirements.txt` but include a release-checklist item to bump certifi every 6 months |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| "Backend disconnected" banner on every cold start for 1–2 s | User learns to distrust the banner; real disconnects ignored | Debounce banner by 5 s on cold start; show a "Starting up…" spinner first |
| SmartScreen dialog on first run with no guidance | User abandons install | README with screenshot walkthrough; "Run anyway" button highlighted |
| AV quarantines the portable exe silently (no UI feedback) | User thinks "I downloaded it but now it's gone" | Download page links to "If the file disappeared…" troubleshooting section |
| Update prompt mid-draft | User loses their recommendation during the exact moment the app matters | Defer updates when LCU reports champion-select active (Pitfall 11) |
| "Using cached data from YYYY-MM-DD" indicator is a tiny grey text | User doesn't notice stale data; blames recommendations when patch changes | Amber banner when cache > 48 h old; red when > 7 days |
| MSI install with no visible progress during ~80 MB copy | Feels frozen; user cancels mid-install | Standard WiX progress dialog (Tauri default) is acceptable; verify it actually appears on slow HDDs |
| First run silently downloads 10 MB of CDN data with no indicator | User thinks app is broken | Visible progress during first-run data fetch (spec §8 success criteria includes this) |
| "Restart Backend" button that kills and relaunches but doesn't clear the Vue state | Button does nothing visible; user concludes it's a dead button | Full re-connect cycle with banner transitions ("Restarting… → Reconnected"); Socket.IO rooms re-joined |
| LoL-client-waiting screen looks identical to app-broken screen | User reports "app is broken" when the real issue is League not running | Distinct copy: "Waiting for League of Legends to open…" with a LoL logo vs. red error banner |

---

## "Looks Done But Isn't" Checklist

Things that appear complete in demos / dev mode but are missing critical pieces for production on an unfamiliar user's machine.

- [ ] **Sidecar cleanup:** Works when the app closes normally. Verify by force-killing Tauri in Task Manager — Python child must also die (Job Object).
- [ ] **Cold start:** Works on the dev machine. Verify on a clean Windows 10 VM with no dev tooling, no Python installed, no antivirus exceptions.
- [ ] **SSL to CDN:** Works with `python backend.py`. Verify from `dist/backend.exe` that `certifi/cacert.pem` is bundled and a real HTTPS fetch succeeds.
- [ ] **Hidden imports:** Works in REPL. Verify Socket.IO round-trip from frontend against the built `.exe`, not the native Python.
- [ ] **Release artifacts:** `.msi` exists. Verify its SHA256 is published in release notes, not just in the workflow log.
- [ ] **Updater signing:** `latest.json` is signed. Verify the signing key is stored in three places (password manager, GitHub secret, offline backup).
- [ ] **Updater flow:** Prompt appears. Verify the whole cycle on a fresh VM: install v1.0.0 → tag v1.0.1 → updater detects → user installs → app relaunches on new version.
- [ ] **Offline first run:** Error banner appears. Verify a seed dataset exists so app is not just "error + empty screen".
- [ ] **Cache corruption recovery:** Happy path works. Verify by truncating `cache/champion_stats.json` to 0 bytes and relaunching — must self-heal.
- [ ] **Port allocation:** Allocation works in isolation. Verify when Vite (5173), Vue dev tools (8098), and another Tauri instance are all running.
- [ ] **Per-user install:** Installs. Verify it installs without admin prompt on a standard user account and without admin rights.
- [ ] **AV response:** "Works on my machine". Verify by scanning the portable exe with VirusTotal; ≤3 detections is the release gate.
- [ ] **Log location:** README says `%APPDATA%\{bundle_id}\logs\`. Verify the literal path with a real bundle_id value after install, because users paste the literal string `{bundle_id}` into File Explorer if we leave it a placeholder.
- [ ] **Mid-draft update safety:** Updater defers during draft. Verify by forcing an update while champion-select is active.
- [ ] **Hover-detection fix:** Code changed. Verify end-to-end that hovered enemy picks reduce enemy synergy weight and hovered ally picks affect ally synergy at reduced weight — not just "code exists".
- [ ] **Single-instance lock:** App starts. Verify that launching twice just focuses the existing window rather than spawning two sidecars fighting over LCU and port.
- [ ] **Data integrity at the CDN:** Published. Verify the validator passes (every `matchups.champion_id` references an existing `champion_stats.champion_id`).

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Lost Tauri private key (Pitfall 9) | **HIGH — user-visible churn** | (1) Generate new key pair. (2) New build under new bundle ID. (3) Publish "Please uninstall v1.x and install v2.0" announcement. (4) Expect 30–50 % churn; prepare a blog post explaining. |
| `latest.json` points to broken release (Pitfall 10) | **LOW** | (1) Revert `latest.json` on `gh-pages` to prior version. (2) Mark broken release as prerelease, not deleted. (3) Publish hotfix with bumped patch version. (4) Add prevention: version-rollback drill. |
| Mass AV quarantine (Pitfall 3) | **MEDIUM** | (1) Submit to `submit.microsoft.com` within hours. (2) Rebuild bootloader, re-release. (3) Pin README "AV troubleshooting" section to GitHub repo front page. (4) Consider Nuitka migration from backlog. |
| Cache corruption across user base (Pitfall 13) | **LOW (if recovery code exists)** | App self-heals on next start. If deployment-wide (e.g., new ETL published a structurally bad JSON): roll back the `gh-pages` commit, clients re-fetch. |
| Partial-data publication (Pitfall 16) | **LOW** | (1) Revert `gh-pages` commit. (2) CDN serves prior consistent data. (3) Investigate ETL race. (4) Fix staging migration. |
| Stuck in stale-CDN loop (Pitfall 15) | **LOW** | (1) Manually purge Fastly cache (not user-controllable on free Pages). (2) Bump manifest timestamp to force all clients to refetch. (3) Long-term: move to content-addressed filenames. |
| Orphan `backend.exe` processes on user machines (Pitfall 1) | **MEDIUM** | (1) Ship v1.0.1 with Job Object. (2) On startup, new version kills any `backend.exe` not owned by its own Tauri parent. (3) One-time cleanup handles accumulated zombies. |
| User can't launch app due to SmartScreen (Pitfall 8) | **LOW per user, HIGH at scale** | Per-user: README screenshots. At scale: if friction is dominating, buy EV cert (~$200–400/year) — pre-approved in backlog. |
| `json_repo` ↔ `supabase_repo` signature drift (Pitfall 12) | **MEDIUM** | Ship hotfix with contract tests. Add mypy strict to CI so next drift is caught at PR time. |

---

## Pitfall-to-Phase Mapping

Assumes roadmap phases along the delivery-form spec: **Packaging** (PyInstaller + Tauri bundle), **CDN** (export script + `json_repo.py` + gh-pages), **Lifecycle** (sidecar spawn/ready/kill + IPC), **Distribution** (release workflow + README + SmartScreen/AV handling), **Auto-update** (updater keys + `latest.json` + mid-draft deferral).

| # | Pitfall | Prevention Phase | Verification |
|---|---------|------------------|--------------|
| 1 | Orphan sidecar processes | Lifecycle | Kill Tauri in Task Manager, assert `backend.exe` count returns to 0 within 1 s |
| 2 | Missing hidden imports | Packaging | CI smoke test: built `.exe` + Socket.IO round-trip |
| 3 | UPX → AV quarantine | Packaging | VirusTotal ≤3 detections + grep `upx=False` in spec + Microsoft false-positive submitted |
| 4 | Ready-file/webview race | Lifecycle | Cold-start smoke test on `windows-latest`, 50× runs, zero flaky-banner sightings |
| 5 | Port allocation TOCTOU | Lifecycle | Repeat cold-start under `windows-latest` with Vite+5173 occupied, 20× success |
| 6 | Path resolution bugs | Packaging | Unit test: `cache_dir() != bundled_resource('.')` ; integration test: cache survives restart |
| 7 | SSL verification failure | Packaging | Integration test: built `.exe` fetches CDN JSON over HTTPS successfully |
| 8 | SmartScreen "Unknown publisher" | Distribution | README has screenshot walkthrough; release notes front-load MSI with friction warning |
| 9 | Lost updater private key | Auto-update + Distribution | Release checklist: key present in password-manager + GH secret + offline backup |
| 10 | `latest.json` points to yanked release | Auto-update | `latest.json` lives on `gh-pages`, not as a release asset; rollback procedure documented and rehearsed |
| 11 | Mid-draft force-update | Auto-update + Lifecycle | E2E test: trigger update while `/api/draft/active` returns true → update deferred |
| 12 | Repo signature drift | CDN | mypy --strict on `backend.py` imports + contract tests for every public `json_repo` function |
| 13 | Cache corruption not recoverable | CDN + Lifecycle | Test: truncate cache file → relaunch → self-heal + log event |
| 14 | Offline first-run UX | CDN + Distribution | Seed dataset bundled; QA on network-disabled VM shows functional state |
| 15 | Stale CDN at edge | CDN | Manifest-based versioning or `?v=timestamp` cache-bust + canary Action every 30 min |
| 16 | ETL/export race | CDN | Staging-schema swap + integrity validator in export step |
| 17 | `gh-pages` bloat | CDN | Force-push orphan deploy; measure branch history size monthly |
| 18 | MSI vs portable confusion | Distribution + Lifecycle | Distinct bundle IDs + single-instance lock + README FAQ |

---

## Sources

- Tauri sidecar PyInstaller multi-process cleanup — [tauri-apps/tauri#11686](https://github.com/tauri-apps/tauri/issues/11686), [tauri-apps/tauri#5611](https://github.com/tauri-apps/tauri/issues/5611), [discussion #3273](https://github.com/tauri-apps/tauri/discussions/3273), [discussion #5870](https://github.com/tauri-apps/tauri/discussions/5870), [Tauri v2 sidecar docs](https://v2.tauri.app/develop/sidecar/).
- PyInstaller Flask-SocketIO hidden-imports — [Flask-SocketIO#259](https://github.com/miguelgrinberg/Flask-SocketIO/issues/259), [python-socketio#633](https://github.com/miguelgrinberg/python-socketio/issues/633), [pyinstaller#4292](https://github.com/pyinstaller/pyinstaller/issues/4292).
- PyInstaller AV false-positives / UPX — [pyinstaller#6754](https://github.com/pyinstaller/pyinstaller/issues/6754), [pyinstaller#8164](https://github.com/pyinstaller/pyinstaller/issues/8164), [upx#711](https://github.com/upx/upx/issues/711), [pythonguis.com guide](https://www.pythonguis.com/faq/problems-with-antivirus-software-and-pyinstaller/), [Nuitka migration article](https://dev.to/weisshufer/from-pyinstaller-to-nuitka-convert-python-to-exe-without-false-positives-19jf).
- PyInstaller `sys._MEIPASS` vs `__file__` — [Run-time Information docs](https://pyinstaller.org/en/stable/runtime-information.html), [pyinstaller#7127](https://github.com/pyinstaller/pyinstaller/issues/7127), [discussion #7449](https://github.com/orgs/pyinstaller/discussions/7449).
- PyInstaller + certifi + requests SSL — [pyinstaller#7229](https://github.com/pyinstaller/pyinstaller/issues/7229), [Azure/azure-iot-sdk-python#991](https://github.com/Azure/azure-iot-sdk-python/issues/991), [SSL fix guide](https://sslinsights.com/fix-certificate-verify-failed-error-in-python/).
- Tauri updater key handling — [Tauri v2 updater plugin docs](https://v2.tauri.app/plugin/updater/), [GHSA-2rcp-jvr4-r259 advisory](https://github.com/tauri-apps/tauri/security/advisories/GHSA-2rcp-jvr4-r259), [tauri-action#950](https://github.com/tauri-apps/tauri-action/issues/950), [Gurjot Tauri updater guide](https://thatgurjot.com/til/tauri-auto-updater/).
- Tauri Windows installer per-user + APPDATA — [Tauri Windows Installer docs](https://v2.tauri.app/distribute/windows-installer/), [Tauri v2 file system plugin](https://v2.tauri.app/plugin/file-system/), [tauri#7491 EBWebView permissions](https://github.com/tauri-apps/tauri/issues/7491).
- Tauri AV detections — [tauri#2486](https://github.com/tauri-apps/tauri/issues/2486), [tauri#4749](https://github.com/tauri-apps/tauri/issues/4749).
- SmartScreen behavior — [alphr SmartScreen guide](https://www.alphr.com/windows-protected-your-pc-disable-smartscreen/), [msp360 KB](https://kb.msp360.com/backup/warnings/ms-defender-smart-screen), community discussions on [pulumi#14450](https://github.com/pulumi/pulumi/issues/14450) and [ente-io/ente#2496](https://github.com/ente-io/ente/issues/2496).
- Port allocation TOCTOU — [Binding on port zero](https://eklitzke.org/binding-on-port-zero), [Bind before connect](https://idea.popcount.org/2014-04-03-bind-before-connect/), [containers/podman#19048](https://github.com/containers/podman/issues/19048).
- GitHub Pages caching / CDN — [GitHub community discussion #11884](https://github.com/orgs/community/discussions/11884), [GitHub community discussion #49753](https://github.com/orgs/community/discussions/49753), MDN [Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control).
- Project context — `.planning/PROJECT.md`, `docs/superpowers/specs/2026-04-14-delivery-form-design.md`, `.planning/codebase/CONCERNS.md`.

---
*Pitfalls research for: Tauri + PyInstaller + GitHub Pages CDN delivery to non-technical Windows users*
*Researched: 2026-04-14*
