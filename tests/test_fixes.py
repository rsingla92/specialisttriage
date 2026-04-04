"""
Tests validating the bug fixes and improvements made in this PR:

  1. SQLAlchemy Query.get() deprecation – replaced with db.session.get()
  2. Unused variable in analytics.volume() – removed dead query assignment
  3. Batch operation authorisation – clinic-pool referrals now accessible in batch
  4. ED-referral skip removed from batch – consistent with single-referral behaviour
  5. Input validation for keywords / workup labels in admin routes
  6. /api/health endpoint – returns 200 when DB is reachable
  7. DB connection-pooling config – TestingConfig overrides with empty dict
"""
import json
from datetime import date

import pytest

from app import create_app, db
from app.models import (
    Clinic,
    ClinicMembership,
    Referral,
    ResponseTemplate,
    User,
    Feedback,
)


# ---------------------------------------------------------------------------
# Fixtures (mirror those in test_routes.py so this file is self-contained)
# ---------------------------------------------------------------------------

@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def specialist(app):
    user = User(
        email="fix.specialist@bc.ca",
        full_name="Dr. Fix Specialist",
        specialty="Urology",
        clinic_name="Fix Clinic",
        role="specialist",
    )
    user.set_password("TestPass1!")
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, email, password="TestPass1!"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def _login_specialist(client, app, specialist_id):
    user = db.session.get(User, specialist_id)
    return _login(client, user.email)


def _import_referrals(client):
    return client.post("/referrals/import", follow_redirects=True)


def _get_csrf(client, url="/dashboard"):
    import re
    resp = client.get(url)
    data = resp.data.decode()
    match = re.search(r'name="csrf-token"\s+content="([^"]+)"', data)
    if match:
        return match.group(1)
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', data)
    return match.group(1) if match else ""


def _create_clinic_for(user_id, role="owner"):
    clinic = Clinic(
        name="Pool Clinic",
        slug="pool-clinic",
        settings={"queue_mode": "hybrid", "auto_triage": True},
    )
    db.session.add(clinic)
    db.session.flush()
    db.session.add(ClinicMembership(user_id=user_id, clinic_id=clinic.id, role=role))
    db.session.commit()
    return clinic


def _make_referral(clinic_id=None, specialist_id=None, category="hematuria"):
    """Create a minimal Referral and return it."""
    ref = Referral(
        patient_first_name="Pool",
        patient_last_name="Patient",
        patient_dob=date(1990, 1, 1),
        referring_physician_name="Dr Z",
        chief_complaint="Blood in urine",
        clinic_id=clinic_id,
        specialist_id=specialist_id,
        clinical_category=category,
    )
    db.session.add(ref)
    db.session.commit()
    return ref


# ---------------------------------------------------------------------------
# 1. SQLAlchemy Session.get() – no LegacyAPIWarnings
# ---------------------------------------------------------------------------

class TestSessionGet:
    """db.session.get() is used instead of Model.query.get()."""

    def test_referral_routes_use_session_get_without_warnings(self, client, specialist, app, recwarn):
        """Navigating authenticated routes must not raise LegacyAPIWarnings."""
        _login_specialist(client, app, specialist)
        _import_referrals(client)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        client.get(f"/referrals/{referral.id}")
        client.get(f"/referrals/{referral.id}/panel")

        legacy_warnings = [
            w for w in recwarn.list
            if getattr(w.category, "__name__", "") == "LegacyAPIWarning"
            or "Query.get" in str(w.message)
        ]
        assert legacy_warnings == [], (
            f"Unexpected LegacyAPIWarnings: {legacy_warnings}"
        )


# ---------------------------------------------------------------------------
# 2. Analytics volume – unused variable removed
# ---------------------------------------------------------------------------

