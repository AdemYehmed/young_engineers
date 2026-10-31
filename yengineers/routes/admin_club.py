"""Administration du club : groupes, membres, séances, calendrier, présences, paiements, galerie.

Ces routes sont rattachées au même blueprint « admin » : le contrôle d'accès central
(`require_login`) et la protection CSRF s'appliquent donc automatiquement à toutes.
"""
import shutil
from datetime import date

from flask import abort, current_app, flash, redirect, render_template, request, url_for

from .. import security
from ..db import get_db
from ..services import club, media_files
from ..services.registrations import clean_text
from ..services.uploads import UploadError
from .admin import _get_registration, bp

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]
PAYMENT_STATE_LABELS = {"paid": "Payé", "partial": "Partiel", "unpaid": "Non payé"}


@bp.app_context_processor
def _club_labels():
    return {
        "MEMBER_LABELS": club.MEMBER_LABELS, "MEMBER_STATUSES": club.MEMBER_STATUSES,
        "SESSION_LABELS": club.SESSION_LABELS, "SESSION_STATUSES": club.SESSION_STATUSES,
        "ATTENDANCE_LABELS": club.ATTENDANCE_LABELS, "ATTENDANCE_STATUSES": club.ATTENDANCE_STATUSES,
        "METHOD_LABELS": club.METHOD_LABELS, "PAYMENT_METHODS": club.PAYMENT_METHODS,
        "PAYMENT_STATE_LABELS": PAYMENT_STATE_LABELS,
    }


@bp.app_template_filter("money")
def _money(millimes):
    return club.format_millimes(millimes)


def _today():
    return club.local_today(current_app.config["LOCAL_UTC_OFFSET_HOURS"])


def _flash_all(errors):
    for message in errors:
        flash(message, "error")


def _get_or_404(row):
    if row is None:
        abort(404)
    return row


def _confirm_page(what, action, back):
    return render_template("admin/confirm_delete.html", what=what, action=action, back=back)


# ===================================================================== groupes
@bp.route("/groups")
def groups_list():
    return render_template("admin/groups.html", rows=club.list_groups(get_db()))


@bp.route("/groups/new", methods=["GET", "POST"])
def group_new():
    return _group_form(None)


@bp.route("/groups/<int:group_id>/edit", methods=["GET", "POST"])
def group_edit(group_id):
    return _group_form(_get_or_404(club.get_group(get_db(), group_id)))


def _group_form(row):
    db = get_db()
    if request.method == "POST":
        data, errors = club.validate_group(db, request.form, row["id"] if row else None)
        if errors:
            _flash_all(errors)
            return render_template("admin/group_form.html", row=row, v=request.form), 422
        club.save_group(db, data, row["id"] if row else None)
        flash("Groupe enregistré.", "success")
        return redirect(url_for("admin.groups_list"))
    return render_template("admin/group_form.html", row=row, v=None)


@bp.route("/groups/<int:group_id>/delete", methods=["GET", "POST"])
def group_delete(group_id):
    row = _get_or_404(club.get_group(get_db(), group_id))
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        message = club.delete_group(get_db(), group_id)
        flash(message or "Groupe supprimé.", "error" if message else "success")
        return redirect(url_for("admin.groups_list"))
    return _confirm_page(f"le groupe « {row['name']} »", url_for("admin.group_delete", group_id=group_id),
                         url_for("admin.groups_list"))


# ===================================================================== membres
@bp.route("/members")
def members_list():
    db = get_db()
    rows = club.list_members(db, request.args)
    return render_template("admin/members.html", rows=rows, groups=club.list_groups(db), f=request.args)


@bp.route("/members/new", methods=["GET", "POST"])
def member_new():
    return _member_form(None)


@bp.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
def member_edit(member_id):
    return _member_form(_get_or_404(club.get_member(get_db(), member_id)))


def _member_form(row):
    db = get_db()
    groups = club.list_groups(db)
    if request.method == "POST":
        data, errors = club.validate_member(db, request.form)
        if errors:
            _flash_all(errors)
            return render_template("admin/member_form.html", row=row, v=request.form, groups=groups), 422
        if row is None:
            if data["group_id"] is None and data["age"] is not None:
                data["group_id"] = club.group_for_age(db, data["age"])  # groupe choisi selon l'âge
            if not data["joined_on"]:
                data["joined_on"] = _today().isoformat()
            member_id = club.create_member(db, data)
        else:
            member_id = row["id"]
            club.update_member(db, member_id, data)
        flash("Membre enregistré.", "success")
        return redirect(url_for("admin.member_detail", member_id=member_id))
    return render_template("admin/member_form.html", row=row, v=None, groups=groups)


