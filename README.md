# ReferralQ

> **Specialist referral triage for Canadian physicians.** A WhiteCoat Prep product.

Multi-specialty referral triage SaaS that helps specialist clinics process referrals faster and gives family physicians pre-referral pathway guidance. Built for the Canadian healthcare system, starting with BC.

## What It Does

- **Efficiency Dashboard** — Category-grouped referrals with batch actions, completeness tracking, and quick review panel
- **Pre-Referral Pathways** — Public, condition-specific workup checklists for family physicians (no login required)
- **Multi-Specialty Support** — Urology, Gastroenterology, and Orthopedics with DB-backed clinical rules
- **Analytics** — Referral volume trends, completeness scores, turnaround time, outcome rates
- **Clinic Management** — Multi-user clinics with shared referral queues, team management, and role-based access
- **LLM Classification** — Claude Haiku fallback for referrals that don't match keyword rules
- **Editable Rules** — Specialists customize workup requirements, classification keywords, and pathway guidance

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, Flask 3.1 |
| Database | SQLite (dev) / PostgreSQL-compatible via SQLAlchemy |
| Auth | Flask-Login (session-based) |
| Migrations | Flask-Migrate / Alembic |
| Frontend | Bootstrap 5, Chart.js, Vanilla JS |
| Design System | Plus Jakarta Sans, #1B6B93 teal (see DESIGN.md) |
| External API | OceanMD REST API (mock included for dev/test) |
| LLM | Anthropic Claude Haiku (optional, for classification fallback) |

## Quick Start

```bash
# 1. Clone and install
git clone <repo>
cd specialisttriage
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Set up the database
flask --app run.py db upgrade

# 3. Seed data
flask --app run.py seed-specialty    # 3 specialties with clinical rules
flask --app run.py seed-demo         # Demo clinic + specialist account
flask --app run.py seed-templates    # Response templates

# 4. Run the development server
python run.py
```

Then open http://127.0.0.1:5000 and log in with the credentials shown by `seed-demo`.

## Project Structure

```
app/
├── models.py              # SQLAlchemy models (User, Referral, Clinic, Specialty, etc.)
├── routes/
│   ├── auth.py            # Login / logout / register / signup / onboarding / invite
│   ├── dashboard.py       # Main referral dashboard (dual-queue)
│   ├── referrals.py       # Import, detail, retriage, feedback, batch, claim, panel
│   ├── pathways.py        # Public FP pre-referral pathway pages
│   ├── analytics.py       # Analytics API + dashboard
│   ├── admin.py           # Clinical rules management
│   ├── clinic.py          # Clinic team + settings management
│   ├── templates.py       # Response template CRUD
│   └── api.py             # JSON REST API
├── services/
│   ├── triage_engine.py   # Rule-based triage scoring (DB-backed + hardcoded fallback)
│   ├── llm_classifier.py  # Claude Haiku classification fallback
│   ├── ocean_md.py        # OceanMD API client + mock data
│   └── specialty_seeder.py # Seed specialties from guidelines
├── templates/             # Jinja2 / Bootstrap 5 HTML
└── static/                # CSS (design system) + JS
tests/
├── test_triage_engine.py  # 45 tests: classification, workup, scoring, LLM, ruleset
├── test_ocean_md.py       # 12 tests: mock mode, live API parsing
├── test_routes.py         # 68 tests: auth, dashboard, batch, clinic, analytics, pathways
└── test_fixes.py          # 21 tests: regression tests for QA-discovered bugs
```

## Running Tests

```bash
python -m pytest -v
```

146 tests covering triage engine, OceanMD service, all routes, clinic management, analytics, LLM classification, and QA regression tests.

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask secret key (required in production) |
| `DATABASE_URL` | SQLAlchemy DB URL (default: SQLite) |
| `OCEAN_MD_API_KEY` | OceanMD API key (empty = mock mode) |
| `OCEAN_MD_BASE_URL` | OceanMD API base URL |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional, for LLM classification fallback) |

## License

See [LICENSE](LICENSE).
