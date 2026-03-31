"""Admin routes for managing clinical rules per specialty."""
import json
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import (
    Specialty, ClinicalCategory, CategoryKeyword, WorkupItem, WorkupKeyword,
    PathwayGuidance,
)
from app.services.triage_engine import clear_ruleset_cache

# Only alphanumeric ASCII characters, spaces, hyphens, and underscores are
# allowed in keyword and workup-label inputs (no Unicode, no HTML/script tags).
_LABEL_RE = re.compile(r"^[a-zA-Z0-9\s\-_]+$")

admin_bp = Blueprint("admin", __name__)


def _get_specialty():
    """Get the current user's specialty, or the first active one."""
    if current_user.specialty_id:
        return db.session.get(Specialty, current_user.specialty_id)
    # Fallback: match by name
    if current_user.specialty:
        s = Specialty.query.filter_by(name=current_user.specialty).first()
        if s:
            return s
    return Specialty.query.filter_by(is_active=True).first()


@admin_bp.route("/")
@login_required
def rules_list():
    """List all categories and workup items for the specialist's specialty."""
    specialty = _get_specialty()
    if not specialty:
        flash("No specialty configured. Contact an administrator.", "warning")
        return redirect(url_for("dashboard.index"))

    categories = (
        ClinicalCategory.query
        .filter_by(specialty_id=specialty.id, is_active=True)
        .order_by(ClinicalCategory.priority_order)
        .all()
    )
    all_specialties = Specialty.query.filter_by(is_active=True).all()
    return render_template(
        "admin/rules_list.html",
        specialty=specialty,
        categories=categories,
        all_specialties=all_specialties,
    )


@admin_bp.route("/category/<slug>")
@login_required
def category_edit(slug):
    """Edit page for one category's workup items and keywords."""
    specialty = _get_specialty()
    if not specialty:
        return redirect(url_for("admin.rules_list"))

    category = ClinicalCategory.query.filter_by(
        specialty_id=specialty.id, slug=slug,
    ).first_or_404()

    return render_template("admin/category_edit.html", specialty=specialty, category=category)


@admin_bp.route("/category/<slug>/workup", methods=["POST"])
@login_required
def update_workup(slug):
    """Add or remove workup items for a category."""
    specialty = _get_specialty()
    category = ClinicalCategory.query.filter_by(
        specialty_id=specialty.id, slug=slug,
    ).first_or_404()

    action = request.form.get("action")

    if action == "add":
        label = request.form.get("label", "").strip()
        keywords_raw = request.form.get("keywords", "").strip()
        if label:
            if not _LABEL_RE.match(label):
                flash("Workup label may only contain letters, numbers, spaces, hyphens, and underscores.", "danger")
                return redirect(url_for("admin.category_edit", slug=slug))
            wi = WorkupItem(category_id=category.id, label=label)
            db.session.add(wi)
            db.session.flush()
            for kw in [k.strip() for k in keywords_raw.split(",") if k.strip()]:
                db.session.add(WorkupKeyword(
                    workup_item_id=wi.id, keyword=kw.lower(),
                    use_word_boundary=len(kw) <= 3,
                ))
            db.session.commit()
            clear_ruleset_cache()
            flash(f"Added workup item: {label}", "success")

    elif action == "delete":
        item_id = request.form.get("item_id", type=int)
        if item_id:
            wi = db.session.get(WorkupItem, item_id)
            if wi and wi.category_id == category.id:
                db.session.delete(wi)
                db.session.commit()
                clear_ruleset_cache()
                flash(f"Removed workup item: {wi.label}", "success")

    return redirect(url_for("admin.category_edit", slug=slug))


@admin_bp.route("/category/<slug>/keywords", methods=["POST"])
@login_required
def update_keywords(slug):
    """Add or remove classification keywords for a category."""
    specialty = _get_specialty()
    category = ClinicalCategory.query.filter_by(
        specialty_id=specialty.id, slug=slug,
    ).first_or_404()

    action = request.form.get("action")

    if action == "add":
        keyword = request.form.get("keyword", "").strip().lower()
        if keyword:
            if not _LABEL_RE.match(keyword):
                flash("Keywords may only contain letters, numbers, spaces, hyphens, and underscores.", "danger")
                return redirect(url_for("admin.category_edit", slug=slug))
            existing = CategoryKeyword.query.filter_by(
                category_id=category.id, keyword=keyword,
            ).first()
            if not existing:
                db.session.add(CategoryKeyword(
                    category_id=category.id, keyword=keyword,
                    use_word_boundary=len(keyword) <= 3,
                ))
                db.session.commit()
                clear_ruleset_cache()
                flash(f"Added keyword: {keyword}", "success")

    elif action == "delete":
        kw_id = request.form.get("keyword_id", type=int)
        if kw_id:
            ck = db.session.get(CategoryKeyword, kw_id)
            if ck and ck.category_id == category.id:
                db.session.delete(ck)
                db.session.commit()
                clear_ruleset_cache()
                flash(f"Removed keyword: {ck.keyword}", "success")

    return redirect(url_for("admin.category_edit", slug=slug))