@bp.route("/members/<int:member_id>")
def member_detail(member_id):
    db = get_db()
    member = _get_or_404(club.get_member(db, member_id))
    payments, total = club.member_payments(db, member_id)
    summary, history = club.member_attendance(db, member_id)
    registration = None
    if member["registration_id"]:
        registration = db.execute("SELECT id, reference FROM registrations WHERE id = ?",
                                  (member["registration_id"],)).fetchone()
    return render_template("admin/member_detail.html", m=member, payments=payments, total=total,
                           summary=summary, history=history, registration=registration,
                           today=_today().isoformat(), period=_today().isoformat()[:7])


@bp.route("/members/<int:member_id>/delete", methods=["GET", "POST"])
def member_delete(member_id):
    row = _get_or_404(club.get_member(get_db(), member_id))
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        message = club.delete_member(get_db(), member_id)
        if message:
            flash(message, "error")
            return redirect(url_for("admin.member_detail", member_id=member_id))
        flash("Membre supprimé.", "success")
        return redirect(url_for("admin.members_list"))
    return _confirm_page(f"le membre « {row['first_name']} {row['last_name']} » et ses présences",
                         url_for("admin.member_delete", member_id=member_id),
                         url_for("admin.member_detail", member_id=member_id))


@bp.route("/registrations/<int:reg_id>/confirm", methods=["POST"])
def registration_confirm(reg_id):
    """Confirme la préinscription et crée le membre dans le groupe correspondant à son âge."""
    _get_registration(reg_id)
    member_id, created = club.confirm_registration(get_db(), reg_id,
                                                   current_app.config["LOCAL_UTC_OFFSET_HOURS"])
    if member_id is None:
        abort(404)
    flash("Préinscription confirmée : le membre a été créé." if created
          else "Déjà confirmée : voici la fiche du membre.", "success")
    return redirect(url_for("admin.member_detail", member_id=member_id))


# ===================================================================== séances
@bp.route("/sessions")
def sessions_list():
    db = get_db()
    rows = club.list_sessions(db, request.args, today=_today().isoformat())
    return render_template("admin/sessions.html", rows=rows, groups=club.list_groups(db), f=request.args,
                           today=_today().isoformat())


@bp.route("/sessions/new", methods=["GET", "POST"])
def session_new():
    return _session_form(None)


@bp.route("/sessions/<int:session_id>/edit", methods=["GET", "POST"])
def session_edit(session_id):
    return _session_form(_get_or_404(club.get_session(get_db(), session_id)))


def _session_form(row):
    db = get_db()
    groups = club.list_groups(db, active_only=True)
    if request.method == "POST":
        data, errors = club.validate_session(db, request.form)
        if errors:
            _flash_all(errors)
            return render_template("admin/session_form.html", row=row, v=request.form, groups=groups), 422
        if row is None:
            ids = club.create_sessions(db, data)
            flash(f"{len(ids)} séance(s) créée(s).", "success")
            if len(ids) == 1:
                return redirect(url_for("admin.session_detail", session_id=ids[0]))
            return redirect(url_for("admin.calendar", month=data["session_date"][:7]))
        club.update_session(db, row["id"], data)
        flash("Séance enregistrée.", "success")
        return redirect(url_for("admin.session_detail", session_id=row["id"]))
    prefill = {"session_date": club.parse_date(request.args.get("date")) or "",
               "group_id": request.args.get("group", "")} if row is None else None
    return render_template("admin/session_form.html", row=row, v=prefill, groups=groups)


@bp.route("/sessions/<int:session_id>")
def session_detail(session_id):
    db = get_db()
    session = _get_or_404(club.get_session(db, session_id))
    roster = club.session_roster(db, session)
    media = db.execute("SELECT * FROM media_items WHERE session_id = ? ORDER BY created_at DESC, id DESC",
                       (session_id,)).fetchall()
    return render_template("admin/session_detail.html", s=session, roster=roster, media=media)


@bp.route("/sessions/<int:session_id>/attendance", methods=["POST"])
def session_attendance(session_id):
    db = get_db()
    session = _get_or_404(club.get_session(db, session_id))
    comment = clean_text(request.form.get("comment"), multiline=True)[:4000]
    with db:
        db.execute("UPDATE club_sessions SET comment = ?, updated_at = datetime('now') WHERE id = ?",
                   (comment, session_id))
    count = club.save_attendance(db, session, request.form)
    flash(f"Présences et commentaire enregistrés ({count} membre(s) dans la liste).", "success")
    return redirect(url_for("admin.session_detail", session_id=session_id))


