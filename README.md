# LoL Draft Analyzer

A real-time League of Legends draft assistant that recommends champions during champion select based on your team composition, enemy picks, and current meta data.

Built with a custom scoring algorithm that combines base champion strength, counter matchups, and team synergy — weighted and normalized using [Wilson Score confidence intervals](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval).

---

## Features

- **Real-time draft tracking** via League Client integration (WebSocket)
- **Champion recommendations** scored by base strength + counter matchups + team synergy
- **Role-aware importance matrices** (e.g. top-vs-top is weighted higher than top-vs-bot)
- **Blind pick mode** when no enemy picks are available yet
- **Hover detection** — reduces weight of uncertain enemy/ally picks
- **Vue 3 frontend** with live updates
- **Automated data pipeline** updating champion stats daily via GitHub Actions

---

## How the Score Works

Each recommended champion gets a **Final Score (0–100)**:

```
Final Score = (Base Score × 30%) + (Counter Score × 45%) + (Synergy Score × 25%)
```

- **Base Score** — How strong is this champion in the current meta (win rate + pick rate)?
- **Counter Score** — How well does this champion perform against the enemy picks?
- **Synergy Score** — How well does this champion synergize with your teammates?

All components use Wilson Score to handle small sample sizes without arbitrary cutoffs.
See [`SCORE_CALCULATION.md`](counterpick-app/apps/backend/SCORE_CALCULATION.md) for the full mathematical breakdown.

---

## Project Structure

```
.
├── counterpick-app/              # Main application (pnpm monorepo)
│   ├── apps/
│   │   ├── backend/              # Python Flask API + recommendation engine
│   │   └── frontend/             # Vue 3 draft tracker UI
│   └── packages/
│       └── core/                 # Shared TypeScript types
├── supabase-dataset-updater/     # ETL pipeline (runs daily via GitHub Actions)
└── dragontail-*/                 # Game assets — download separately (see below)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3, TypeScript, Vite, Pinia |
| Backend | Python, Flask, Flask-SocketIO |
| Database | Supabase (PostgreSQL) |
| Data source | Lolalytics (champion stats & matchups) |
| Build | pnpm, Turbo |
| CI/CD | GitHub Actions |

---

## Setup

### Prerequisites

- Node.js >= 18 and [pnpm](https://pnpm.io/)
- Python 3.11+
- A [Supabase](https://supabase.com) project
- [Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon) assets (see below)

### 1. Clone and install

```bash
git clone <your-repo-url>
cd counterpick-app
pnpm install
```

### 2. Configure environment variables

```bash
# Backend
cp apps/backend/.env.example apps/backend/.env
# Fill in your Supabase credentials
```

```bash
# Dataset updater (optional, for running the ETL locally)
cp ../supabase-dataset-updater/.env.example ../supabase-dataset-updater/.env
```

### 3. Download game assets

The `dragontail-*/` folder is not included in the repo (2.6 GB). Download from Riot:

```
https://developer.riotgames.com/docs/lol#data-dragon
```

Extract into the project root so the path looks like `dragontail-15.xx.x/`.

### 4. Start the backend

```bash
cd apps/backend
pip install -r requirements.txt
pip install -e .
python backend.py
```

Backend runs at `http://localhost:5000`.

### 5. Start the frontend

```bash
# From counterpick-app/
pnpm dev
```

Frontend runs at `http://localhost:5173`.

---

## Dataset Updater

The `supabase-dataset-updater/` pipeline fetches champion stats from Lolalytics and writes them to Supabase. It runs automatically every day via GitHub Actions.

To run locally:

```bash
cd supabase-dataset-updater
pnpm install
pnpm update
```

For GitHub Actions, set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as repository secrets under **Settings > Secrets and variables > Actions**.

---

## Acknowledgements

Inspired by [draftgap](https://github.com/vigovlugt/draftgap) by vigovlugt. The frontend design concept and draft-tracking idea drew from that project — the recommendation engine, scoring algorithm, and backend are written from scratch.

Champion data provided by [Lolalytics](https://lolalytics.com) and [Riot Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon).

---

## License

Private use only. Not affiliated with Riot Games.
