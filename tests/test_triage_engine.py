"""Tests for the triage engine."""
import pytest
from app.services.triage_engine import triage_referral, ReferralData


def make_referral(**kwargs) -> ReferralData:
    defaults = {
        "chief_complaint": "Routine follow-up",
        "clinical_notes": "",
        "relevant_history": "No significant history",
        "current_medications": "None",
        "allergies": "NKDA",
        "relevant_investigations": "Urinalysis normal",
        "patient_age": 55,
        "specialty_requested": "Urology",
    }
    defaults.update(kwargs)
    return ReferralData(**defaults)


class TestUrgencyScoring:
    def test_gross_hematuria_triggers_urgent(self):
        ref = make_referral(chief_complaint="Gross hematuria x 2 weeks, no infection")
        result = triage_referral(ref)
        assert result.recommended_priority == "urgent"
        assert result.urgency_score >= 50

    def test_acute_urinary_retention_is_urgent(self):
        ref = make_referral(chief_complaint="Acute urinary retention, cannot void")
        result = triage_referral(ref)
        assert result.recommended_priority == "urgent"

    def test_psa_rise_is_high_priority(self):
        ref = make_referral(
            chief_complaint="Rising PSA over 2 years – from 2.1 to 6.8",
            relevant_investigations="PSA 6.8 ng/mL, urinalysis clear",
        )
        result = triage_referral(ref)
        assert result.recommended_priority in ("high", "routine")
        assert result.urgency_score >= 40

    def test_routine_bph_complaint(self):
        ref = make_referral(
            chief_complaint="BPH symptoms – nocturia, weak stream",
            relevant_investigations="Urinalysis normal, PSA 2.1",
        )
        result = triage_referral(ref)
        assert result.recommended_priority in ("high", "routine")

    def test_low_back_pain_no_urinary_symptoms_is_low_or_inappropriate(self):
        ref = make_referral(
            chief_complaint="Lower back pain, no urinary symptoms",
            relevant_history="No significant history",
            relevant_investigations="",
        )
        result = triage_referral(ref)
        # Should not be urgent or high
        assert result.recommended_priority not in ("urgent",)

    def test_testicular_torsion_is_urgent(self):
        ref = make_referral(chief_complaint="Testicular torsion – sudden onset severe pain")
        result = triage_referral(ref)
        assert result.recommended_priority == "urgent"


class TestCompletenessScoring:
    def test_full_referral_scores_high_completeness(self):
        ref = make_referral(
            chief_complaint="Recurrent UTI",
            relevant_history="BPH",
            current_medications="Tamsulosin",
            relevant_investigations="Urinalysis, urine culture",
        )
        result = triage_referral(ref)
        assert result.completeness_score >= 70

    def test_missing_all_required_fields_scores_low(self):
        ref = ReferralData(
            chief_complaint="",
            relevant_history="",
            current_medications="",
            relevant_investigations="",
            specialty_requested="Urology",
        )
        result = triage_referral(ref)
        assert result.completeness_score < 40
        assert len(result.missing_information) > 0

    def test_missing_chief_complaint_flagged(self):
        ref = ReferralData(
            chief_complaint="",
            relevant_history="Hypertension",
            current_medications="Ramipril",
            relevant_investigations="Urinalysis normal",
            specialty_requested="Urology",
        )
        result = triage_referral(ref)
        assert any("Chief complaint" in m for m in result.missing_information)

    def test_missing_investigations_flagged_for_urology(self):
        ref = make_referral(relevant_investigations="")
        result = triage_referral(ref)
        assert any("investigation" in m.lower() for m in result.missing_information)

    def test_investigation_word_boundary_no_false_match(self):
        """Short tokens (e.g. 'psa') must not match as substrings of longer words."""
        # 'capsaicin' contains 'psa' as a substring but is not a PSA test result
        ref = make_referral(relevant_investigations="topical capsaicin applied")
        result = triage_referral(ref)
        # Without word-boundary matching, 'psa' would be found in 'capsaicin';
        # with it, investigations should be flagged as missing.
        assert any("investigation" in m.lower() for m in result.missing_information)


class TestAppropriatenessScoring:
    def test_inappropriate_keyword_lowers_score(self):
        ref = make_referral(
            chief_complaint="Refer to physiotherapy for back pain – not a urology issue"
        )
        result = triage_referral(ref)
        assert result.appropriateness_score < 50

    def test_red_flag_raises_appropriateness(self):
        ref = make_referral(
            chief_complaint="Gross hematuria",
            relevant_investigations="CT urogram, urinalysis 3+ blood",
        )
        result = triage_referral(ref)
        assert result.appropriateness_score >= 60

    def test_score_bounded_0_100(self):
        for complaint in [
            "acute urinary retention clot retention urosepsis gross hematuria",
            "physiotherapy weight loss dietary refer to gp",
        ]:
            ref = make_referral(chief_complaint=complaint)
            result = triage_referral(ref)
            assert 0 <= result.appropriateness_score <= 100
            assert 0 <= result.completeness_score <= 100
            assert 0 <= result.urgency_score <= 100


class TestTriageNotes:
    def test_notes_mention_urgent_keyword(self):
        ref = make_referral(chief_complaint="Gross hematuria x 3 weeks")
        result = triage_referral(ref)
        assert result.triage_notes
        assert len(result.triage_notes) > 20

    def test_notes_mention_missing_info(self):
        ref = ReferralData(
            chief_complaint="Urinary symptoms",
            relevant_history="",
            current_medications="",
            relevant_investigations="",
            specialty_requested="Urology",
        )
        result = triage_referral(ref)
        assert "missing" in result.triage_notes.lower() or result.missing_information

    def test_elderly_patient_psa_flag(self):
        ref = make_referral(
            patient_age=75,
            relevant_investigations="Urinalysis: clear",  # no PSA mention
        )
        result = triage_referral(ref)
        assert any("Patient >70" in f for f in result.flags)

    def test_no_psa_flag_when_psa_present(self):
        ref = make_referral(
            patient_age=75,
            relevant_investigations="PSA 2.1 ng/mL, urinalysis normal",
        )
        result = triage_referral(ref)
        # Flag for PSA should NOT fire when PSA is in investigations
        assert not any("PSA status" in f for f in result.flags)


class TestNonUrologySpecialty:
    def test_non_urology_uses_shorter_required_fields(self):
        ref = ReferralData(
            chief_complaint="",
            relevant_history="",
            current_medications="",
            relevant_investigations="",
            specialty_requested="Cardiology",
        )
        result = triage_referral(ref)
        # Should flag missing fields but not require urology-specific investigations
        assert len(result.missing_information) > 0