@bp.route("/sessions/<int:session_id>/delete", methods=["GET", "POST"])
def session_delete(session_id):
    row = _get_or_404(club.get_session(get_db(), session_id))
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        club.delete_session(get_db(), session_id)
        flash("Séance supprimée.", "success")
        return redirect(url_for("admin.sessions_list"))
    return _confirm_page(f"la séance du {row['session_date']} ({row['group_name']}) avec ses présences",
                         url_for("admin.session_delete", session_id=session_id),
                         url_for("admin.session_detail", session_id=session_id))


@bp.route("/calendar")
def calendar():
    today = _today()
    month = club.parse_month(request.args.get("month"), today.isoformat()[:7])
    year, mon = int(month[:4]), int(month[5:7])
    db = get_db()
    group = request.args.get("group", "")
    group_id = int(group) if group.isdigit() else None
    weeks = club.month_calendar(db, year, mon, group_id)
    py, pm = club.shift_month(year, mon, -1)
    ny, nm = club.shift_month(year, mon, 1)
    return render_template("admin/calendar.html", weeks=weeks, label=f"{MONTHS_FR[mon - 1]} {year}", month=month,
                           prev_month=f"{py:04d}-{pm:02d}", next_month=f"{ny:04d}-{nm:02d}",
                           this_month=today.isoformat()[:7], group=group_id, today=today,
                           groups=club.list_groups(db))


# ===================================================================== paiements
@bp.route("/payments")
def payments_page():
    db = get_db()
    period = club.parse_month(request.args.get("month"), _today().isoformat()[:7])
    group = request.args.get("group", "")
    group_id = int(group) if group.isdigit() else None
    items, totals = club.month_overview(db, period, group_id)
    payments = club.list_payments(db, period=period)
    year, mon = int(period[:4]), int(period[5:7])
    py, pm = club.shift_month(year, mon, -1)
    ny, nm = club.shift_month(year, mon, 1)
    return render_template("admin/payments.html", items=items, totals=totals, payments=payments,
                           period=period, label=f"{MONTHS_FR[mon - 1]} {year}", group=group_id,
                           groups=club.list_groups(db), prev_month=f"{py:04d}-{pm:02d}",
                           next_month=f"{ny:04d}-{nm:02d}")


@bp.route("/payments/new", methods=["GET", "POST"])
def payment_new():
    return _payment_form(None)


@bp.route("/payments/<int:payment_id>/edit", methods=["GET", "POST"])
def payment_edit(payment_id):
    return _payment_form(_get_or_404(club.get_payment(get_db(), payment_id)))


def _payment_form(row):
    db = get_db()
    members = [m for m in club.list_members(db, {}) if m["status"] != "left" or (row and m["id"] == row["member_id"])]
    next_url = security.safe_next(request.values.get("next"))
    if request.method == "POST":
        data, errors = club.validate_payment(db, request.form, current_app.config["LOCAL_UTC_OFFSET_HOURS"])
        if errors:
            _flash_all(errors)
            return render_template("admin/payment_form.html", row=row, v=request.form, members=members,
                                   next_url=next_url), 422
        if row is None:
            club.add_payment(db, data)
        else:
            club.update_payment(db, row["id"], data)
        flash("Paiement enregistré.", "success")
        return redirect(next_url or url_for("admin.payments_page", month=data["period"]))
    prefill = None
    if row is None:
        prefill = {"member_id": request.args.get("member", ""), "paid_on": _today().isoformat(),
                   "period": request.args.get("month", "")}
    return render_template("admin/payment_form.html", row=row, v=prefill, members=members, next_url=next_url)


@bp.route("/payments/<int:payment_id>/delete", methods=["GET", "POST"])
def payment_delete(payment_id):
    row = _get_or_404(club.get_payment(get_db(), payment_id))
    back = url_for("admin.member_detail", member_id=row["member_id"])
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        club.delete_payment(get_db(), payment_id)
        flash("Paiement supprimé.", "success")
        return redirect(back)
    return _confirm_page(f"le paiement de {club.format_millimes(row['amount_millimes'])} DT de "
                         f"{row['first_name']} {row['last_name']} ({row['paid_on']})",
                         url_for("admin.payment_delete", payment_id=payment_id), back)


# ===================================================================== galerie
@bp.route("/gallery")
def gallery_list():
    cfg = current_app.config
    db = get_db()
    items = media_files.list_items(db, limit=300)
    try:
        free = shutil.disk_usage(cfg["MEDIA_DIR"]).free
    except OSError:
        free = None
    return render_template("admin/gallery.html", items=items, free=free,
                           max_photo=cfg["MAX_PHOTO_MB"], max_video=cfg["MAX_VIDEO_MB"])


