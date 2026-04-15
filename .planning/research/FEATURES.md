# Feature Research — Desktop Delivery Surface

**Domain:** Windows desktop installer/updater UX for a bundled-backend + CDN-read-path app, targeted at non-technical gaming-adjacent users
**Researched:** 2026-04-14
**Confidence:** HIGH (grounded in the approved delivery-form spec §4–§8 and corroborated by current Tauri v2 + Windows platform conventions; gaming-specific UX expectations are MEDIUM, extrapolated from adjacent tools)

Scope note: The underlying draft analyzer (recommendations, LCU integration, champion lookup) is already shipped and intentionally not researched here. This document is strictly about the delivery surface — how the app arrives on the user's machine, comes up on first run, keeps itself current, fails gracefully, and produces diagnostics.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features a non-technical Windows gamer assumes will exist. Missing any of these makes the app feel broken, sketchy, or "not finished" and causes abandonment before value is delivered.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single downloadable Windows installer on the GitHub Release page (`.msi`) | Matches what they get from every other Windows app (Discord, OBS, Riot Client itself) — double-click → installed | LOW (built-in Tauri bundler target) | Spec §4.3 commits to `.msi` as primary; portable `.exe` is secondary. `.msi` is the artifact users pick by default because it looks "official." |
| Per-user install that works without admin rights | Gaming-adjacent tools are run on personal machines where users don't necessarily have admin; asking for UAC prompt every update is friction | LOW (Tauri `perMachine: false` setting in `tauri.conf.json`) | Spec §8 Installation criterion: "Installer completes on clean Windows 10 and Windows 11 without requiring admin rights." Aligns with `%LOCALAPPDATA%\Programs\` default install location. |
| Start Menu entry with app name and icon | Windows users launch apps from Start Menu; no Start Menu entry = "where did it go?" | LOW (Tauri handles automatically) | Spec §8 Installation criterion explicitly required. Must include a recognizable icon; default blank icon looks unfinished. |
| Desktop shortcut option during install | Gaming users expect a desktop icon for fast relaunch before every play session | LOW (WiX/NSIS built-in; Tauri exposes) | Not explicitly in spec §8 but universally expected by the target audience. Offer as a checked-by-default option. |
| Working uninstaller registered in Windows "Apps & features" / "Add or remove programs" | Users revoke trust by uninstalling; an app that can't be cleanly removed is "malware-like" | LOW (Tauri bundler handles) | Spec §8: "Uninstaller removes the app and its cache, optionally preserving user settings (none in v1)." Must remove the `%APPDATA%\{bundle_id}\` tree including logs/cache or leave clearly documented residue. |
| SHA256 hash published in GitHub Release notes | Security-minded users verify; more importantly, AV-triggered users need a way to confirm they have the official artifact | LOW (one CI step: `sha256sum` into release body) | Spec §4.4 step 6 + §8 Build&distribution criterion. Publish BOTH `.msi` and portable `.exe` hashes. |
| README troubleshooting section covering SmartScreen bypass and AV false-positive guidance | First-launch SmartScreen warning is the #1 abandonment point for unsigned apps; without "More info → Run anyway" instructions, users bounce | LOW (documentation only) | Spec §8 Documentation criterion. Include screenshots of the SmartScreen dialog — non-technical users pattern-match on visuals, not text. |
| Visible progress during first-run CDN data download | A blank window for 10+ seconds on first run reads as "hung / crashed"; users force-quit | MEDIUM (progress UI in Vue + wire-up from sidecar fetch events via Socket.IO or HTTP polling) | Spec §8 First-run criterion. Must show per-file or overall % progress with the current table name, not a generic spinner. |
| Clear, actionable offline-first-run error | "Can't reach servers" with a Retry button, not a stack trace | LOW (Vue error view + retry calling the sidecar) | Spec §7 table row "CDN unreachable on first run" + §8 First-run criterion. Must suggest checking internet connection explicitly. |
| Backend-disconnected banner with Restart button | When the Python sidecar dies mid-session, silent failure destroys trust; banner + one-click recovery preserves it | MEDIUM (Tauri event `backend-disconnected` → Vue banner → Tauri command `restart_backend`) | Spec §5.2 + §7. This is the single most important error-state affordance because sidecar crashes are the most probable runtime failure mode. |
| "Waiting for League of Legends…" view when LCU is not running | The app is useless without LoL; users need to see it's ready, not broken | LOW (existing LCU detection in `league_client_auth.py` + a simple full-screen state) | Spec §7 table + §8 Runtime criterion ("LoL client is detected within 3 s of being started"). Must poll and recover without user action. |
| Auto-update prompt at app start when a new version exists | Unprompted silent updates feel untrustworthy; no update mechanism at all means users run old buggy versions forever | MEDIUM (Tauri v2 updater plugin — ships with a default dialog UI) | Spec §5 key decision + §8 Auto-update criteria. Tauri v2's built-in dialog shows release notes (from the `note` field of `latest.json`) and Install / Later buttons. On Windows, installing the update auto-closes the app, which is standard behavior. |
| Local log files written to the conventional Windows app-data location | When users report bugs, the maintainer's first ask is "send your log file"; logs must be findable and not require admin rights to read | LOW (Python `logging` + Tauri `log` crate, both writing to the app-data-dir) | Spec §7.2: `%APPDATA%\{TAURI_BUNDLE_ID}\logs\backend-<YYYY-MM-DD>.log`. `%APPDATA%` (Roaming) is correct for per-user app-specific files that follow the user across devices; this is consistent with Microsoft guidance and matches what tools like Discord and VS Code do. |
| README documents log-folder path | Users can't attach logs to bug reports if they can't find them | LOW (documentation only) | Spec §8 Documentation criterion. Include the literal string `%APPDATA%\{bundle_id}\logs\` so users can paste it into the Windows Run dialog. |
| Cached-data staleness indicator when running on stale CDN data | A silent offline mode that serves 30-day-old matchup data without telling the user damages the recommendation quality without explanation | LOW (timestamp check on cache meta + small banner/badge) | Spec §7 table rows "CDN unreachable on later run" and "Cache older than 7 days." Show last-update date so users know what they're looking at. |

### Differentiators (Competitive Advantage)

Polish features that raise the bar above the "it works" baseline and signal care. Not required for launch but meaningfully improve perceived quality for gaming-adjacent users who are accustomed to the Riot / Discord / Steam aesthetic.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Installer shows a release-notes preview on the update prompt | Users who see "what's new" trust updates more and are less likely to postpone indefinitely | LOW (populate `note` field in `latest.json` from CHANGELOG — Tauri's default dialog renders it) | Spec §4.3 uses `latest.json`. Keep notes short and gameplay-relevant ("Fixed: hovered picks now correctly factored in") — not changelog jargon. |
| Update prompt offers "Install on next launch" in addition to "Install now" and "Later" | Respects the mid-draft reality — users should never be forced to interrupt champion select for an update | MEDIUM (requires custom updater UI via `@tauri-apps/api/updater`; the built-in dialog only offers immediate install + later) | Per the Tauri v2 updater docs, disabling the built-in dialog is required to gain this level of control. Explicitly aligns with the §10 anti-feature "no silent force-updates mid-draft." |
| First-run splash / welcome screen with ≤3 lines of context ("Launch League, start a draft, see recommendations") | Reduces "what do I do now?" confusion; installs confidence that the app knows what it's doing | LOW (static Vue view shown once, dismissed into memory) | Spec has no explicit requirement; fits inside the "first-run UX" active item. Keep it brief — gamers dismiss anything longer than a tooltip. |
| "Open log folder" button inside the app | Eliminates the "navigate to `%APPDATA%\...`" friction when filing a bug report | LOW (Tauri `shell.open` with the logs path) | Removes one of the most common support-flow frustrations. Pairs with the "Report a bug" link pointing at the GitHub Issues page. |
| "Copy diagnostics" button that copies app version + OS build + last 100 log lines to clipboard | Non-technical users paste this into a GitHub issue or Discord message without touching the filesystem | MEDIUM (Tauri command to read log tail + system info + clipboard write) | Differentiator because few indie gaming tools do this well, and it dramatically improves bug-report signal-to-noise. Must NOT include any LCU auth tokens from logs — redact. |
| Portable `.exe` as a secondary artifact for power users / shared gaming rigs | Users on locked-down PCs or shared machines can run without any install; lowers friction for a noticeable slice of the audience | LOW (Tauri bundler target, same build) | Spec §4.3 + §8 Build&distribution criterion. Confirmed in-scope. |
| Signed updater manifest (`latest.json` signed via Tauri's Ed25519 signing) | Prevents a hijacked CDN from pushing a malicious update; the signing key is cheap (free via `tauri signer generate`) and distinct from expensive EV code signing | MEDIUM (key generation, CI secret storage, signing step) | Spec §4.3 + §4.4 — already in scope. This is effectively free supply-chain integrity. Worth calling out because users won't see it, but it's the one security property that survives the no-EV-cert constraint. |
| Version number visible in the app (title bar or About dialog) | Users and the maintainer both need this to correlate bug reports with releases | LOW (read from Tauri `app::getVersion()`) | Not explicitly in spec §8, but standard desktop-app hygiene. Missing version info turns every bug report into a guessing game. |
| Rollout cadence: patch releases auto-update, minor/major releases prompt with more prominent notes | Matches user expectations — small fixes should be silent-ish; feature-adding releases should be announced | MEDIUM (requires custom updater UI; channel handling in `latest.json`) | Tauri's built-in updater does not differentiate by semver category. Implementing this requires the custom-UI path. Skippable for v1. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem like obvious additions but create problems, violate the spec's Out-of-Scope list, or undermine the "zero-friction, privacy-preserving delivery" core value. Each row maps directly to spec §10 or the PROJECT.md Out-of-Scope section.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Silent / force-install updates that apply mid-session | "Always up to date with no interruption" | Installing an update mid-draft destroys the session (Tauri/Windows auto-exits the app to run the installer) — catastrophic UX during champion select; also feels hostile | Prompt-based updater with "Install now" / "Later" / (differentiator) "Install on next launch" — user always controls the moment |
| Telemetry / usage analytics | "We'd know what's broken" | Spec §10 + PROJECT.md constraint: v1 is privacy-preserving; no network calls beyond CDN + LCU. Adding telemetry breaks the stated privacy property and invites AV/firewall flags | Local logs + user-initiated "Copy diagnostics" button; telemetry only if later added as opt-in |
| Crash-reporting SaaS (Sentry, Bugsnag, etc.) | "Auto-capture crashes without asking the user" | Same as telemetry — plus it introduces a runtime dependency, a third-party network destination, and a privacy-policy obligation that a non-commercial v1 doesn't want | Structured local logs in `%APPDATA%\{bundle_id}\logs\` + user-initiated attachment on bug report |
| Code signing with an EV certificate to eliminate SmartScreen entirely | "Users see scary warnings; signing fixes it" | Spec §10 + PROJECT.md constraint: $200–400/year cost not justified for a non-commercial v1. Introduces a funding requirement and key-management burden | Procedural mitigation: UPX off, SHA256 in notes, README SmartScreen walkthrough, Microsoft false-positive submission per release |
| Auto-launch on Windows startup | "Always ready when I launch LoL" | Consumes RAM and background CPU when the user isn't playing; triggers "what is this running?" reactions; users associate unsolicited startup with adware | Fast cold-start instead; the app is useful enough only when LoL is running anyway, so starting-with-LoL (via process watcher) would be the right pattern if ever added — but not v1 |
| System-tray presence / minimize-to-tray | "Keep it ready without a taskbar entry" | Adds lifecycle complexity (tray vs window close semantics, per-user tray-icon settings), hides the app from users who then think it's closed when it isn't, and again invokes the "running silently in background" reaction | Normal window close = full exit; relaunch cost is low because the app is small |
| User settings / preferences UI (theme, language, role override, hotkeys) | "Every app has settings" | Spec §10: explicitly deferred — "no settings shipped in v1." Adds storage layer, migration concerns, and testing surface with zero v1 value since sensible defaults cover the use case | Ship with good defaults; add a Settings view only when a concrete v1.x need emerges, store via `@tauri-apps/plugin-store` |
| In-app changelog / "What's New" page beyond the updater release notes | "Polish" | Maintenance cost per release; duplicates the GitHub Releases page; users don't read it | Put release notes in the updater prompt's `note` field (already covered); link to GitHub Releases for full history |
| Multi-channel updates (stable / beta) | "Power users want to test upcoming features" | Tauri v2 updater supports channels but requires separate `latest.json` per channel, CI branching, and user-visible channel selection UI. For a single-maintainer v1 it's overhead without clear demand | Single stable channel only; power users can watch the GitHub repo for prereleases |
| macOS/Linux builds | "Cross-platform is modern" | Spec §10 + PROJECT.md constraint: LoL on macOS has ~5% share and no Linux support from Riot; build-matrix cost is non-trivial (separate signing, separate AV story, separate update manifest) | Windows-only for v1; backlog if user demand materializes |
| In-app update for the bundled champion/matchup data (as opposed to code updates) | "Daily data refresh without waiting for the app to restart" | Already solved structurally by the CDN cache + conditional GET at startup (spec §6.4). Adding a live-refresh UI surface invites race conditions during an active draft | Keep current behavior: conditional GET at backend startup, silent background re-fetch every 10 minutes when CDN is reachable (spec §7) |
| Machine-specific licensing / account login | "Track entitlements, reduce piracy, enable user accounts" | Non-commercial release; adds a server dependency, a credential store, and friction that destroys the "zero-friction delivery" Core Value | None — the app is free and anonymous |

---

## Feature Dependencies

```
Tauri updater wired to GitHub Releases
   ├── requires ──> Signed latest.json (Ed25519 key pair, CI secrets)
   ├── requires ──> CI release workflow produces .msi + portable .exe on v* tag
   └── enables  ──> Auto-update prompt UX
                        └── enables ──> "Install on next launch" variant (differentiator, needs custom updater UI)