class TestAnalyticsVolumeNoDeadCode:
    """The volume() endpoint must return correct data without dead query."""

    def test_volume_returns_data(self, client, specialist, app):
        _login_specialist(client, app, specialist)
        _import_referrals(client)

        resp = client.get("/api/analytics/volume?days=30")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        # Each row must contain 'date' and 'count'
        for row in data["data"]:
            assert "date" in row
            assert "count" in row

    def test_volume_zero_days_returns_all(self, client, specialist, app):
        """days=0 means no date cutoff – all referrals are included."""
        _login_specialist(client, app, specialist)
        _import_referrals(client)

        resp = client.get("/api/analytics/volume?days=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data


# ---------------------------------------------------------------------------
# 3. Batch authorisation – clinic-pool referrals are accessible
# ---------------------------------------------------------------------------

class TestBatchClinicPoolAccess:
    """Batch action can process clinic-pool referrals (no specialist_id set)."""

    def test_batch_accepts_clinic_pool_referral(self, client, specialist, app):
        _login_specialist(client, app, specialist)
        clinic = _create_clinic_for(specialist)
        ref = _make_referral(clinic_id=clinic.id, specialist_id=None)

        resp = client.post(
            "/referrals/batch",
            data=json.dumps({"referral_ids": [ref.id], "action_type": "accepted"}),
            content_type="application/json",
            headers={"X-CSRFToken": _get_csrf(client)},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # The pool referral must NOT be rejected as "not_owned"
        assert all(r["status"] != "rejected" for r in data["results"]), (
            "Clinic-pool referral was incorrectly rejected in batch"
        )

    def test_batch_rejects_referral_from_other_clinic(self, client, specialist, app):
        """Referrals from a clinic the user is NOT a member of must be rejected."""
        _login_specialist(client, app, specialist)

        # Create a second clinic that the specialist is NOT a member of
        other_clinic = Clinic(
            name="Other Clinic",
            slug="other-clinic",
            settings={"queue_mode": "individual", "auto_triage": True},
        )
        db.session.add(other_clinic)
        db.session.commit()
        ref = _make_referral(clinic_id=other_clinic.id, specialist_id=None)

        resp = client.post(
            "/referrals/batch",
            data=json.dumps({"referral_ids": [ref.id], "action_type": "accepted"}),
            content_type="application/json",
            headers={"X-CSRFToken": _get_csrf(client)},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(r["status"] == "rejected" for r in data["results"]), (
            "Referral from a foreign clinic should be rejected"
        )

    def test_admin_can_batch_any_referral(self, client, app):
        """A system admin can batch-process any referral."""
        admin = User(
            email="admin.batch@bc.ca",
            full_name="Admin User",
            specialty="Urology",
            clinic_name="Admin Clinic",
            role="admin",
        )
        admin.set_password("AdminPass1!")
        db.session.add(admin)
        db.session.commit()
        _login(client, admin.email, "AdminPass1!")

        # Referral belonging to a completely different specialist
        other = User(
            email="other.specialist@bc.ca",
            full_name="Other Doc",
            specialty="Urology",
            clinic_name="Other Clinic",
            role="specialist",
        )
        other.set_password("OtherPass1!")
        db.session.add(other)
        db.session.flush()
        ref = _make_referral(specialist_id=other.id)

        resp = client.post(
            "/referrals/batch",
            data=json.dumps({"referral_ids": [ref.id], "action_type": "accepted"}),
            content_type="application/json",
            headers={"X-CSRFToken": _get_csrf(client)},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(r["status"] != "rejected" for r in data["results"]), (
            "Admin should be able to process any referral in batch"
        )


# ---------------------------------------------------------------------------
# 4. ED referrals are no longer skipped in batch
# ---------------------------------------------------------------------------

class TestBatchEdReferral:
    """Erectile-dysfunction referrals must be processable via batch (consistent
    with individual send_feedback behaviour)."""

    def test_ed_referral_not_skipped_in_batch(self, client, specialist, app):
        _login_specialist(client, app, specialist)
        ref = _make_referral(specialist_id=specialist, category="erectile_dysfunction")

        resp = client.post(
            "/referrals/batch",
            data=json.dumps({"referral_ids": [ref.id], "action_type": "accepted"}),
            content_type="application/json",
            headers={"X-CSRFToken": _get_csrf(client)},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert not any(
            r.get("reason") == "ed_referral" for r in data["results"]
        ), "ED referral must not be silently skipped in batch"
        # The referral should be actioned (sent/saved), not skipped for this reason
        assert any(r["status"] in ("sent", "saved") for r in data["results"])

    def test_ed_referral_individual_feedback_still_works(self, client, specialist, app):
        """Confirm individual feedback endpoint also processes ED referrals."""
        _login_specialist(client, app, specialist)
        ref = _make_referral(specialist_id=specialist, category="erectile_dysfunction")

        resp = client.post(
            f"/referrals/{ref.id}/feedback",
            data={
                "decision": "accepted",
                "message": "Accepted ED referral.",
                "recommended_workup": "",
                "redirect_to": "",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Flash message varies by delivery mode; look for the common substring
        assert b"Feedback" in resp.data and (
            b"sent" in resp.data or b"saved" in resp.data
        )


# ---------------------------------------------------------------------------
# 5. Input validation – keywords and workup labels
# ---------------------------------------------------------------------------

class TestAdminInputValidation:
    """Admin routes must reject keywords/labels with disallowed characters."""

    def _seed_and_login(self, client, specialist, app):
        _login_specialist(client, app, specialist)
        from app.services.specialty_seeder import seed_all_specialties
        seed_all_specialties(db)

    def _get_admin_csrf(self, client):
        import re
        resp = client.get("/admin/")
        data = resp.data.decode()
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', data)
        return match.group(1) if match else ""

    def test_valid_keyword_is_accepted(self, client, specialist, app):
        self._seed_and_login(client, specialist, app)
        resp = client.post(
            "/admin/category/hematuria/keywords",
            data={
                "csrf_token": self._get_admin_csrf(client),
                "action": "add",
                "keyword": "visible hematuria",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"visible hematuria" in resp.data

    def test_keyword_with_script_tag_rejected(self, client, specialist, app):
        self._seed_and_login(client, specialist, app)
        resp = client.post(
            "/admin/category/hematuria/keywords",
            data={
                "csrf_token": self._get_admin_csrf(client),
                "action": "add",
                "keyword": "<script>alert(1)</script>",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Must display a danger flash message and NOT add the keyword
        assert b"only contain" in resp.data.lower() or b"letters" in resp.data.lower()
        assert b"<script>" not in resp.data

    def test_keyword_with_sql_injection_rejected(self, client, specialist, app):
        self._seed_and_login(client, specialist, app)
        resp = client.post(
            "/admin/category/hematuria/keywords",
            data={
                "csrf_token": self._get_admin_csrf(client),
                "action": "add",
                "keyword": "'; DROP TABLE keywords; --",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"only contain" in resp.data.lower() or b"letters" in resp.data.lower()

    def test_valid_workup_label_is_accepted(self, client, specialist, app):
        self._seed_and_login(client, specialist, app)
        resp = client.post(
            "/admin/category/hematuria/workup",
            data={
                "csrf_token": self._get_admin_csrf(client),
                "action": "add",
                "label": "Urine Culture",
                "keywords": "urine culture, culture",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Urine Culture" in resp.data

    def test_workup_label_with_html_rejected(self, client, specialist, app):
        self._seed_and_login(client, specialist, app)
        resp = client.post(
            "/admin/category/hematuria/workup",
            data={
                "csrf_token": self._get_admin_csrf(client),
                "action": "add",
                "label": "<b>Bad Label</b>",
                "keywords": "",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"only contain" in resp.data.lower() or b"letters" in resp.data.lower()
        assert b"<b>" not in resp.data

    def test_workup_detection_keywords_with_script_tag_rejected(self, client, specialist, app):
        """Detection keywords (comma-separated) must also pass _LABEL_RE validation."""
        self._seed_and_login(client, specialist, app)
        resp = client.post(
            "/admin/category/hematuria/workup",
            data={
                "csrf_token": self._get_admin_csrf(client),
                "action": "add",
                "label": "Valid Label",
                "keywords": "normal keyword, <script>xss</script>",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"only contain" in resp.data.lower() or b"letters" in resp.data.lower()
        # The workup item must NOT have been persisted
        assert b"Valid Label" not in resp.data or b"Added workup item" not in resp.data

    def test_keyword_regex_rejects_tab_and_newline(self, client, specialist, app):
        """Control characters (tab, newline) must be rejected by _LABEL_RE."""
        self._seed_and_login(client, specialist, app)
        for bad_keyword in ["tab\there", "new\nline"]:
            resp = client.post(
                "/admin/category/hematuria/keywords",
                data={
                    "csrf_token": self._get_admin_csrf(client),
                    "action": "add",
                    "keyword": bad_keyword,
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b"only contain" in resp.data.lower() or b"letters" in resp.data.lower(), (
                f"Expected validation error for keyword {bad_keyword!r}"
            )


# ---------------------------------------------------------------------------
# 6. Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client, app):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, client, app):
        resp = client.get("/api/health")
        data = resp.get_json()
        assert data is not None
        assert "status" in data
        assert "db" in data

    def test_health_db_ok(self, client, app):
        resp = client.get("/api/health")
        data = resp.get_json()
        assert data["db"] is True
        assert data["status"] == "ok"

    def test_health_no_auth_required(self, client, app):
        """Health endpoint must be accessible without authentication."""
        resp = client.get("/api/health")
        # Must NOT redirect to login
        assert resp.status_code != 302


# ---------------------------------------------------------------------------
# 7. Connection-pooling config – TestingConfig overrides correctly
# ---------------------------------------------------------------------------

class TestConnectionPoolingConfig:
    def test_testing_config_has_empty_engine_options(self, app):
        """TestingConfig must override engine options so SQLite in-memory works."""
        assert app.config.get("SQLALCHEMY_ENGINE_OPTIONS") == {}

    def test_base_config_has_pool_settings(self):
        """Base Config must define pool_size, pool_recycle, and pool_pre_ping."""
        from config import Config
        opts = Config.SQLALCHEMY_ENGINE_OPTIONS
        assert "pool_size" in opts
        assert "pool_recycle" in opts
        assert "pool_pre_ping" in opts
        assert opts["pool_size"] > 0
        assert opts["pool_pre_ping"] is True
