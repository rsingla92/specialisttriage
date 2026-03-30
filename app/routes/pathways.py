"""Public FP pre-referral pathway pages. Loads content from DB when available."""
from flask import Blueprint, render_template, abort
from app.models import Specialty, ClinicalCategory

pathways_bp = Blueprint("pathways", __name__)


@pathways_bp.route("/pathways")
def index():
    """List all specialties with their pathway categories."""
    specialties = Specialty.query.filter_by(is_active=True).all()
    spec_data = []
    for s in specialties:
        cats = (
            ClinicalCategory.query
            .filter_by(specialty_id=s.id, is_active=True)
            .order_by(ClinicalCategory.priority_order)
            .all()
        )
        if cats:
            spec_data.append({"specialty": s, "categories": cats})

    return render_template("pathways/index.html", specialties=spec_data)


@pathways_bp.route("/pathways/<specialty_slug>/<category_slug>")
def pathway(specialty_slug, category_slug):
    """Show the pre-referral pathway for a specific clinical category."""
    specialty = Specialty.query.filter_by(slug=specialty_slug, is_active=True).first_or_404()
    category = ClinicalCategory.query.filter_by(
        specialty_id=specialty.id, slug=category_slug, is_active=True,
    ).first_or_404()

    workup_items = category.workup_items
    guidance = category.guidance

    return render_template(
        "pathways/pathway.html",
        specialty=specialty,
        category=category,
        label=category.display_name,
        workup_items=workup_items,
        consider_before=guidance.consider_before if guidance else [],
        refer_if=guidance.refer_if if guidance else "",
        source=guidance.source if guidance else None,
    )


# Legacy route: redirect /pathways/<category> to /pathways/urology/<category>
@pathways_bp.route("/pathways/<category_slug>")
def pathway_legacy(category_slug):
    """Backward-compatible route for urology pathways."""
    from flask import redirect, url_for
    return redirect(url_for("pathways.pathway",
                            specialty_slug="urology", category_slug=category_slug))