CI release workflow
   ├── requires ──> PyInstaller sidecar build stage (backend.exe)
   ├── requires ──> Vite frontend build
   ├── requires ──> Tauri bundle stage
   └── enables  ──> SHA256 hash publication in release notes
                        └── enables ──> README SmartScreen/AV troubleshooting with hash-verification step

Dynamic port allocation + sidecar lifecycle (spec §5)
   ├── requires ──> backend.py --port and --ready-file CLI args
   ├── requires ──> Tauri host Rust code (TcpListener, spawn, Job Object)
   └── enables  ──> backend-disconnected banner + Restart button
                        └── enables ──> "Open log folder" and "Copy diagnostics" differentiators

CDN JSON read path (spec §6)
   ├── requires ──> json_repo.py replacing supabase_repo on runtime path
   ├── requires ──> GitHub Actions export step + gh-pages branch + Pages config
   └── enables  ──> First-run progress UI
                        └── enables ──> Cached-data staleness indicator
                        └── enables ──> Offline graceful-degradation UX

Structured logging to %APPDATA%\{bundle_id}\logs\
   ├── required by ──> User-reported bug diagnosis (the whole "no telemetry" stance depends on good local logs)
   └── enables  ──> "Open log folder" and "Copy diagnostics" differentiators

README documentation
   ├── requires ──> Finalized bundle_id, CDN URL, installer filenames, log path
   └── required by ──> SmartScreen-bypass user flow (non-technical users need screenshots to pattern-match)
