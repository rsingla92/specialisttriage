"""Tests for the OceanMD service layer."""
import requests as requests_lib
from unittest.mock import patch, MagicMock
from app.services.ocean_md import OceanMDService


class TestOceanMDServiceMock:
    """Tests using mock mode (no API key)."""

    def setup_method(self):
        self.service = OceanMDService(
            base_url="https://ocean.cognisantmd.com/api",
            api_key="",  # empty key → mock mode
        )

    def test_mock_mode_when_no_key(self):
        assert self.service._use_mock is True

    def test_fetch_pending_returns_list(self):
        referrals = self.service.fetch_pending_referrals()
        assert isinstance(referrals, list)
        assert len(referrals) > 0

    def test_mock_referral_has_required_fields(self):
        referrals = self.service.fetch_pending_referrals()
        required = [
            "ocean_referral_id",
            "patient_first_name",
            "patient_last_name",
            "patient_dob",
            "chief_complaint",
            "referring_physician_name",
            "specialty_requested",
        ]
        for ref in referrals:
            for field in required:
                assert field in ref, f"Missing field: {field}"

    def test_send_feedback_mock_returns_true(self):
        result = self.service.send_feedback("OCN-2026-001", "Thank you.", "accepted")
        assert result is True

    def test_mock_referrals_all_urology(self):
        referrals = self.service.fetch_pending_referrals()
        for ref in referrals:
            assert ref["specialty_requested"] == "Urology"

    def test_mock_includes_urgent_case(self):
        referrals = self.service.fetch_pending_referrals()
        complaints = [r["chief_complaint"].lower() for r in referrals]
        assert any("hematuria" in c for c in complaints)


class TestOceanMDServiceLive:
    """Tests for live API behaviour (uses mocked requests)."""

    def setup_method(self):
        self.service = OceanMDService(
            base_url="https://ocean.cognisantmd.com/api",
            api_key="test-api-key-123",
        )

    def test_live_mode_when_key_set(self):
        assert self.service._use_mock is False

    def test_fetch_pending_handles_api_error(self):
        with patch("app.services.ocean_md.requests.get") as mock_get:
            mock_get.side_effect = requests_lib.RequestException("Network error")
            result = self.service.fetch_pending_referrals()
            assert result == []

    def test_fetch_pending_parses_response(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "referrals": [
                {
                    "id": "OCN-TEST-001",
                    "patientFirstName": "John",
                    "patientLastName": "Doe",
                    "patientDateOfBirth": "1965-03-15",
                    "patientPhn": "1234567890",
                    "referringPhysicianName": "Dr. Smith",
                    "referringClinic": "Test Clinic",
                    "referringPhysicianPhone": "604-555-0000",
                    "referringPhysicianFax": "604-555-0001",
                    "chiefComplaint": "Hematuria",
                    "clinicalNotes": "Notes here",
                    "relevantHistory": "None",
                    "medications": "None",
                    "allergies": "NKDA",
                    "investigations": "Urinalysis",
                    "specialtyRequested": "Urology",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.ocean_md.requests.get", return_value=mock_response):
            result = self.service.fetch_pending_referrals()

        assert len(result) == 1
        assert result[0]["ocean_referral_id"] == "OCN-TEST-001"
        assert result[0]["patient_first_name"] == "John"
        assert result[0]["chief_complaint"] == "Hematuria"

    def test_send_feedback_success(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.ocean_md.requests.post", return_value=mock_response):
            result = self.service.send_feedback("OCN-001", "Message", "accepted")

        assert result is True

    def test_send_feedback_includes_workup_and_redirect(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.ocean_md.requests.post", return_value=mock_response) as mock_post:
            self.service.send_feedback(
                "OCN-001",
                "Please arrange the following before appointment.",
                "needs_info",
                recommended_workup="Urinalysis, urine culture, renal ultrasound",
                redirect_to=None,
            )

        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["recommendedWorkup"] == "Urinalysis, urine culture, renal ultrasound"
        assert "redirectTo" not in payload

    def test_send_feedback_failure(self):
        with patch("app.services.ocean_md.requests.post") as mock_post:
            mock_post.side_effect = requests_lib.RequestException("Connection refused")
            result = self.service.send_feedback("OCN-001", "Message", "accepted")

        assert result is False
