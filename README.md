# SpecialistTriage BC

> **Reducing inappropriate specialist referrals in British Columbia.**

A SaaS triage tool that sits between EMRs and specialists, using OceanMD's API to bulk-process and triage inbound referrals. Designed initially for BC urologists who each receive 70–100 referrals/week with an estimated 30–40% inappropriate rate.

## Problem

- Specialists receive high volumes of incomplete or poorly worked-up referrals
- No systematic triage or feedback to referring physicians
- Result: longer patient wait times, specialist burnout, and frustrated family doctors

## Solution

SpecialistTriage BC integrates with [OceanMD](https://ocean.cognisantmd.com/) (BC's primary e-referral platform) to:

1. **Bulk-import** pending referrals from OceanMD
2. **Auto-triage** each referral using BC/GPAC guideline-informed rules:
   - Appropriateness score (0–100)
   - Completeness score (0–100) – flags missing investigations or clinical history
   - Urgency score (0–100) – detects red-flag symptoms
   - Priority classification: `urgent` | `high` | `routine` | `low` | `needs_info` | `inappropriate`
3. **Present** a prioritised dashboard to the specialist
4. **Send structured feedback** to the referring physician via OceanMD (decision: accepted / declined / needs info / redirect)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Flask 3.x |
| Database | SQLite (dev) / PostgreSQL-compatible via SQLAlchemy |
| Auth | Flask-Login (session-based) |
| Migrations | Flask-Migrate / Alembic |
| Frontend | Bootstrap 5, Vanilla JS |
| External API | OceanMD REST API (mock included for dev/test) |

## Quick Start

```bash
# 1. Clone and install
git clone <repo>
cd specialisttriage
pip install -r requirements.txt

# 2. Set up the database
flask --app run.py db upgrade

# 3. Create a demo specialist account
flask --app run.py seed-demo

# 4. Run the development server
python run.py
```

Then open http://127.0.0.1:5000 and log in with `demo@example.com` / `password123`.

Click **Import from OceanMD** to load 5 sample BC urology referrals (mock data) and see the auto-triage in action.

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask secret key (required in production) |
| `DATABASE_URL` | SQLAlchemy DB URL (default: SQLite) |
| `OCEAN_MD_API_KEY` | OceanMD API key (empty = mock mode) |
| `OCEAN_MD_BASE_URL` | OceanMD API base URL |

## Running Tests

```bash
python -m pytest -v
```

53 tests cover:
- Triage engine (urgency, completeness, appropriateness, priority classification)
- OceanMD service (mock mode, live API error handling, response parsing)
- Flask routes (auth, dashboard, referral import/detail/retriage, feedback, REST API)

## Project Structure

```
app/
├── models.py              # SQLAlchemy models (User, Referral, TriageResult, Feedback)
├── routes/
│   ├── auth.py            # Login / logout / register
│   ├── dashboard.py       # Main referral dashboard
│   ├── referrals.py       # Import, detail, retriage, feedback
│   └── api.py             # JSON REST API
├── services/
│   ├── triage_engine.py   # Rule-based triage scoring (GPAC-informed)
│   └── ocean_md.py        # OceanMD API client + mock data
├── templates/             # Jinja2 / Bootstrap 5 HTML
└── static/                # CSS + JS
tests/
├── test_triage_engine.py  # Triage engine unit tests
├── test_ocean_md.py       # OceanMD service tests
└── test_routes.py         # Flask integration tests
```

## Roadmap

- [ ] Machine-learning triage model trained on historical referral outcomes
- [ ] Multi-specialty support beyond Urology
- [ ] Two-way OceanMD integration (real-time webhooks)
- [ ] Referring physician portal (view feedback history, compliance metrics)
- [ ] Analytics dashboard (inappropriate referral rate trends, wait-time impact)
- [ ] EMR-agnostic FHIR adapter

## License

See [LICENSE](LICENSE).