def _recent_sessions(db):
    return db.execute(
        "SELECT s.id, s.session_date, s.title, g.name AS group_name FROM club_sessions s "
        "JOIN club_groups g ON g.id = s.group_id ORDER BY s.session_date DESC, s.id DESC LIMIT 80").fetchall()


def _media_fields(db, form):
    """Champs communs (titre, légende, séance, publication). Retourne (valeurs, erreurs)."""
    errors = []
    title = clean_text(form.get("title"))[:150]
    caption = clean_text(form.get("caption"), multiline=True)[:1000]
    session_raw = clean_text(form.get("session_id"))
    session_id = None
    if session_raw:
        if not session_raw.isdigit() or club.get_session(db, int(session_raw)) is None:
            errors.append("Séance inconnue.")
        else:
            session_id = int(session_raw)
    is_public = bool(form.get("is_public"))
    consent = bool(form.get("consent_confirmed"))
    if is_public and not consent:
        errors.append("Pour publier sur le site, confirmez que les parents ont donné leur accord "
                      "(case « consentement des parents »).")
    return {"title": title, "caption": caption, "session_id": session_id,
            "is_public": is_public, "consent": consent}, errors


@bp.route("/gallery/upload", methods=["GET", "POST"])
def gallery_upload():
    cfg = current_app.config
    db = get_db()
    sessions = _recent_sessions(db)
    if request.method == "POST":
        fields, errors = _media_fields(db, request.form)
        files = [f for f in request.files.getlist("files") if f and f.filename]
        if not files:
            errors.append("Choisissez au moins un fichier.")
        if errors:
            _flash_all(errors)
            return render_template("admin/gallery_upload.html", v=request.form, sessions=sessions,
                                   max_photo=cfg["MAX_PHOTO_MB"], max_video=cfg["MAX_VIDEO_MB"]), 422
        added = 0
        for f in files:
            try:
                stored = media_files.store_file(f, cfg["MEDIA_DIR"], cfg["MAX_PHOTO_MB"] * 1024 * 1024,
                                                cfg["MAX_VIDEO_MB"] * 1024 * 1024)
            except UploadError as exc:
                flash(f"{f.filename} : {exc}", "error")
                continue
            try:
                media_files.add_item(db, stored, fields["title"], fields["caption"], fields["session_id"],
                                     fields["is_public"], fields["consent"])
            except Exception:
                media_files.delete_file(cfg["MEDIA_DIR"], stored["filename"])  # pas de fichier orphelin
                raise
            added += 1
        if added:
            flash(f"{added} fichier(s) ajouté(s).", "success")
            return redirect(url_for("admin.gallery_list"))
        return render_template("admin/gallery_upload.html", v=request.form, sessions=sessions,
                               max_photo=cfg["MAX_PHOTO_MB"], max_video=cfg["MAX_VIDEO_MB"]), 422
    prefill = {"session_id": request.args.get("session", "")}
    return render_template("admin/gallery_upload.html", v=prefill, sessions=sessions,
                           max_photo=cfg["MAX_PHOTO_MB"], max_video=cfg["MAX_VIDEO_MB"])


@bp.route("/gallery/<int:item_id>/edit", methods=["GET", "POST"])
def gallery_edit(item_id):
    db = get_db()
    item = _get_or_404(media_files.get_item(db, item_id))
    sessions = _recent_sessions(db)
    if request.method == "POST":
        fields, errors = _media_fields(db, request.form)
        if errors:
            _flash_all(errors)
            return render_template("admin/gallery_edit.html", item=item, v=request.form, sessions=sessions), 422
        media_files.update_item(db, item_id, fields["title"], fields["caption"], fields["session_id"],
                                fields["is_public"], fields["consent"])
        flash("Média mis à jour.", "success")
        return redirect(url_for("admin.gallery_list"))
    return render_template("admin/gallery_edit.html", item=item, v=None, sessions=sessions)


@bp.route("/gallery/<int:item_id>/delete", methods=["GET", "POST"])
def gallery_delete(item_id):
    db = get_db()
    item = _get_or_404(media_files.get_item(db, item_id))
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        media_files.delete_item(db, item_id)
        media_files.delete_file(current_app.config["MEDIA_DIR"], item["filename"])
        flash("Média supprimé.", "success")
        return redirect(url_for("admin.gallery_list"))
    return _confirm_page(f"le fichier « {item['title'] or item['original_name']} »",
                         url_for("admin.gallery_delete", item_id=item_id), url_for("admin.gallery_list"))
