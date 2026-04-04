"""Dashboard route."""
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import case, func
from sqlalchemy.orm import joinedload
from app import db
from app.models import Referral, TriageResult

dashboard_bp = Blueprint("dashboard", __name__)

_ITEMS_PER_PAGE = 20

_PRIORITY_SORT = case(
    (Referral.priority == "urgent", 0),
    (Referral.priority == "high", 1),
    (Referral.priority == "routine", 2),
    (Referral.priority == "low", 3),
    (Referral.priority == "needs_info", 4),
    (Referral.priority == "inappropriate", 5),
    else_=6,
)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    # Dual-queue support
    clinic_ids = current_user.active_clinic_ids
    has_clinics = bool(clinic_ids)
    tab = request.args.get("tab", "mine")

    if tab == "pool" and clinic_ids:
        base_q = Referral.query.filter(
            Referral.clinic_id.in_(clinic_ids),
            Referral.specialist_id.is_(None),
        )
    else:
        base_q = Referral.query.filter_by(specialist_id=current_user.id)

    # Queue counts
    pool_count = Referral.query.filter(
        Referral.clinic_id.in_(clinic_ids),
        Referral.specialist_id.is_(None),
    ).count() if clinic_ids else 0
    mine_count = Referral.query.filter_by(specialist_id=current_user.id).count()

    # Category filtering
    category = request.args.get("category")
    if category:
        base_q = base_q.filter_by(clinical_category=category)

    # Stats (always computed on user's referrals, not filtered)
    full_q = Referral.query.filter_by(specialist_id=current_user.id)
    stats = {
        "total": full_q.count(),
        "incomplete": full_q.filter(
            func.json_array_length(Referral.missing_workup) > 0
        ).count(),
        "pending": full_q.filter(
            Referral.status.in_(("pending", "triaged", "needs_info"))
        ).count(),
        "resolved": full_q.filter(
            Referral.status.in_(("accepted", "declined", "redirected"))
        ).count(),
    }

    # Time saved estimate (3 min per resolved referral this week)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    resolved_this_week = full_q.filter(
        Referral.resolved_at >= week_ago
    ).count()
    stats["time_saved_min"] = resolved_this_week * 3

    # Category counts
    cat_rows = (
        db.session.query(
            func.coalesce(Referral.clinical_category, "other"),
            func.count(Referral.id),
        )
        .filter(Referral.specialist_id == current_user.id)
        .group_by(Referral.clinical_category)
        .all()
    )
    category_counts = {cat: count for cat, count in cat_rows}

    # Sorting
    sort = request.args.get("sort", "")
    sort_dir = request.args.get("dir", "desc")
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    if sort == "urgency":
        order_expr = _PRIORITY_SORT.asc() if sort_dir == "asc" else _PRIORITY_SORT.desc()
        base_q = base_q.order_by(order_expr, Referral.received_at.desc())
    elif sort == "completeness":
        base_q = base_q.outerjoin(TriageResult)
        col = TriageResult.completeness_score
        order_expr = col.asc().nullslast() if sort_dir == "asc" else col.desc().nullslast()
        base_q = base_q.order_by(order_expr, Referral.received_at.desc())
    else:
        base_q = base_q.order_by(_PRIORITY_SORT, Referral.received_at.desc())

    # Eager-load specialist to avoid N+1
    base_q = base_q.options(
        joinedload(Referral.specialist),
        joinedload(Referral.triage_result),
    )

    # Pagination
    page = request.args.get("page", 1, type=int)
    pagination = base_q.paginate(page=page, per_page=_ITEMS_PER_PAGE, error_out=False)

    return render_template(
        "dashboard/index.html",
        referrals=pagination.items,
        pagination=pagination,
        stats=stats,
        category_counts=category_counts,
        current_category=category,
        current_sort=sort,
        current_dir=sort_dir,
        tab=tab,
        has_clinics=has_clinics,
        pool_count=pool_count,
        mine_count=mine_count,
    )
