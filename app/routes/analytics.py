"""Analytics dashboard routes."""
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import Referral, TriageResult

analytics_bp = Blueprint("analytics", __name__)


def _date_cutoff(days):
    """Return UTC datetime for N days ago."""
    return datetime.now(timezone.utc) - timedelta(days=days)


def _base_query():
    """Referrals owned by the current user."""
    return Referral.query.filter_by(specialist_id=current_user.id)


@analytics_bp.route("/analytics")
@login_required
def index():
    return render_template("analytics/index.html")


@analytics_bp.route("/api/analytics/volume")
@login_required
def volume():
    days = request.args.get("days", 30, type=int)
    cutoff = _date_cutoff(days) if days > 0 else None

    rows = (
        db.session.query(
            func.date(Referral.received_at),
            func.count(Referral.id),
        )
        .filter(Referral.specialist_id == current_user.id)
        .filter(Referral.received_at >= cutoff if cutoff else True)
        .group_by(func.date(Referral.received_at))
        .order_by(func.date(Referral.received_at))
        .all()
    )
    return jsonify({"data": [{"date": str(d), "count": c} for d, c in rows]})


@analytics_bp.route("/api/analytics/categories")
@login_required
def categories():
    days = request.args.get("days", 30, type=int)
    cutoff = _date_cutoff(days) if days > 0 else None

    q = db.session.query(
        func.coalesce(Referral.clinical_category, "other"),
        func.count(Referral.id),
    ).filter(Referral.specialist_id == current_user.id)

    if cutoff:
        q = q.filter(Referral.received_at >= cutoff)

    rows = q.group_by(Referral.clinical_category).all()
    return jsonify({"data": [{"category": cat, "count": c} for cat, c in rows]})


@analytics_bp.route("/api/analytics/completeness")
@login_required
def completeness():
    days = request.args.get("days", 30, type=int)
    cutoff = _date_cutoff(days) if days > 0 else None

    q = (
        db.session.query(
            func.date(TriageResult.triaged_at),
            func.avg(TriageResult.completeness_score),
        )
        .join(Referral, TriageResult.referral_id == Referral.id)
        .filter(Referral.specialist_id == current_user.id)
    )
    if cutoff:
        q = q.filter(TriageResult.triaged_at >= cutoff)

    rows = (
        q.group_by(func.date(TriageResult.triaged_at))
        .order_by(func.date(TriageResult.triaged_at))
        .all()
    )
    return jsonify({"data": [{"date": str(d), "avg": round(a, 1) if a else 0} for d, a in rows]})


@analytics_bp.route("/api/analytics/turnaround")
@login_required
def turnaround():
    days = request.args.get("days", 30, type=int)
    cutoff = _date_cutoff(days) if days > 0 else None

    q = db.session.query(
        func.date(Referral.resolved_at),
        func.avg(
            (func.julianday(Referral.resolved_at) - func.julianday(Referral.received_at)) * 24
        ),
    ).filter(
        Referral.specialist_id == current_user.id,
        Referral.resolved_at.isnot(None),
    )
    if cutoff:
        q = q.filter(Referral.resolved_at >= cutoff)

    rows = (
        q.group_by(func.date(Referral.resolved_at))
        .order_by(func.date(Referral.resolved_at))
        .all()
    )
    return jsonify({"data": [{"date": str(d), "avg_hours": round(h, 1) if h else 0} for d, h in rows]})


@analytics_bp.route("/api/analytics/outcomes")
@login_required
def outcomes():
    days = request.args.get("days", 30, type=int)
    cutoff = _date_cutoff(days) if days > 0 else None

    q = db.session.query(
        Referral.status,
        func.count(Referral.id),
    ).filter(
        Referral.specialist_id == current_user.id,
        Referral.status.in_(("accepted", "declined", "needs_info", "redirected")),
    )
    if cutoff:
        q = q.filter(Referral.resolved_at >= cutoff)

    rows = q.group_by(Referral.status).all()
    return jsonify({"data": [{"status": s, "count": c} for s, c in rows]})


@analytics_bp.route("/api/analytics/referring-physicians")
@login_required
def referring_physicians():
    days = request.args.get("days", 30, type=int)
    cutoff = _date_cutoff(days) if days > 0 else None

    q = (
        db.session.query(
            Referral.referring_physician_name,
            func.count(Referral.id).label("volume"),
            func.avg(TriageResult.completeness_score).label("avg_completeness"),
        )
        .outerjoin(TriageResult, TriageResult.referral_id == Referral.id)
        .filter(Referral.specialist_id == current_user.id)
    )
    if cutoff:
        q = q.filter(Referral.received_at >= cutoff)

    rows = (
        q.group_by(Referral.referring_physician_name)
        .order_by(func.count(Referral.id).desc())
        .limit(10)
        .all()
    )
    return jsonify({"data": [
        {"name": name, "volume": vol, "avg_completeness": round(ac, 1) if ac else None}
        for name, vol, ac in rows
    ]})


@analytics_bp.route("/api/analytics/summary")
@login_required
def summary():
    """Summary stats for the analytics header cards."""
    days = request.args.get("days", 30, type=int)
    cutoff = _date_cutoff(days) if days > 0 else None

    base = _base_query()
    if cutoff:
        base = base.filter(Referral.received_at >= cutoff)

    total = base.count()

    avg_completeness = (
        db.session.query(func.avg(TriageResult.completeness_score))
        .join(Referral, TriageResult.referral_id == Referral.id)
        .filter(Referral.specialist_id == current_user.id)
        .filter(Referral.received_at >= cutoff if cutoff else True)
        .scalar()
    )

    resolved = base.filter(Referral.resolved_at.isnot(None))
    avg_turnaround = (
        db.session.query(
            func.avg(
                (func.julianday(Referral.resolved_at) - func.julianday(Referral.received_at)) * 24
            )
        )
        .filter(Referral.specialist_id == current_user.id, Referral.resolved_at.isnot(None))
        .filter(Referral.received_at >= cutoff if cutoff else True)
        .scalar()
    )

    accepted = base.filter_by(status="accepted").count()
    acceptance_rate = (accepted / total * 100) if total > 0 else 0

    return jsonify({
        "total": total,
        "avg_completeness": round(avg_completeness, 1) if avg_completeness else 0,
        "avg_turnaround_hours": round(avg_turnaround, 1) if avg_turnaround else 0,
        "acceptance_rate": round(acceptance_rate, 1),
    })
