# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-07-03

Exploratory prototype stage. Not deployed, not used by a real clinic.

### Added
- Rule-based triage engine scoring appropriateness, completeness, and urgency for incoming referrals, with keyword weights for Urology grounded in BC's [GPAC](https://www2.gov.bc.ca/gov/content/health/practitioner-professional-resources/bc-guidelines) guidelines.
- Draft rule sets for Gastroenterology and Orthopedics, seeded from general Canadian guidelines but not yet clinically reviewed to the same depth as Urology.
- Claude Haiku fallback classifier for referrals that don't match keyword rules.
- Mock OceanMD e-referral client for local development; live API integration code exists but is untested against the real OceanMD service.
- Specialist dashboard: category-grouped queue, inline quick review, batch actions, completeness tracking.
- Public, no-login pre-referral pathway pages for family physicians.
- Analytics dashboard: referral volume, completeness, turnaround time, outcome rates.
- Multi-user clinic management with role-based access.
- Editable clinical rules UI (keywords, workup requirements, pathway guidance).
- 146 tests covering the triage engine, OceanMD service, all routes, and QA regression cases. Clean `mypy` and `ruff` runs.

### Known limitations
- No CI pipeline; tests/lint/typecheck are run locally only.
- No real-world usage; all data is seeded/synthetic.
- LLM classification fallback has no accuracy evaluation harness.
- PostgreSQL compatibility (via SQLAlchemy) is unverified; only run against SQLite so far.
