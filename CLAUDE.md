# ReferralQ

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Testing
- Run: `python -m pytest -v`
- Test directory: `tests/`
- Framework: pytest + pytest-flask
- Current count: 105 tests

## Development
- Python 3.11, Flask 3.1, SQLAlchemy 2.0
- DB: SQLite (dev), PostgreSQL-compatible via SQLAlchemy
- Frontend: Bootstrap 5.3, Vanilla JS, Chart.js (analytics)
- Start: `python run.py` (port 5000)
- Seed: `flask seed-demo && flask seed-templates && flask seed-specialty`