```

### Dependency Notes

- **Auto-update UX depends on Tauri updater being wired end-to-end.** The built-in dialog requires `latest.json` to be reachable and correctly signed; without the signing key, the updater refuses to run. This is the one tech-plumbing dependency that blocks the entire update-experience feature cluster.
- **Backend-disconnected banner depends on the sidecar-lifecycle plumbing.** The Tauri host must emit the `backend-disconnected` event on child exit (spec §5.2); without that plumbing, the frontend has no way to distinguish "backend crashed" from "backend is busy." No event wiring = no recovery UX.
- **First-run progress UI depends on the `json_repo` fetch code emitting progress events.** The Python sidecar needs to stream progress (either via Socket.IO to the already-connected frontend, or via polled HTTP) as each table downloads. This is a small but non-zero change beyond the plain `json_repo.fetch_json` shown in spec §6.3.
- **"Copy diagnostics" depends on log rotation being stable.** If logs grow unbounded, reading "the last 100 lines" works; if rotation drops the current file mid-read, the copy fails. Daily rotation (spec §7.2) is fine.
- **SmartScreen bypass documentation conflicts with NO mitigation.** Without the README, the SHA256 hashes and UPX-off decision are invisible to users — they see the scary dialog and bounce. The docs are the user-facing half of the AV story; cheap to produce, high payoff.

---

## MVP Definition

### Launch With (v1)

Minimum viable delivery surface — without these, non-technical users abandon before reaching the underlying (already-shipped) value.

- [ ] `.msi` installer + portable `.exe`, both published as GitHub Release assets on `v*` tags — spec §4.3, §8
- [ ] SHA256 hashes in release notes — spec §4.4, §8
- [ ] Per-user install without admin rights, Start Menu entry, working uninstaller — spec §8
- [ ] First-run CDN download with visible per-table progress and offline error fallback — spec §7, §8
- [ ] Backend-disconnected banner with Restart button — spec §5.2, §7
- [ ] "Waiting for League of Legends…" view when LCU is absent — spec §7
- [ ] Cached-data staleness indicator when CDN is unreachable or cache is older than 7 days — spec §7
- [ ] Tauri updater wired to signed `latest.json` on GitHub Releases — spec §5 key decision, §8
- [ ] Default Tauri updater prompt UX (Install / Later buttons, release notes shown from `note` field) — no custom UI in v1
- [ ] Structured Python + Rust logs to `%APPDATA%\{bundle_id}\logs\` with daily rotation — spec §7.2
- [ ] README covers: download link, SmartScreen "More info → Run anyway" walkthrough with screenshots, AV false-positive guidance, hash verification, log folder path — spec §8

### Add After Validation (v1.x)

Differentiators that move the experience from "works" to "polished." Triggers are real user feedback, not speculation.

- [ ] "Open log folder" button in the app — trigger: second bug report that stalls on "where are my logs?"
- [ ] "Copy diagnostics" button (version + OS + log tail → clipboard) — trigger: third bug report with unreadable screenshots instead of pasted text
- [ ] "Install on next launch" option in the update prompt (requires custom updater UI) — trigger: a user reports a mid-draft forced-update interruption
- [ ] Desktop shortcut option during install — trigger: users asking how to pin the app
- [ ] Version number visible in title bar / About dialog — trigger: bug report with no version info
- [ ] First-run welcome screen with a ≤3-line quickstart — trigger: new-user confusion reports

### Future Consideration (v2+)

Explicit defers, all cross-referenced to spec §10 or PROJECT.md Out-of-Scope.

- [ ] Settings / preferences UI — defer per spec §10 until a concrete need emerges
- [ ] macOS / Linux builds — defer per spec §10 / PROJECT.md (~5% LoL share on macOS, no Linux support from Riot)
- [ ] EV code signing / Microsoft Trusted Signing to eliminate SmartScreen — defer per spec §10 until AV friction dominates user feedback and funding is available
- [ ] Opt-in telemetry / crash reporting — defer per spec §10; if ever added must be opt-in and explicitly documented
- [ ] Multi-channel updates (stable / beta) — defer; single channel suffices for current release cadence
- [ ] Nuitka migration away from PyInstaller — defer per spec §10 unless AV reports become frequent

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `.msi` installer + Start Menu + uninstaller | HIGH | LOW (Tauri bundler defaults) | P1 |
| SHA256 hashes in release notes | MEDIUM (essential for AV-hit users, invisible to others) | LOW | P1 |
| README SmartScreen + AV walkthrough with screenshots | HIGH | LOW | P1 |
| First-run CDN download progress UI | HIGH (prevents "app is hung" abandonment) | MEDIUM (progress events from sidecar) | P1 |
| Offline-first-run error state with Retry | HIGH | LOW | P1 |
| Backend-disconnected banner + Restart button | HIGH | MEDIUM (Tauri event + Rust command + Vue banner) | P1 |
| LoL-client-waiting view | HIGH | LOW (existing detection + simple view) | P1 |
| Cached-data staleness indicator | MEDIUM | LOW (meta timestamp + small badge) | P1 |
| Tauri updater with signed `latest.json`, default prompt UX | HIGH | MEDIUM (signing key, CI secrets, `latest.json` generation) | P1 |
| Logs to `%APPDATA%\{bundle_id}\logs\` with daily rotation | HIGH (required by the "no telemetry" stance) | LOW | P1 |
| README log-folder documentation | MEDIUM | LOW | P1 |
| Portable `.exe` secondary artifact | MEDIUM | LOW (same build, different bundler target) | P1 |
| Version number visible in-app | MEDIUM | LOW | P2 |
| "Open log folder" button | MEDIUM | LOW | P2 |
| "Copy diagnostics" button | HIGH (for bug-report quality) | MEDIUM (log tail + redaction + clipboard) | P2 |
| First-run welcome screen | LOW | LOW | P2 |
| Desktop shortcut during install | LOW | LOW | P2 |
| "Install on next launch" update option | HIGH (avoids mid-draft interruption) | MEDIUM-HIGH (custom updater UI) | P2 |
| Multi-channel (stable/beta) updates | LOW | MEDIUM | P3 |
| Settings UI | LOW (v1) | MEDIUM | P3 |
| EV code signing | MEDIUM (removes SmartScreen entirely) | HIGH (cost + key mgmt) | P3 |

**Priority key:**
- P1: Must have for v1 launch — mapped to spec §8 acceptance gates
- P2: Should have, add post-launch based on user feedback
- P3: Explicit defer per spec §10 / PROJECT.md Out of Scope

---

## Competitor / Reference Feature Analysis

Reference points are tools in the same "unsigned, indie, gaming-adjacent, Windows desktop" category that the target user has likely installed before. Goal: calibrate expectations, not copy.

| Feature | OBS Studio (signed, polished) | Blitz.gg (LoL companion, heavily signed & funded) | Mobalytics desktop (LoL companion, signed) | Small indie PyInstaller-based tools | Our v1 approach |
|---------|--------------------------------|----------------------------------------------------|---------------------------------------------|---------------------------------------|-----------------|
| Installer format | `.exe` installer + portable | `.exe` (custom installer) | `.exe` (custom installer) | Often just a raw `.exe`, no installer — high friction | `.msi` + portable `.exe` — matches polished norms |
| Code signing | Yes (signed) | Yes (EV) | Yes (EV) | Rarely | No (procedural mitigation only) — matches indie-tool norms, below polished norms |
| Auto-update | Built-in updater with prompt | Silent background updates | Built-in updater | Usually none; manual re-download | Tauri updater with prompt — good middle ground |
| First-run data download | Offline-first bundled assets | Heavy network-dependent onboarding (login, setup) | Heavy network-dependent onboarding | None — preloaded or no data | CDN fetch with progress — lighter than Blitz-class tools, more than bundled |
| Telemetry | Anonymous opt-out | Extensive (usage, match data, crashes) | Extensive | Rarely | None (privacy-preserving) — deliberate differentiator |
| Start Menu / shortcuts | Yes | Yes, also auto-launch + tray | Yes, also auto-launch | Depends | Yes; no tray, no auto-launch (anti-feature per spec) |
| SmartScreen behavior | No warning (signed + reputation) | No warning (signed + reputation) | No warning (signed + reputation) | Warning on every install | Warning mitigated by README walkthrough only |

**Takeaway:** Our target comparison is closer to "polished indie" than "funded companion app." The delivery surface should feel as clean as OBS's (installer, updater, clear errors, local logs), while deliberately NOT copying the Blitz/Mobalytics model (account login, heavy telemetry, auto-launch, tray presence). The privacy-preserving stance and the absence of an account login are themselves differentiators in the LoL-companion space.

---

## Sources

Approved spec (authoritative, HIGH confidence):
- `.planning/PROJECT.md` — Core Value, Active requirements, Out of Scope
- `docs/superpowers/specs/2026-04-14-delivery-form-design.md` — §4 Build pipeline, §5 Lifecycle, §6 CDN read path, §7 Error handling, §7.2 Logging, §8 Success criteria, §10 Out-of-scope

Tauri v2 updater UX behavior (HIGH confidence — official docs):
- [Updater plugin — Tauri v2 docs](https://v2.tauri.app/plugin/updater/) — built-in dialog shows release notes from `note` field; `@tauri-apps/api/updater` required for custom UI; on Windows the app auto-exits during install
- [Dialog plugin — Tauri v2 docs](https://v2.tauri.app/plugin/dialog/)

Tauri v2 updater practical integration (MEDIUM confidence — community):
- [How to make automatic updates work with Tauri v2 and GitHub — That Gurjot](https://thatgurjot.com/til/tauri-auto-updater/)
- [Tauri v2 with Auto-Updater — CrabNebula docs](https://docs.crabnebula.dev/cloud/guides/auto-updates-tauri/)
- [Tauri v2 updater — Ratul's Blog](https://ratulmaharaj.com/posts/tauri-automatic-updates/)

Windows platform conventions (HIGH confidence — Microsoft Learn):
- [Best location for app-generated log files — Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/793928/best-location-for-app-generated-log-files) — confirms `%APPDATA%` as the conventional location for per-user app logs
- [AppData folder explained — Windows Central](https://www.windowscentral.com/software-apps/windows-11/what-is-the-appdata-folder-windows-11-app-data-storage-explained) — Roaming vs Local vs LocalLow semantics

SmartScreen bypass UX (MEDIUM confidence — covered by multiple community sources):
- [How to Bypass the Windows Defender SmartScreen warning (Medium)](https://medium.com/@techworldthink/how-to-bypass-the-windows-defender-smartscreen-prevented-an-unrecognized-app-from-starting-85ae0d717de4)
- [4 Best Ways to Bypass Windows Defender SmartScreen Warning — Fortect](https://www.fortect.com/windows-optimization-tips/windows-defender-smartscreen-prevented-an-unrecognized-app-from-starting-warning/)
- [Microsoft Q&A — SmartScreen on signed apps](https://learn.microsoft.com/en-us/answers/questions/5584097/how-to-bypass-windows-defender-smartscreen-even-af)

NSIS / installer conventions (HIGH confidence — NSIS official):
- [NSIS Best Practices](https://nsis.sourceforge.io/Best_practices)
- [Simple installer with Start Menu shortcut and uninstaller — NSIS](https://nsis.sourceforge.io/A_simple_installer_with_start_menu_shortcut_and_uninstaller)

---

*Feature research for: Windows desktop delivery surface of LoL Draft Analyzer v1*
*Researched: 2026-04-14*
