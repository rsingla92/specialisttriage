"""JSON REST API routes for the specialist triage application."""
from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from app.models import Referral, TriageResult, Feedback

api_bp = Blueprint("api", __name__)


def _referral_to_dict(r: Referral) -> dict:
    return {
        "id": r.id,
        "ocean_referral_id": r.ocean_referral_id,
        "patient_name": r.patient_full_name,
        "patient_age": r.patient_age,
        "referring_physician": r.referring_physician_name,
        "referring_clinic": r.referring_clinic,
        "chief_complaint": r.chief_complaint,
        "specialty_requested": r.specialty_requested,
        "status": r.status,
        "priority": r.priority,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "triaged_at": r.triaged_at.isoformat() if r.triaged_at else None,
        "triage": _triage_to_dict(r.triage_result) if r.triage_result else None,
    }


def _triage_to_dict(t: TriageResult) -> dict:
    return {
        "appropriateness_score": t.appropriateness_score,
        "completeness_score": t.completeness_score,
        "urgency_score": t.urgency_score,
        "recommended_priority": t.recommended_priority,
        "missing_information": t.missing_information,
        "triage_notes": t.triage_notes,
        "flags": t.flags,
        "model_version": t.model_version,
        "triaged_at": t.triaged_at.isoformat() if t.triaged_at else None,
    }


@api_bp.route("/referrals")
@login_required
def list_referrals():
    query = Referral.query.filter_by(specialist_id=current_user.id)

    status_filter = request.args.get("status")
    if status_filter:
        query = query.filter_by(status=status_filter)

    priority_filter = request.args.get("priority")
    if priority_filter:
        query = query.filter_by(priority=priority_filter)

    referrals = query.order_by(Referral.received_at.desc()).all()
    return jsonify({"referrals": [_referral_to_dict(r) for r in referrals]})


@api_bp.route("/referrals/<int:referral_id>")
@login_required
def get_referral(referral_id):
    referral = Referral.query.get_or_404(referral_id)
    if referral.specialist_id != current_user.id and current_user.role != "admin":
        abort(403)
    return jsonify(_referral_to_dict(referral))


@api_bp.route("/stats")
@login_required
def stats():
    referrals = Referral.query.filter_by(specialist_id=current_user.id).all()
    priority_counts: dict[str, int] = {}
    for r in referrals:
        key = r.priority or "unclassified"
        priority_counts[key] = priority_counts.get(key, 0) + 1

    return jsonify(
        {
            "total": len(referrals),
            "by_priority": priority_counts,
            "pending": sum(1 for r in referrals if r.status == "pending"),
            "resolved": sum(
                1 for r in referrals if r.status in ("accepted", "declined")
            ),
        }
    )
