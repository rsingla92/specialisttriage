"""Analytics dashboard routes."""
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, and_
from app import db
from app.models import Referral, TriageResult

analytics_bp = Blueprint("analytics", __name__)


def _date_cutoff(days):
    """Return UTC datetime for N days ago."""
    return datetime.now(timezone.utc) - timedelta(days=days)


def _get_date_filter(query_args, date_column):
    """Return a SQLAlchemy filter clause based on query parameters.

    Supports two modes:
    - start_date + end_date (ISO format strings): absolute date range
    - days (int): relative N-days-ago cutoff (0 = all time)

    Returns a filter clause or True (no filter).
    """
    start_str = query_args.get("start_date", type=str)
    end_str = query_args.get("end_date", type=str)

    if start_str and end_str:
        try:
            start_dt = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
            end_dt = datetime.fromisoformat(end_str).replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except (ValueError, TypeError):
            # Fall through to days-based logic on invalid dates
            pass
        else:
            if start_dt < end_dt:
                return and_(date_column >= start_dt, date_column <= end_dt)

    days = query_args.get("days", 30, type=int)
    if days > 0:
        cutoff = _date_cutoff(days)
        return date_column >= cutoff
    return True


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
    date_filter = _get_date_filter(request.args, Referral.received_at)

    rows = (
        db.session.query(
            func.date(Referral.received_at),
            func.count(Referral.id),
        )
        .filter(Referral.specialist_id == current_user.id)
        .filter(date_filter)
        .group_by(func.date(Referral.received_at))
        .order_by(func.date(Referral.received_at))
        .all()
    )
    return jsonify({"data": [{"date": str(d), "count": c} for d, c in rows]})


@analytics_bp.route("/api/analytics/categories")
@login_required
def categories():
    date_filter = _get_date_filter(request.args, Referral.received_at)

    q = db.session.query(
        func.coalesce(Referral.clinical_category, "other"),
        func.count(Referral.id),
    ).filter(Referral.specialist_id == current_user.id).filter(date_filter)

    rows = q.group_by(Referral.clinical_category).all()
    return jsonify({"data": [{"category": cat, "count": c} for cat, c in rows]})


@analytics_bp.route("/api/analytics/completeness")
@login_required
def completeness():
    date_filter = _get_date_filter(request.args, TriageResult.triaged_at)

    q = (
        db.session.query(
            func.date(TriageResult.triaged_at),
            func.avg(TriageResult.completeness_score),
        )
        .join(Referral, TriageResult.referral_id == Referral.id)
        .filter(Referral.specialist_id == current_user.id)
        .filter(date_filter)
    )

    rows = (
        q.group_by(func.date(TriageResult.triaged_at))
        .order_by(func.date(TriageResult.triaged_at))
        .all()
    )
    return jsonify({"data": [{"date": str(d), "avg": round(a, 1) if a else 0} for d, a in rows]})


@analytics_bp.route("/api/analytics/turnaround")
@login_required
def turnaround():
    date_filter = _get_date_filter(request.args, Referral.resolved_at)

    q = db.session.query(
        func.date(Referral.resolved_at),
        func.avg(
            (func.julianday(Referral.resolved_at) - func.julianday(Referral.received_at)) * 24
        ),
    ).filter(
        Referral.specialist_id == current_user.id,
        Referral.resolved_at.isnot(None),
    ).filter(date_filter)

    rows = (
        q.group_by(func.date(Referral.resolved_at))
        .order_by(func.date(Referral.resolved_at))
        .all()
    )
    return jsonify({"data": [{"date": str(d), "avg_hours": round(h, 1) if h else 0} for d, h in rows]})


@analytics_bp.route("/api/analytics/outcomes")
@login_required
def outcomes():
    date_filter = _get_date_filter(request.args, Referral.resolved_at)

    q = db.session.query(
        Referral.status,
        func.count(Referral.id),
    ).filter(
        Referral.specialist_id == current_user.id,
        Referral.status.in_(("accepted", "declined", "needs_info", "redirected")),
    ).filter(date_filter)

    rows = q.group_by(Referral.status).all()
    return jsonify({"data": [{"status": s, "count": c} for s, c in rows]})


@analytics_bp.route("/api/analytics/referring-physicians")
@login_required
def referring_physicians():
    date_filter = _get_date_filter(request.args, Referral.received_at)

    q = (
        db.session.query(
            Referral.referring_physician_name,
            func.count(Referral.id).label("volume"),
            func.avg(TriageResult.completeness_score).label("avg_completeness"),
        )
        .outerjoin(TriageResult, TriageResult.referral_id == Referral.id)
        .filter(Referral.specialist_id == current_user.id)
        .filter(date_filter)
    )

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
    date_filter = _get_date_filter(request.args, Referral.received_at)

    base = _base_query().filter(date_filter)

    total = base.count()

    avg_completeness = (
        db.session.query(func.avg(TriageResult.completeness_score))
        .join(Referral, TriageResult.referral_id == Referral.id)
        .filter(Referral.specialist_id == current_user.id)
        .filter(_get_date_filter(request.args, Referral.received_at))
        .scalar()
    )

    avg_turnaround = (
        db.session.query(
            func.avg(
                (func.julianday(Referral.resolved_at) - func.julianday(Referral.received_at)) * 24
            )
        )
        .filter(Referral.specialist_id == current_user.id, Referral.resolved_at.isnot(None))
        .filter(_get_date_filter(request.args, Referral.received_at))
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
