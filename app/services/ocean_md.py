"""
OceanMD API integration service.

OceanMD (ocean.cognisantmd.com) is BC's primary e-referral platform, used by
thousands of physicians across the province.  This module wraps the relevant
OceanMD API calls and provides a lightweight mock for local development / testing
when OCEAN_MD_API_KEY is not set.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import requests
from flask import current_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock data – used when no real API key is configured
# ---------------------------------------------------------------------------

_MOCK_REFERRALS: list[dict[str, Any]] = [
    {
        "ocean_referral_id": "OCN-2026-001",
        "patient_first_name": "James",
        "patient_last_name": "MacDonald",
        "patient_dob": str(date.today() - timedelta(days=365 * 58)),
        "patient_phn": "9876543210",
        "referring_physician_name": "Dr. Sarah Lee",
        "referring_clinic": "North Shore Medical Clinic",
        "referring_physician_phone": "604-555-0101",
        "referring_physician_fax": "604-555-0102",
        "chief_complaint": "Gross hematuria x 3 weeks, no infection on urine culture",
        "clinical_notes": (
            "Patient presented with painless gross hematuria. CT urogram ordered, "
            "showed no stone. Urinalysis: 3+ blood, no nitrites."
        ),
        "relevant_history": "Hypertension, ex-smoker 20 pack-year history",
        "current_medications": "Ramipril 5mg daily, ASA 81mg daily",
        "allergies": "Penicillin",
        "relevant_investigations": (
            "Urinalysis: 3+ blood. CT urogram: no obstructing stone, no obvious mass. "
            "Urine culture: negative. Creatinine: 88 μmol/L."
        ),
        "specialty_requested": "Urology",
    },
    {
        "ocean_referral_id": "OCN-2026-002",
        "patient_first_name": "Patrick",
        "patient_last_name": "Nguyen",
        "patient_dob": str(date.today() - timedelta(days=365 * 72)),
        "patient_phn": "9876543211",
        "referring_physician_name": "Dr. Michael Chen",
        "referring_clinic": "Lonsdale Medical Group",
        "referring_physician_phone": "604-555-0201",
        "referring_physician_fax": "604-555-0202",
        "chief_complaint": "Rising PSA – 6.8 ng/mL up from 4.1 last year",
        "clinical_notes": (
            "72M with rising PSA over 2 years. DRE: mildly enlarged, no nodule. "
            "Patient concerned about prostate cancer."
        ),
        "relevant_history": "Type 2 diabetes, osteoarthritis",
        "current_medications": "Metformin 500mg BID, Naproxen PRN",
        "allergies": "NKDA",
        "relevant_investigations": "PSA 6.8 ng/mL (prev 4.1), DRE: no nodule, UA: clear",
        "specialty_requested": "Urology",
    },
    {
        "ocean_referral_id": "OCN-2026-003",
        "patient_first_name": "Robert",
        "patient_last_name": "Kowalski",
        "patient_dob": str(date.today() - timedelta(days=365 * 45)),
        "patient_phn": "9876543212",
        "referring_physician_name": "Dr. Priya Sharma",
        "referring_clinic": "Deep Cove Family Practice",
        "referring_physician_phone": "604-555-0301",
        "referring_physician_fax": "604-555-0302",
        "chief_complaint": "Lower back pain and fatigue",
        "clinical_notes": "Non-specific low back pain for 3 months. No urinary symptoms.",
        "relevant_history": "Sedentary lifestyle, overweight",
        "current_medications": "None",
        "allergies": "NKDA",
        "relevant_investigations": "",
        "specialty_requested": "Urology",
    },
    {
        "ocean_referral_id": "OCN-2026-004",
        "patient_first_name": "David",
        "patient_last_name": "Williams",
        "patient_dob": str(date.today() - timedelta(days=365 * 63)),
        "patient_phn": "9876543213",
        "referring_physician_name": "Dr. Amanda Foster",
        "referring_clinic": "Lynn Valley Medical",
        "referring_physician_phone": "604-555-0401",
        "referring_physician_fax": "604-555-0402",
        "chief_complaint": "Recurrent urinary tract infections – 4 episodes in 12 months",
        "clinical_notes": (
            "Male patient with 4 UTIs this year, each culture-positive E. coli. "
            "Last episode required IV antibiotics. Ultrasound kidney/bladder ordered – pending."
        ),
        "relevant_history": "BPH diagnosed 2 years ago, on tamsulosin",
        "current_medications": "Tamsulosin 0.4mg daily",
        "allergies": "Sulfa drugs",
        "relevant_investigations": "Urine cultures: E. coli x4, PSA 3.2, creatinine normal",
        "specialty_requested": "Urology",
    },
    {
        "ocean_referral_id": "OCN-2026-005",
        "patient_first_name": "Mei",
        "patient_last_name": "Zhang",
        "patient_dob": str(date.today() - timedelta(days=365 * 38)),
        "patient_phn": "9876543214",
        "referring_physician_name": "Dr. John Patel",
        "referring_clinic": "Capilano Medical Centre",
        "referring_physician_phone": "604-555-0501",
        "referring_physician_fax": "604-555-0502",
        "chief_complaint": "Stress urinary incontinence affecting quality of life",
        "clinical_notes": (
            "38F, 2 vaginal deliveries. Leaks with cough/sneeze/exercise. "
            "Has completed 3 months of pelvic floor physiotherapy with minimal improvement."
        ),
        "relevant_history": "G2P2, otherwise healthy",
        "current_medications": "Oral contraceptive pill",
        "allergies": "NKDA",
        "relevant_investigations": "Urinalysis: normal, voiding diary completed (avg 8x/day)",
        "specialty_requested": "Urology",
    },
    {
        "ocean_referral_id": "OCN-2026-006",
        "patient_first_name": "Tom",
        "patient_last_name": "Bradley",
        "patient_dob": str(date.today() - timedelta(days=365 * 52)),
        "patient_phn": "9876543215",
        "referring_physician_name": "Dr. Susan Kim",
        "referring_clinic": "Deep Cove Medical",
        "referring_physician_phone": "604-555-0601",
        "referring_physician_fax": "604-555-0602",
        "chief_complaint": "Left flank pain, CT shows 8mm ureteral stone",
        "clinical_notes": (
            "52M presenting with acute left flank pain radiating to groin. "
            "CT KUB confirms 8mm stone at left UVJ. Creatinine 92. Urinalysis shows blood."
        ),
        "relevant_history": "Previous kidney stone 5 years ago (passed spontaneously)",
        "current_medications": "Lisinopril 10mg",
        "allergies": "NKDA",
        "relevant_investigations": "CT KUB: 8mm stone L UVJ, creatinine 92, urinalysis 3+ blood",
        "specialty_requested": "Urology",
    },
    {
        "ocean_referral_id": "OCN-2026-007",
        "patient_first_name": "Alan",
        "patient_last_name": "Foster",
        "patient_dob": str(date.today() - timedelta(days=365 * 61)),
        "patient_phn": "9876543216",
        "referring_physician_name": "Dr. Mark Lee",
        "referring_clinic": "Lynn Valley Medical",
        "referring_physician_phone": "604-555-0701",
        "referring_physician_fax": "604-555-0702",
        "chief_complaint": "Erectile dysfunction for 2 years",
        "clinical_notes": (
            "61M with ED for 2 years. Has tried sildenafil 50mg with partial response. "
            "HTN and diabetes well controlled. No other urological symptoms."
        ),
        "relevant_history": "Type 2 DM, HTN, hyperlipidemia",
        "current_medications": "Metformin 1000mg BID, Amlodipine 5mg, Atorvastatin 20mg",
        "allergies": "NKDA",
        "relevant_investigations": "HbA1c 7.1, testosterone 12 nmol/L (normal)",
        "specialty_requested": "Urology",
    },
    {
        "ocean_referral_id": "OCN-2026-008",
        "patient_first_name": "Karen",
        "patient_last_name": "White",
        "patient_dob": str(date.today() - timedelta(days=365 * 44)),
        "patient_phn": "9876543217",
        "referring_physician_name": "Dr. Emily Chen",
        "referring_clinic": "North Van Walk-In",
        "referring_physician_phone": "604-555-0801",
        "referring_physician_fax": "604-555-0802",
        "chief_complaint": "Lower back pain and fatigue, requesting urology assessment",
        "clinical_notes": (
            "44F with chronic lower back pain and fatigue. No urinary symptoms. "
            "Requesting urology referral at patient's request."
        ),
        "relevant_history": "Fibromyalgia, depression",
        "current_medications": "Duloxetine 60mg, acetaminophen PRN",
        "allergies": "Codeine",
        "relevant_investigations": "",
        "specialty_requested": "Urology",
    },
]


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class OceanMDService:
    """Client for the OceanMD e-referral platform API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._use_mock = not bool(api_key)
        if self._use_mock:
            logger.info("OceanMD API key not set – running in mock mode")

    @classmethod
    def from_app(cls) -> "OceanMDService":
        return cls(
            base_url=current_app.config["OCEAN_MD_BASE_URL"],
            api_key=current_app.config.get("OCEAN_MD_API_KEY", ""),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def fetch_pending_referrals(self) -> list[dict[str, Any]]:
        """
        Fetch unprocessed inbound referrals from OceanMD.

        Returns a list of referral dictionaries normalised to the app schema.
        Falls back to mock data when no API key is configured.
        """
        if self._use_mock:
            # Return a fresh list with shallow-copied dicts so that callers
            # can safely mutate the result without affecting global mock data.
            return [referral.copy() for referral in _MOCK_REFERRALS]

        try:
            resp = requests.get(
                f"{self.base_url}/referrals",
                headers=self._headers(),
                params={"status": "pending"},
                timeout=10,
            )
            resp.raise_for_status()
            return [self._normalize(r) for r in resp.json().get("referrals", [])]
        except requests.RequestException as exc:
            logger.error("OceanMD API error: %s", exc)
            return []

    def send_feedback(
        self,
        ocean_referral_id: str,
        message: str,
        decision: str,
        recommended_workup: str | None = None,
        redirect_to: str | None = None,
    ) -> bool:
        """
        Send triage feedback to the referring physician via OceanMD.

        Returns True on success, False on failure.
        """
        if self._use_mock:
            logger.info(
                "Mock: sending feedback for referral %s – decision: %s",
                ocean_referral_id,
                decision,
            )
            return True

        payload: dict[str, Any] = {"decision": decision, "message": message}
        if recommended_workup:
            payload["recommendedWorkup"] = recommended_workup
        if redirect_to:
            payload["redirectTo"] = redirect_to

        try:
            resp = requests.post(
                f"{self.base_url}/referrals/{ocean_referral_id}/feedback",
                headers=self._headers(),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("OceanMD send_feedback error: %s", exc)
            return False

    @staticmethod
    def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
        """Map OceanMD API response fields to the internal schema."""
        return {
            "ocean_referral_id": raw.get("id"),
            "patient_first_name": raw.get("patientFirstName", ""),
            "patient_last_name": raw.get("patientLastName", ""),
            "patient_dob": raw.get("patientDateOfBirth", ""),
            "patient_phn": raw.get("patientPhn", ""),
            "referring_physician_name": raw.get("referringPhysicianName", ""),
            "referring_clinic": raw.get("referringClinic", ""),
            "referring_physician_phone": raw.get("referringPhysicianPhone", ""),
            "referring_physician_fax": raw.get("referringPhysicianFax", ""),
            "chief_complaint": raw.get("chiefComplaint", ""),
            "clinical_notes": raw.get("clinicalNotes", ""),
            "relevant_history": raw.get("relevantHistory", ""),
            "current_medications": raw.get("medications", ""),
            "allergies": raw.get("allergies", ""),
            "relevant_investigations": raw.get("investigations", ""),
            "specialty_requested": raw.get("specialtyRequested", "Urology"),
        }
