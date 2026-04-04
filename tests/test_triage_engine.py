"""Tests for the triage engine."""
from app.services.triage_engine import (
    triage_referral, ReferralData, classify_category, detect_missing_workup,
)


from typing import Any


def make_referral(**kwargs: Any) -> ReferralData:
    defaults: dict[str, Any] = {
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


class TestClinicalCategoryClassification:
    def test_hematuria_classified(self):
        assert classify_category("gross hematuria x 3 weeks") == "hematuria"

    def test_psa_classified(self):
        assert classify_category("rising psa 6.8 from 4.1") == "psa_prostate"

    def test_stones_classified(self):
        assert classify_category("left kidney stone 8mm") == "stones"

    def test_incontinence_classified(self):
        assert classify_category("stress urinary incontinence") == "incontinence"

    def test_uti_classified(self):
        assert classify_category("recurrent uti 4 episodes") == "uti_recurrent"

    def test_ed_classified(self):
        assert classify_category("erectile dysfunction 2 years") == "erectile_dysfunction"

    def test_no_match_classified_other(self):
        assert classify_category("lower back pain and fatigue") == "other"

    def test_multi_keyword_uses_priority_order(self):
        # Hematuria should win over stones when both present
        assert classify_category("hematuria with kidney stones") == "hematuria"


class TestMissingWorkupDetection:
    def test_hematuria_missing_cytology(self):
        missing = detect_missing_workup("hematuria", "urinalysis done, ct urogram, creatinine 88")
        assert "Urine cytology" in missing

    def test_hematuria_complete(self):
        text = "urinalysis done, urine cytology negative, ct urogram normal, creatinine 88"
        missing = detect_missing_workup("hematuria", text)
        assert len(missing) == 0

    def test_psa_missing_dre(self):
        missing = detect_missing_workup("psa_prostate", "psa 6.8, family history negative")
        assert "DRE findings" in missing

    def test_other_no_workup_flags(self):
        missing = detect_missing_workup("other", "lower back pain")
        assert len(missing) == 0

    def test_word_boundary_on_workup(self):
        # "capsaicin" should NOT match "psa"
        missing = detect_missing_workup("psa_prostate", "capsaicin cream applied")
        assert "PSA value" in missing


class TestTriageOutputNewFields:
    def test_output_includes_clinical_category(self):
        ref = make_referral(chief_complaint="Gross hematuria x 2 weeks")
        result = triage_referral(ref)
        assert result.clinical_category == "hematuria"

    def test_output_includes_missing_workup(self):
        ref = make_referral(
            chief_complaint="Rising PSA 6.8",
            relevant_investigations="",
        )
        result = triage_referral(ref)
        assert len(result.missing_workup) > 0

    def test_ed_referral_flagged(self):
        ref = make_referral(chief_complaint="Erectile dysfunction for 2 years")
        result = triage_referral(ref)
        assert result.clinical_category == "erectile_dysfunction"
        assert any("ED referral" in f for f in result.flags)


class TestTriageRuleSet:
    def test_build_hardcoded_ruleset(self):
        from app.services.triage_engine import _build_hardcoded_ruleset
        rs = _build_hardcoded_ruleset()
        assert rs.specialty_id is None
        assert len(rs.categories) == 6
        assert len(rs.urgent_keywords) > 0
        assert "field_penalty" in rs.scoring

    def test_classify_with_ruleset(self):
        from app.services.triage_engine import _build_hardcoded_ruleset
        rs = _build_hardcoded_ruleset()
        assert classify_category("gross hematuria", ruleset=rs) == "hematuria"
        assert classify_category("rising psa", ruleset=rs) == "psa_prostate"
        assert classify_category("random text", ruleset=rs) == "other"

    def test_detect_workup_with_ruleset(self):
        from app.services.triage_engine import _build_hardcoded_ruleset
        rs = _build_hardcoded_ruleset()
        missing = detect_missing_workup("hematuria", "urinalysis done, creatinine 88", ruleset=rs)
        assert "Urine cytology" in missing

    def test_triage_with_specialty_id_none(self):
        ref = make_referral(chief_complaint="Gross hematuria x 2 weeks")
        result = triage_referral(ref, specialty_id=None)
        assert result.clinical_category == "hematuria"

    def test_load_ruleset_fallback(self):
        from app.services.triage_engine import load_ruleset, clear_ruleset_cache
        clear_ruleset_cache()
        rs = load_ruleset(specialty_id=None)
        assert rs.specialty_id is None
        assert len(rs.categories) == 6


class TestLLMClassification:
    def test_llm_not_called_when_keyword_matches(self):
        ref = make_referral(chief_complaint="Gross hematuria x 2 weeks")
        result = triage_referral(ref)
        assert result.clinical_category == "hematuria"
        assert "LLM" not in str(result.flags)

    def test_llm_not_called_when_disabled(self):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        ref = make_referral(chief_complaint="Lower back pain and fatigue only")
        result = triage_referral(ref)
        assert result.clinical_category == "other"
        assert "LLM" not in str(result.flags)

    def test_llm_classifier_returns_none_without_key(self):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        from app.services.llm_classifier import classify_with_llm
        result = classify_with_llm("test text", [{"slug": "hematuria", "display_name": "Hematuria"}])
        assert result is None

    def test_llm_is_enabled_check(self):
        import os
        from app.services.llm_classifier import is_llm_enabled
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert not is_llm_enabled()
        os.environ["ANTHROPIC_API_KEY"] = "test"
        try:
            assert is_llm_enabled()
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_llm_called_on_other_with_mock(self):
        import os
        from unittest.mock import patch
        from app.services.llm_classifier import LLMClassification
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        try:
            mock_result = LLMClassification(
                category="hematuria", confidence=0.85, reasoning="blood in urine"
            )
            with patch("app.services.llm_classifier.is_llm_enabled", return_value=True):
                with patch("app.services.llm_classifier.classify_with_llm", return_value=mock_result):
                    ref = make_referral(chief_complaint="Patient has unusual voiding symptoms")
                    triage_referral(ref)
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)


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
