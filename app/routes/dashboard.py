"""Dashboard route."""
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Referral

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    referrals = (
        Referral.query.filter_by(specialist_id=current_user.id)
        .order_by(Referral.received_at.desc())
        .all()
    )

    stats = {
        "total": len(referrals),
        "pending": sum(1 for r in referrals if r.status == "pending"),
        "urgent": sum(1 for r in referrals if r.priority == "urgent"),
        "high": sum(1 for r in referrals if r.priority == "high"),
        "inappropriate": sum(1 for r in referrals if r.priority == "inappropriate"),
        "needs_info": sum(1 for r in referrals if r.priority == "needs_info" or r.status == "needs_info"),
        "resolved": sum(1 for r in referrals if r.status in ("accepted", "declined", "redirected")),
    }

    # Priority sort order for display
    priority_order = {"urgent": 0, "high": 1, "routine": 2, "low": 3, "needs_info": 4,
                      "inappropriate": 5, None: 6}
    referrals_sorted = sorted(referrals, key=lambda r: priority_order.get(r.priority, 6))

    return render_template("dashboard/index.html", referrals=referrals_sorted, stats=stats)
