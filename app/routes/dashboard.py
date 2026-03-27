"""Dashboard route."""
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app import db
from app.models import Referral

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    base_q = Referral.query.filter_by(specialist_id=current_user.id)

    stats = {
        "total": base_q.count(),
        "pending": base_q.filter_by(status="pending").count(),
        "urgent": base_q.filter_by(priority="urgent").count(),
        "high": base_q.filter_by(priority="high").count(),
        "inappropriate": base_q.filter_by(priority="inappropriate").count(),
        "needs_info": base_q.filter(
            db.or_(Referral.priority == "needs_info", Referral.status == "needs_info")
        ).count(),
        "resolved": base_q.filter(
            Referral.status.in_(("accepted", "declined", "redirected"))
        ).count(),
    }

    referrals = base_q.order_by(Referral.received_at.desc()).all()

    # Priority sort order for display
    priority_order = {"urgent": 0, "high": 1, "routine": 2, "low": 3, "needs_info": 4,
                      "inappropriate": 5, None: 6}
    referrals_sorted = sorted(referrals, key=lambda r: priority_order.get(r.priority, 6))

    return render_template("dashboard/index.html", referrals=referrals_sorted, stats=stats)
