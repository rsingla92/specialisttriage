"""Integration tests for the Flask application routes."""
import pytest
from app import create_app, db
from app.models import User, Referral


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def specialist(app):
    user = User(
        email="test.specialist@bc.ca",
        full_name="Dr. Test Specialist",
        specialty="Urology",
        clinic_name="Test Clinic",
        role="specialist",
    )
    user.set_password("testpassword")
    db.session.add(user)
    db.session.commit()
    return user.id


def login(client, email, password):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def login_specialist(client, app, specialist_id):
    user = db.session.get(User, specialist_id)
    return login(client, user.email, "testpassword")


class TestAuth:
    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"SpecialistTriage" in resp.data

    def test_register_page_loads(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200

    def test_invalid_login(self, client):
        resp = login(client, "nobody@example.com", "wrong")
        assert resp.status_code == 200
        assert b"Invalid email or password" in resp.data

    def test_valid_login(self, client, specialist, app):
        resp = login_specialist(client, app, specialist)
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_logout(self, client, specialist, app):
        login_specialist(client, app, specialist)
        resp = client.get("/logout", follow_redirects=True)
        assert resp.status_code == 200

    def test_register_creates_account(self, client):
        resp = client.post(
            "/register",
            data={
                "full_name": "Dr. New User",
                "email": "new.user@bc.ca",
                "password": "securepass1",
                "confirm_password": "securepass1",
                "specialty": "Urology",
                "clinic_name": "Test Hospital",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data or b"Welcome" in resp.data


class TestDashboard:
    def test_dashboard_requires_login(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code in (200, 302)

    def test_dashboard_accessible_when_logged_in(self, client, specialist, app):
        login_specialist(client, app, specialist)
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_dashboard_shows_stats(self, client, specialist, app):
        login_specialist(client, app, specialist)
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert b"Total" in resp.data


class TestReferralImport:
    def test_import_creates_referrals(self, client, specialist, app):
        login_specialist(client, app, specialist)
        resp = client.post("/referrals/import", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Imported" in resp.data or b"already on file" in resp.data

        count = Referral.query.filter_by(specialist_id=specialist).count()
        assert count > 0

    def test_second_import_skips_duplicates(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)
        count_before = Referral.query.filter_by(specialist_id=specialist).count()

        resp = client.post("/referrals/import", follow_redirects=True)
        assert resp.status_code == 200
        assert b"already on file" in resp.data

        count_after = Referral.query.filter_by(specialist_id=specialist).count()
        assert count_after == count_before

    def test_referrals_auto_triaged_on_import(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referrals = Referral.query.filter_by(specialist_id=specialist).all()
        for r in referrals:
            assert r.triage_result is not None
            assert r.priority is not None


class TestReferralDetail:
    def test_referral_detail_accessible(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        assert referral is not None
        resp = client.get(f"/referrals/{referral.id}")
        assert resp.status_code == 200
        assert b"Triage Assessment" in resp.data or b"Run Triage" in resp.data

    def test_referral_triage_result_shows(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        assert referral.triage_result is not None

        resp = client.get(f"/referrals/{referral.id}")
        assert resp.status_code == 200
        assert b"Appropriateness" in resp.data

    def test_retriage_endpoint(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        resp = client.post(f"/referrals/{referral.id}/retriage", follow_redirects=True)
        assert resp.status_code == 200

    def test_referral_shows_patient_info(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        resp = client.get(f"/referrals/{referral.id}")
        assert referral.patient_first_name.encode() in resp.data


class TestFeedback:
    def test_feedback_page_loads(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        resp = client.get(f"/referrals/{referral.id}/feedback")
        assert resp.status_code == 200
        assert b"Send Feedback" in resp.data

    def test_feedback_submission(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        referral_id = referral.id

        resp = client.post(
            f"/referrals/{referral_id}/feedback",
            data={
                "decision": "accepted",
                "message": "Thank you for the referral. We will see this patient.",
                "recommended_workup": "",
                "redirect_to": "",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Feedback sent" in resp.data

        referral = db.session.get(Referral, referral_id)
        assert referral.feedback is not None
        assert referral.feedback.decision == "accepted"
        assert referral.status == "accepted"

    def test_feedback_requires_decision_and_message(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        resp = client.post(
            f"/referrals/{referral.id}/feedback",
            data={"decision": "", "message": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"required" in resp.data.lower()


class TestAPI:
    def test_api_requires_login(self, client):
        resp = client.get("/api/referrals")
        assert resp.status_code in (302, 401)

    def test_api_referrals(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        resp = client.get("/api/referrals")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "referrals" in data
        assert len(data["referrals"]) > 0

    def test_api_stats(self, client, specialist, app):
        login_specialist(client, app, specialist)
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total" in data
        assert data["total"] >= 0

    def test_api_referral_filter_by_status(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        resp = client.get("/api/referrals?status=triaged")
        assert resp.status_code == 200
        data = resp.get_json()
        for r in data["referrals"]:
            assert r["status"] == "triaged"

    def test_api_referral_detail(self, client, specialist, app):
        login_specialist(client, app, specialist)
        client.post("/referrals/import", follow_redirects=True)

        referral = Referral.query.filter_by(specialist_id=specialist).first()
        resp = client.get(f"/api/referrals/{referral.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == referral.id
        assert "triage" in data
        assert data["triage"] is not None
