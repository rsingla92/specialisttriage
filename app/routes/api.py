"""JSON REST API routes for the specialist triage application."""
from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy import func, text
from app import db
from app.models import Referral, TriageResult

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health():
    """Health-check endpoint for load-balancer probes."""
    from sqlalchemy.exc import OperationalError, DatabaseError
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except (OperationalError, DatabaseError):
        db.session.rollback()
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return jsonify({"status": status, "db": db_ok}), 200 if db_ok else 503


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
        "clinical_category": r.clinical_category,
        "missing_workup": r.missing_workup or [],
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "triaged_at": r.triaged_at.isoformat() if r.triaged_at else None,
        "triage": _triage_to_dict(r.triage_result),  # type: ignore[arg-type]
    }


def _triage_to_dict(t: TriageResult | None) -> dict | None:
    if t is None:
        return None
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

    category_filter = request.args.get("category")
    if category_filter:
        query = query.filter_by(clinical_category=category_filter)

    referrals = query.order_by(Referral.received_at.desc()).all()
    return jsonify({"referrals": [_referral_to_dict(r) for r in referrals]})


@api_bp.route("/referrals/<int:referral_id>")
@login_required
def get_referral(referral_id):
    referral = db.session.get(Referral, referral_id)
    if referral is None:
        abort(404)
    if referral.specialist_id != current_user.id and current_user.role != "admin":
        abort(403)
    return jsonify(_referral_to_dict(referral))


@api_bp.route("/stats")
@login_required
def stats():
    base_q = Referral.query.filter_by(specialist_id=current_user.id)

    total = base_q.count()

    priority_rows = (
        db.session.query(
            db.func.coalesce(Referral.priority, "unclassified"),
            func.count(Referral.id),
        )
        .filter(Referral.specialist_id == current_user.id)
        .group_by(Referral.priority)
        .all()
    )
    priority_counts: dict[str, int] = {p: c for p, c in priority_rows}

    pending = base_q.filter_by(status="pending").count()
    resolved = base_q.filter(
        Referral.status.in_(("accepted", "declined", "redirected"))
    ).count()

    category_rows = (
        db.session.query(
            db.func.coalesce(Referral.clinical_category, "other"),
            func.count(Referral.id),
        )
        .filter(Referral.specialist_id == current_user.id)
        .group_by(Referral.clinical_category)
        .all()
    )
    category_counts: dict[str, int] = {c: n for c, n in category_rows}

    return jsonify(
        {
            "total": total,
            "by_priority": priority_counts,
            "by_category": category_counts,
            "pending": pending,
            "resolved": resolved,
        }
    )