@admin_bp.route("/category/<slug>/guidance", methods=["POST"])
@login_required
def update_guidance(slug):
    """Edit pathway guidance text for a category."""
    specialty = _get_specialty()
    category = ClinicalCategory.query.filter_by(
        specialty_id=specialty.id, slug=slug,
    ).first_or_404()

    consider_before_raw = request.form.get("consider_before", "").strip()
    refer_if = request.form.get("refer_if", "").strip()

    consider_before = [line.strip() for line in consider_before_raw.split("\n") if line.strip()]

    if category.guidance:
        category.guidance.consider_before = consider_before
        category.guidance.refer_if = refer_if
    else:
        db.session.add(PathwayGuidance(
            category_id=category.id,
            consider_before=consider_before,
            refer_if=refer_if,
        ))

    db.session.commit()
    clear_ruleset_cache()
    flash("Guidance updated.", "success")
    return redirect(url_for("admin.category_edit", slug=slug))


@admin_bp.route("/categories", methods=["POST"])
@login_required
def create_category():
    """Create a new clinical category for the specialty."""
    specialty = _get_specialty()
    if not specialty:
        return redirect(url_for("admin.rules_list"))

    name = request.form.get("display_name", "").strip()
    slug = request.form.get("slug", "").strip().lower().replace(" ", "_")

    if not name or not slug:
        flash("Name and slug are required.", "danger")
        return redirect(url_for("admin.rules_list"))

    existing = ClinicalCategory.query.filter_by(
        specialty_id=specialty.id, slug=slug,
    ).first()
    if existing:
        flash(f"Category '{slug}' already exists.", "warning")
        return redirect(url_for("admin.rules_list"))

    max_order = db.session.query(db.func.max(ClinicalCategory.priority_order)).filter_by(
        specialty_id=specialty.id,
    ).scalar() or 0

    cat = ClinicalCategory(
        specialty_id=specialty.id, slug=slug, display_name=name,
        priority_order=max_order + 1,
    )
    db.session.add(cat)
    db.session.commit()
    clear_ruleset_cache()
    flash(f"Created category: {name}", "success")
    return redirect(url_for("admin.category_edit", slug=slug))


@admin_bp.route("/export")
@login_required
def export_rules():
    """Export all rules for the specialty as JSON."""
    specialty = _get_specialty()
    if not specialty:
        return jsonify({"error": "No specialty"}), 400

    categories = ClinicalCategory.query.filter_by(
        specialty_id=specialty.id, is_active=True,
    ).order_by(ClinicalCategory.priority_order).all()

    data = {
        "specialty": specialty.name,
        "slug": specialty.slug,
        "categories": [],
    }
    for cat in categories:
        cat_data = {
            "slug": cat.slug,
            "display_name": cat.display_name,
            "priority_order": cat.priority_order,
            "keywords": [{"keyword": ck.keyword, "word_boundary": ck.use_word_boundary}
                         for ck in cat.keywords],
            "workup_items": [
                {
                    "label": wi.label,
                    "detection_keywords": [{"keyword": wk.keyword, "word_boundary": wk.use_word_boundary}
                                           for wk in wi.detection_keywords],
                }
                for wi in cat.workup_items
            ],
            "guidance": {
                "consider_before": cat.guidance.consider_before if cat.guidance else [],
                "refer_if": cat.guidance.refer_if if cat.guidance else "",
            } if cat.guidance else None,
        }
        data["categories"].append(cat_data)

    return jsonify(data)


@admin_bp.route("/import", methods=["POST"])
@login_required
def import_rules():
    """Import rules from JSON."""
    specialty = _get_specialty()
    if not specialty:
        flash("No specialty configured.", "warning")
        return redirect(url_for("admin.rules_list"))

    json_text = request.form.get("json_data", "")
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        flash("Invalid JSON.", "danger")
        return redirect(url_for("admin.rules_list"))

    imported = 0
    for cat_data in data.get("categories", []):
        slug = cat_data.get("slug")
        if not slug:
            continue

        cat = ClinicalCategory.query.filter_by(
            specialty_id=specialty.id, slug=slug,
        ).first()
        if not cat:
            cat = ClinicalCategory(
                specialty_id=specialty.id, slug=slug,
                display_name=cat_data.get("display_name", slug),
                priority_order=cat_data.get("priority_order", 0),
            )
            db.session.add(cat)
            db.session.flush()

        # Add keywords
        existing_kws = {ck.keyword for ck in cat.keywords}
        for kw_data in cat_data.get("keywords", []):
            kw = kw_data.get("keyword", "").lower()
            if kw and kw not in existing_kws:
                db.session.add(CategoryKeyword(
                    category_id=cat.id, keyword=kw,
                    use_word_boundary=kw_data.get("word_boundary", len(kw) <= 3),
                ))

        # Add workup items
        existing_items = {wi.label for wi in cat.workup_items}
        for wi_data in cat_data.get("workup_items", []):
            label = wi_data.get("label", "")
            if label and label not in existing_items:
                wi = WorkupItem(category_id=cat.id, label=label)
                db.session.add(wi)
                db.session.flush()
                for dk in wi_data.get("detection_keywords", []):
                    db.session.add(WorkupKeyword(
                        workup_item_id=wi.id, keyword=dk.get("keyword", ""),
                        use_word_boundary=dk.get("word_boundary", False),
                    ))

        imported += 1

    db.session.commit()
    clear_ruleset_cache()
    flash(f"Imported {imported} categories.", "success")
    return redirect(url_for("admin.rules_list"))
