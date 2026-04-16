# LoL Draft Analyzer

A real-time League of Legends draft assistant that recommends champions during champion select based on your team composition, enemy picks, and current meta data.

Built with a custom scoring algorithm that combines base champion strength, counter matchups, and team synergy — weighted and normalized using [Wilson Score confidence intervals](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval).

---

## Download and Install

Download the latest release from **[GitHub Releases](https://github.com/Chertixd/LoL-Draft-Helper/releases/latest)**.

Two installer options are available:

- **MSI installer** (recommended): Double-click the `.msi` file. Installs per-user (no admin rights required), creates a Start Menu entry, and registers a clean uninstaller in Add/Remove Programs.
- **Portable setup** (NSIS `-setup.exe`): Self-extracting installer with a setup wizard. Same application content, installs per-user without admin rights. Choose this if your organization blocks `.msi` files.

Both options install the same application. See the [MSI vs Portable FAQ](#msi-vs-portable-faq) below for details.

---

## SHA256 Verification

Each GitHub Release includes SHA256 hashes in the release notes. Verify your download matches:

```powershell
(Get-FileHash "LoL-Draft-Analyzer_1.0.0_x64_en-US.msi" -Algorithm SHA256).Hash
```

Compare the output against the hash listed in the release notes. If they do not match, re-download the file or report the discrepancy.

---

## Windows SmartScreen

Because the app is not code-signed, Windows SmartScreen will show a warning on first run:

1. A dialog appears: **"Windows protected your PC"**.
2. Click **"More info"** (the link text below the warning message).
3. Click **"Run anyway"**.
4. This only happens on first run. Windows remembers the choice for subsequent launches.

This warning is normal for unsigned applications and does not indicate malware. You can verify the file integrity using the [SHA256 hash](#sha256-verification) above.

---

## Antivirus False Positives

PyInstaller-packaged applications sometimes trigger false-positive detections from antivirus software. If your AV flags the application:

1. **Verify the SHA256 hash** matches the value published in the GitHub Release notes.
2. **Add an exclusion** in your antivirus for the install directory if needed.
3. **Report the false positive** to Microsoft: <https://www.microsoft.com/en-us/wdsi/filesubmission>
4. The app makes **no network calls** except to the GitHub Pages CDN (for champion data) and the local League of Legends client. No telemetry, no phoning home.

If false positives persist with your AV vendor, check the GitHub Issues page for known workarounds.

---

## Features

- **Real-time draft tracking** via League Client integration (WebSocket)
- **Champion recommendations** scored by base strength + counter matchups + team synergy
- **Role-aware importance matrices** (e.g. top-vs-top is weighted higher than top-vs-bot)
- **Blind pick mode** when no enemy picks are available yet
- **Hover detection** — reduces weight of uncertain enemy/ally picks
- **Auto-update** via the built-in Tauri updater (checks on app start)
- **CDN data pipeline** updating champion stats daily via GitHub Actions
- **Per-user installation** with no admin rights required

---

## How the Score Works

Each recommended champion gets a **Final Score (0-100)**:

```
Final Score = (Base Score x 30%) + (Counter Score x 45%) + (Synergy Score x 25%)
```

- **Base Score** -- How strong is this champion in the current meta (win rate + pick rate)?
- **Counter Score** -- How well does this champion perform against the enemy picks?
- **Synergy Score** -- How well does this champion synergize with your teammates?

All components use Wilson Score to handle small sample sizes without arbitrary cutoffs.
See [`SCORE_CALCULATION.md`](counterpick-app/apps/backend/SCORE_CALCULATION.md) for the full mathematical breakdown.

---

## Log Files

Logs are stored at:

```
%APPDATA%\dev.till.lol-draft-analyzer\logs\
```

Two log files are maintained:

- **`backend.log`** -- Python sidecar (daily rotation, 14 days retained)
- **`tauri.log`** -- Rust host

Include both files when reporting bugs.

---

## Troubleshooting

**App shows a blank white screen**
The embedded WebView2 runtime may need updating. Download the latest WebView2 Runtime from Microsoft: <https://developer.microsoft.com/en-us/microsoft-edge/webview2/>

**"Backend stopped unexpectedly" error**
Check if your antivirus quarantined `backend.exe`. Add an exclusion for the install directory (see [Antivirus False Positives](#antivirus-false-positives) above).

**"Waiting for League of Legends..." stays on screen**
The LoL client must be running and you must be in champion select or lobby. The app detects the client automatically -- no manual configuration is needed. If the client is running but not detected, restart both the app and the LoL client.

---

## MSI vs Portable FAQ

**Q: What is the difference between MSI and Portable?**

A: Both install the same application. The MSI uses Windows Installer, which provides cleaner uninstall via Add/Remove Programs. The Portable option uses NSIS (a self-extracting setup wizard). Both install per-user without admin rights. Choose MSI unless your organization blocks `.msi` files.

**Q: Do I need admin rights?**

A: No. Both installers install to a per-user directory and do not require elevated privileges.

**Q: How do I uninstall?**

A: MSI: use Add/Remove Programs in Windows Settings. NSIS: use the uninstaller in the Start Menu folder or Add/Remove Programs.

---

## Project Structure

```
.
├── counterpick-app/              # Main application (pnpm monorepo)
│   ├── apps/
│   │   ├── backend/              # Python Flask API + recommendation engine
│   │   └── frontend/             # Vue 3 draft tracker UI
│   ├── src-tauri/                # Tauri desktop host (Rust)
│   └── packages/
│       └── core/                 # Shared TypeScript types
├── supabase-dataset-updater/     # ETL pipeline (runs daily via GitHub Actions)
└── docs/                         # Operator documentation
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop Host | Tauri (Rust), WebView2 |
| Frontend | Vue 3, TypeScript, Vite, Pinia |
| Backend | Python, Flask, Flask-SocketIO |
| Data Source | Lolalytics (champion stats & matchups) via CDN |
| Data Pipeline | Supabase (PostgreSQL) + GitHub Pages CDN |
| Build | pnpm, Turbo, PyInstaller |
| CI/CD | GitHub Actions |

---

## Development Setup

### Prerequisites

- Node.js >= 18 and [pnpm](https://pnpm.io/) 9.2.0+
- Python 3.10+
- Rust (stable toolchain)
- [Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon) assets (see below)

### 1. Clone and install

```bash
git clone <your-repo-url>
cd counterpick-app
pnpm install
```

### 2. Configure environment variables

```bash
# Backend (only needed for local Supabase development)
cp apps/backend/.env.example apps/backend/.env
# Fill in your Supabase credentials
```

### 3. Download game assets

The `dragontail-*/` folder is not included in the repo (2.6 GB). Download from Riot:

```
https://developer.riotgames.com/docs/lol#data-dragon
```

Extract into the project root so the path looks like `dragontail-15.xx.x/`.

### 4. Start in development mode

```bash
# From counterpick-app/ — launches Tauri with Vite HMR + native Python backend
pnpm tauri dev
```

Or run backend and frontend separately:

```bash
# Backend
cd apps/backend
pip install -r requirements.txt
pip install -e .
python backend.py
# Runs at http://localhost:5000

# Frontend (from counterpick-app/)
pnpm dev
# Runs at http://localhost:5173
```

---

## Dataset Updater

The `supabase-dataset-updater/` pipeline fetches champion stats from Lolalytics and writes them to Supabase. It runs automatically every day via GitHub Actions. The data is then exported to JSON and published to GitHub Pages CDN for client consumption.

See [`docs/DATA-PIPELINE.md`](docs/DATA-PIPELINE.md) for the full operator runbook.

---

## Acknowledgements

Inspired by [draftgap](https://github.com/vigovlugt/draftgap) by vigovlugt. The frontend design concept and draft-tracking idea drew from that project -- the recommendation engine, scoring algorithm, and backend are written from scratch.

Champion data provided by [Lolalytics](https://lolalytics.com) and [Riot Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon).

---

## License

Private use only. Not affiliated with Riot Games.
