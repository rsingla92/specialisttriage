"""Response template management routes."""
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import ResponseTemplate, VALID_CATEGORIES, VALID_TEMPLATE_TYPES

templates_bp = Blueprint("templates", __name__)


def _get_template_for_user(category, template_type):
    """Return user-specific template if it exists, otherwise system default."""
    user_tpl = ResponseTemplate.query.filter_by(
        category=category, template_type=template_type, created_by=current_user.id,
    ).first()
    if user_tpl:
        return user_tpl
    return ResponseTemplate.query.filter_by(
        category=category, template_type=template_type, created_by=None,
    ).first()


@templates_bp.route("/")
@login_required
def list_templates():
    """List all templates available to the current user."""
    system = ResponseTemplate.query.filter_by(created_by=None).all()
    user = ResponseTemplate.query.filter_by(created_by=current_user.id).all()
    return render_template("templates/list.html", system=system, user=user)


@templates_bp.route("/", methods=["POST"])
@login_required
def create_template():
    """Create or update a user-specific template override."""
    category = request.form.get("category", "")
    template_type = request.form.get("template_type", "")
    body_text = request.form.get("body_text", "").strip()

    if not body_text or category not in VALID_CATEGORIES or template_type not in VALID_TEMPLATE_TYPES:
        flash("Category, template type, and template text are required.", "danger")
        return redirect(url_for("templates.list_templates"))

    existing = ResponseTemplate.query.filter_by(
        category=category, template_type=template_type, created_by=current_user.id,
    ).first()
    if existing:
        existing.body_text = body_text
    else:
        tpl = ResponseTemplate(
            category=category,
            template_type=template_type,
            body_text=body_text,
            created_by=current_user.id,
        )
        db.session.add(tpl)

    db.session.commit()
    flash("Template saved.", "success")
    return redirect(url_for("templates.list_templates"))


@templates_bp.route("/api", methods=["GET", "POST"])
@login_required
def api_get_template():
    """JSON endpoint for fetching a rendered template."""
    if request.method == "POST":
        params = request.form
    else:
        params = request.args

    category = params.get("category", "")
    template_type = params.get("type", "needs_info")
    patient_name = params.get("patient", "")
    specialist_name = params.get("specialist", current_user.full_name)

    if category not in VALID_CATEGORIES:
        return jsonify({"error": "Invalid category"}), 400
    if template_type not in VALID_TEMPLATE_TYPES:
        return jsonify({"error": "Invalid template type"}), 400

    tpl = _get_template_for_user(category, template_type)
    if not tpl:
        return jsonify({"error": "Template not found"}), 404

    return jsonify({
        "id": tpl.id,
        "body": tpl.render(patient_name=patient_name, specialist_name=specialist_name),
        "raw": tpl.body_text,
    })
