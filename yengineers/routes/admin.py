"""Espace d'administration privé (/admin). Interface en français.

Sécurité : un before_request sur tout le blueprint refuse l'accès à toute route
(sauf la page de connexion) si l'administrateur n'est pas authentifié.
"""
import csv
import io
import re
from datetime import datetime, timezone

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .. import security
from ..db import IntegrityErrors, backup_db, get_db, list_backups
from ..services import registrations as regs
from ..services import settings as site_settings
from ..services.uploads import UploadError, delete_image, save_image

bp = Blueprint("admin", __name__)

STATUS_LABELS = {"new": "Nouveau", "contacted": "Contacté", "waiting": "En attente",
                 "archived": "Archivé"}
INTEREST_LABELS = {"robotics": "Robotique", "programming": "Programmation",
                   "electronics": "Électronique", "projects": "Projets pratiques"}
LEVEL_LABELS = {"beginner": "Débutant", "intermediate": "Intermédiaire", "advanced": "Avancé"}
LANG_LABELS = {"ar": "Arabe", "fr": "Français", "en": "Anglais"}
ICONS = {"robot": "Robot", "code": "Code", "chip": "Puce électronique",
         "wrench": "Outil / projet", "bulb": "Idée / innovation"}

DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


@bp.app_context_processor
def _admin_labels():
    return {
        "STATUS_LABELS": STATUS_LABELS, "INTEREST_LABELS": INTEREST_LABELS,
        "LEVEL_LABELS": LEVEL_LABELS, "LANG_LABELS": LANG_LABELS, "ICONS": ICONS,
        "STATUSES": regs.STATUSES, "INTERESTS": regs.INTERESTS, "LEVELS": regs.LEVELS,
        "LANG_CHOICES": regs.LANG_CHOICES,
    }


# --------------------------------------------------------------- accès
@bp.before_request
def require_login():
    """Contrôle d'accès serveur appliqué à TOUTES les routes d'administration."""
    g.lang = "fr"  # interface d'administration en français
    if request.endpoint == "admin.login":
        return None
    admin_id = session.get("admin_id")
    if admin_id:
        row = get_db().execute("SELECT id, username FROM admins WHERE id = ?", (admin_id,)).fetchone()
        if row:
            g.admin = row
            return None
        session.clear()
    target = request.full_path if request.query_string else request.path
    return redirect(url_for("admin.login", next=target.rstrip("?")))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_id"):
        return redirect(url_for("admin.dashboard"))
    cfg = current_app.config
    window = cfg["LOGIN_WINDOW_MINUTES"] * 60
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()[:64]
        password = request.form.get("password") or ""
        ip_key = security.client_key()
        user_key = security.key_for(username or "-")
        if (security.rate_count("login_fail", ip_key, window) >= cfg["LOGIN_MAX_ATTEMPTS"] * 2
                or security.rate_count("login_fail", user_key, window) >= cfg["LOGIN_MAX_ATTEMPTS"]):
            error = (f"Trop de tentatives. Réessayez dans {cfg['LOGIN_WINDOW_MINUTES']} minutes.")
            return render_template("admin/login.html", error=error), 429
        row = get_db().execute(
            "SELECT id, username, password_hash FROM admins WHERE lower(username) = lower(?)", (username,)
        ).fetchone()
        # Vérification systématique (même si l'utilisateur n'existe pas) : temps constant.
        ok = check_password_hash(row["password_hash"] if row else DUMMY_HASH, password)
        if row and ok:
            security.rate_clear("login_fail", user_key)
            next_url = security.safe_next(request.args.get("next"))
            session.clear()  # nouvelle session : empêche la fixation de session
            session.permanent = True
            session["admin_id"] = row["id"]
            security.rotate_csrf()
            with get_db() as db:
                db.execute("UPDATE admins SET last_login_at = datetime('now') WHERE id = ?", (row["id"],))
            return redirect(next_url or url_for("admin.dashboard"))
        security.rate_add("login_fail", ip_key)
        security.rate_add("login_fail", user_key)
        error = "Identifiant ou mot de passe incorrect."
        return render_template("admin/login.html", error=error), 401
    return render_template("admin/login.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("admin.login"))


@bp.route("/password", methods=["GET", "POST"])
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        db = get_db()
        row = db.execute("SELECT password_hash FROM admins WHERE id = ?", (g.admin["id"],)).fetchone()
        if not check_password_hash(row["password_hash"], current):
            flash("Mot de passe actuel incorrect.", "error")
        elif len(new) < 12:
            flash("Le nouveau mot de passe doit contenir au moins 12 caractères.", "error")
        elif new != confirm:
            flash("La confirmation ne correspond pas.", "error")
        else:
            with db:
                db.execute("UPDATE admins SET password_hash = ? WHERE id = ?",
                           (generate_password_hash(new), g.admin["id"]))
            flash("Mot de passe modifié.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/password.html")


# --------------------------------------------------------- tableau de bord
@bp.route("/")
def dashboard():
    stats = regs.dashboard_stats(get_db())
    return render_template("admin/dashboard.html", stats=stats)


# ------------------------------------------------------------ préinscriptions
def _page():
    try:
        return max(1, int(request.args.get("page", "1")))
    except ValueError:
        return 1


@bp.route("/registrations")
def registrations_list():
    cfg = current_app.config
    page = _page()
    rows, total = regs.list_registrations(
        get_db(), request.args, page, cfg["PAGE_SIZE"], cfg["LOCAL_UTC_OFFSET_HOURS"]
    )
    pages = max(1, -(-total // cfg["PAGE_SIZE"]))
    query = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("admin/registrations.html", rows=rows, total=total, page=page,
                           pages=pages, query=query, f=request.args)


@bp.route("/registrations/export.csv")
def registrations_export():
    cfg = current_app.config
    clause, params = regs.build_filters(request.args, cfg["LOCAL_UTC_OFFSET_HOURS"])
    rows = get_db().execute(
        f"SELECT r.*, {regs.INTEREST_AGG} FROM registrations r {clause} "
        "ORDER BY r.created_at DESC, r.id DESC", params
    ).fetchall()

    localdt = current_app.jinja_env.filters["localdt"]  # capturé ici : le générateur s'exécute hors requête

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL)
        buf.write("﻿")  # BOM UTF-8 : Excel lit correctement l'arabe
        writer.writerow(["Référence", "Date (heure locale)", "Statut", "Parent / tuteur",
                         "Prénom du jeune", "Âge", "Téléphone", "Email", "Langue",
                         "Centres d'intérêt", "Niveau", "Message", "Note admin"])
        yield buf.getvalue()
        for r in rows:
            buf.seek(0)
            buf.truncate(0)
            interests = "; ".join(INTEREST_LABELS.get(i, i) for i in (r["interests"] or "").split(",") if i)
            writer.writerow([regs.csv_safe(v) for v in [
                r["reference"], localdt(r["created_at"]), STATUS_LABELS[r["status"]],
                r["parent_name"], r["youth_first_name"], r["age"], r["phone"], r["email"],
                LANG_LABELS[r["preferred_language"]], interests,
                LEVEL_LABELS[r["experience_level"]], r["message"], r["admin_note"]]])
            yield buf.getvalue()

    filename = f"preinscriptions-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return Response(generate(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _get_registration(reg_id):
    row = get_db().execute(
        f"SELECT r.*, {regs.INTEREST_AGG} FROM registrations r WHERE r.id = ?", (reg_id,)
    ).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/registrations/<int:reg_id>", methods=["GET", "POST"])
def registration_detail(reg_id):
    row = _get_registration(reg_id)
    errors, values = {}, None
    if request.method == "POST":
        data, errors = regs.validate(request.form, require_consent=False)
        status = request.form.get("status", row["status"])
        note = regs.clean_text(request.form.get("admin_note"), multiline=True)[:2000]
        if status not in regs.STATUSES:
            errors["status"] = ("Statut invalide", {})
        if not errors:
            try:
                regs.update_registration(get_db(), reg_id, data, status, note)
            except IntegrityErrors:
                errors["email"] = ("Une autre préinscription existe déjà avec cet email et ce prénom.", {})
            else:
                flash("Préinscription mise à jour.", "success")
                return redirect(url_for("admin.registration_detail", reg_id=reg_id))
        values = dict(request.form)
        values["interests"] = request.form.getlist("interests")
    return render_template("admin/registration_detail.html", r=row, errors=errors,
                           values=values, errmsg=_admin_error_text)


def _admin_error_text(err):
    """Messages d'erreur de validation en français pour l'administration."""
    from ..i18n import translate
    key, params = err
    return translate("fr", key, **params) if key.startswith("err.") else key


@bp.route("/registrations/<int:reg_id>/status", methods=["POST"])
def registration_status(reg_id):
    _get_registration(reg_id)
    status = request.form.get("status")
    if status not in regs.STATUSES:
        abort(400)
    db = get_db()
    with db:
        db.execute("UPDATE registrations SET status=?, updated_at=datetime('now') WHERE id=?",
                   (status, reg_id))
    flash("Statut mis à jour.", "success")
    return redirect(security.safe_next(request.form.get("next")) or
                    url_for("admin.registration_detail", reg_id=reg_id))


@bp.route("/registrations/<int:reg_id>/delete", methods=["GET", "POST"])
def registration_delete(reg_id):
    row = _get_registration(reg_id)
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        cfg = current_app.config
        if cfg["DB_KIND"] == "sqlite":
            backup_db(cfg["DATABASE"], cfg["BACKUP_DIR"], label="before-delete")  # filet de sécurité
        db = get_db()
        with db:
            db.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
        flash(f"Préinscription {row['reference']} supprimée" + (" (une sauvegarde a été créée avant)." if cfg["DB_KIND"] == "sqlite" else "."), "success")
        return redirect(url_for("admin.registrations_list"))
    return render_template("admin/confirm_delete.html", what=f"la préinscription {row['reference']} "
                           f"({row['youth_first_name']})", action=url_for("admin.registration_delete", reg_id=reg_id),
                           back=url_for("admin.registration_detail", reg_id=reg_id))


# ---------------------------------------------------------------- activités
def _int_order(value, default=100):
    try:
        return max(0, min(100000, int(value)))
    except (TypeError, ValueError):
        return default


def _activity_form(row=None):
    f = request.form
    data = {"icon": f.get("icon", "robot"), "sort_order": _int_order(f.get("sort_order")),
            "is_published": 1 if f.get("is_published") else 0}
    errors = []
    for lg, name in (("ar", "arabe"), ("fr", "français"), ("en", "anglais")):
        title = regs.clean_text(f.get(f"title_{lg}"))
        desc = regs.clean_text(f.get(f"description_{lg}"), multiline=True)
        if not title:
            errors.append(f"Le titre en {name} est obligatoire.")
        if len(title) > 120:
            errors.append(f"Le titre en {name} est trop long (120 caractères max).")
        if len(desc) > 600:
            errors.append(f"La description en {name} est trop longue (600 caractères max).")
        data[f"title_{lg}"], data[f"description_{lg}"] = title, desc
    if data["icon"] not in ICONS:
        data["icon"] = "robot"
    return data, errors


@bp.route("/activities")
def activities_list():
    rows = get_db().execute("SELECT * FROM activities ORDER BY sort_order, id").fetchall()
    return render_template("admin/activities.html", rows=rows)


@bp.route("/activities/new", methods=["GET", "POST"])
def activity_new():
    return _activity_edit(None)


@bp.route("/activities/<int:act_id>/edit", methods=["GET", "POST"])
def activity_edit(act_id):
    return _activity_edit(act_id)


def _activity_edit(act_id):
    db = get_db()
    row = None
    if act_id is not None:
        row = db.execute("SELECT * FROM activities WHERE id = ?", (act_id,)).fetchone()
        if row is None:
            abort(404)
    if request.method == "POST":
        data, errors = _activity_form(row)
        cfg = current_app.config
        new_image = ""
        try:
            new_image = save_image(get_db(), request.files.get("image"),
                                   cfg["MAX_UPLOAD_MB"] * 1024 * 1024)
        except UploadError as exc:
            errors.append(str(exc))
        if errors:
            delete_image(get_db(), new_image)
            for e in errors:
                flash(e, "error")
            return render_template("admin/activity_form.html", row=row, v=request.form), 422
        old_image = row["image"] if row else ""
        image = new_image or old_image
        if request.form.get("remove_image") and not new_image:
            image = ""
        with db:
            if row is None:
                db.execute(
                    """INSERT INTO activities (title_ar,title_fr,title_en,description_ar,description_fr,
                       description_en,icon,image,sort_order,is_published) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (data["title_ar"], data["title_fr"], data["title_en"], data["description_ar"],
                     data["description_fr"], data["description_en"], data["icon"], image,
                     data["sort_order"], data["is_published"]))
            else:
                db.execute(
                    """UPDATE activities SET title_ar=?,title_fr=?,title_en=?,description_ar=?,
                       description_fr=?,description_en=?,icon=?,image=?,sort_order=?,is_published=?,
                       updated_at=datetime('now') WHERE id=?""",
                    (data["title_ar"], data["title_fr"], data["title_en"], data["description_ar"],
                     data["description_fr"], data["description_en"], data["icon"], image,
                     data["sort_order"], data["is_published"], act_id))
        if old_image and old_image != image:
            delete_image(get_db(), old_image)
        flash("Activité enregistrée.", "success")
        return redirect(url_for("admin.activities_list"))
    return render_template("admin/activity_form.html", row=row, v=None)


@bp.route("/activities/<int:act_id>/toggle", methods=["POST"])
def activity_toggle(act_id):
    db = get_db()
    row = db.execute("SELECT is_published FROM activities WHERE id = ?", (act_id,)).fetchone()
    if row is None:
        abort(404)
    with db:
        db.execute("UPDATE activities SET is_published = ?, updated_at=datetime('now') WHERE id = ?",
                   (0 if row["is_published"] else 1, act_id))
    flash("Activité masquée." if row["is_published"] else "Activité publiée.", "success")
    return redirect(url_for("admin.activities_list"))


@bp.route("/activities/<int:act_id>/delete", methods=["GET", "POST"])
def activity_delete(act_id):
    db = get_db()
    row = db.execute("SELECT * FROM activities WHERE id = ?", (act_id,)).fetchone()
    if row is None:
        abort(404)
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        with db:
            db.execute("DELETE FROM activities WHERE id = ?", (act_id,))
        delete_image(get_db(), row["image"])
        flash("Activité supprimée.", "success")
        return redirect(url_for("admin.activities_list"))
    return render_template("admin/confirm_delete.html", what=f"l'activité « {row['title_fr']} »",
                           action=url_for("admin.activity_delete", act_id=act_id),
                           back=url_for("admin.activities_list"))


# --------------------------------------------------------------------- FAQ
def _faq_form():
    f = request.form
    data = {"sort_order": _int_order(f.get("sort_order")),
            "is_published": 1 if f.get("is_published") else 0}
    errors = []
    for lg, name in (("ar", "arabe"), ("fr", "français"), ("en", "anglais")):
        q = regs.clean_text(f.get(f"question_{lg}"))
        a = regs.clean_text(f.get(f"answer_{lg}"), multiline=True)
        if not q or not a:
            errors.append(f"Question et réponse en {name} obligatoires.")
        if len(q) > 250 or len(a) > 1500:
            errors.append(f"Texte trop long en {name}.")
        data[f"question_{lg}"], data[f"answer_{lg}"] = q, a
    return data, errors


@bp.route("/faqs")
def faqs_list():
    rows = get_db().execute("SELECT * FROM faqs ORDER BY sort_order, id").fetchall()
    return render_template("admin/faqs.html", rows=rows)


@bp.route("/faqs/new", methods=["GET", "POST"])
def faq_new():
    return _faq_edit(None)


@bp.route("/faqs/<int:faq_id>/edit", methods=["GET", "POST"])
def faq_edit(faq_id):
    return _faq_edit(faq_id)


def _faq_edit(faq_id):
    db = get_db()
    row = None
    if faq_id is not None:
        row = db.execute("SELECT * FROM faqs WHERE id = ?", (faq_id,)).fetchone()
        if row is None:
            abort(404)
    if request.method == "POST":
        data, errors = _faq_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/faq_form.html", row=row, v=request.form), 422
        cols = ("question_ar", "question_fr", "question_en", "answer_ar", "answer_fr", "answer_en",
                "sort_order", "is_published")
        with db:
            if row is None:
                db.execute(f"INSERT INTO faqs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                           [data[c] for c in cols])
            else:
                db.execute("UPDATE faqs SET " + ",".join(f"{c}=?" for c in cols) +
                           ", updated_at=datetime('now') WHERE id=?", [data[c] for c in cols] + [faq_id])
        flash("Question enregistrée.", "success")
        return redirect(url_for("admin.faqs_list"))
    return render_template("admin/faq_form.html", row=row, v=None)


@bp.route("/faqs/<int:faq_id>/toggle", methods=["POST"])
def faq_toggle(faq_id):
    db = get_db()
    row = db.execute("SELECT is_published FROM faqs WHERE id = ?", (faq_id,)).fetchone()
    if row is None:
        abort(404)
    with db:
        db.execute("UPDATE faqs SET is_published = ?, updated_at=datetime('now') WHERE id = ?",
                   (0 if row["is_published"] else 1, faq_id))
    return redirect(url_for("admin.faqs_list"))


@bp.route("/faqs/<int:faq_id>/delete", methods=["GET", "POST"])
def faq_delete(faq_id):
    db = get_db()
    row = db.execute("SELECT * FROM faqs WHERE id = ?", (faq_id,)).fetchone()
    if row is None:
        abort(404)
    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            abort(400)
        with db:
            db.execute("DELETE FROM faqs WHERE id = ?", (faq_id,))
        flash("Question supprimée.", "success")
        return redirect(url_for("admin.faqs_list"))
    return render_template("admin/confirm_delete.html", what=f"la question « {row['question_fr']} »",
                           action=url_for("admin.faq_delete", faq_id=faq_id),
                           back=url_for("admin.faqs_list"))


# ---------------------------------------------------------------- paramètres
@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        values, errors = site_settings.validate_and_collect(request.form)
        cfg = current_app.config
        new_logo = ""
        try:
            new_logo = save_image(get_db(), request.files.get("logo"),
                                  cfg["MAX_UPLOAD_MB"] * 1024 * 1024)
        except UploadError as exc:
            errors.append(f"Logo : {exc}")
        if errors:
            delete_image(get_db(), new_logo)
            for e in errors:
                flash(e, "error")
        else:
            old_logo = site_settings.setting("logo_file")
            if new_logo:
                values["logo_file"] = new_logo
            elif request.form.get("remove_logo"):
                values["logo_file"] = ""
            site_settings.save_settings(values)
            if old_logo and values.get("logo_file", old_logo) != old_logo:
                delete_image(get_db(), old_logo)
            flash("Paramètres enregistrés.", "success")
            return redirect(url_for("admin.settings_page"))
    return render_template("admin/settings.html", groups=site_settings.SETTING_GROUPS,
                           values=site_settings.all_settings(), posted=request.form if request.method == "POST" else None)


# --------------------------------------------------------------- sauvegardes
@bp.route("/backups", methods=["GET", "POST"])
def backups():
    cfg = current_app.config
    if cfg["DB_KIND"] != "sqlite":
        return render_template("admin/backups.html", items=[], postgres=True)
    if request.method == "POST":
        backup_db(cfg["DATABASE"], cfg["BACKUP_DIR"], label="manual")
        flash("Sauvegarde créée dans le dossier des sauvegardes du serveur.", "success")
        return redirect(url_for("admin.backups"))
    return render_template("admin/backups.html", items=list_backups(cfg["BACKUP_DIR"]), postgres=False)


# -------------------------------------------------------------- déploiement
@bp.route("/deployment")
def deployment():
    """Diagnostic pour vérifier la chaîne Netlify → Render → PostgreSQL (aucun secret affiché)."""
    cfg = current_app.config
    db = get_db()
    db.execute("SELECT 1").fetchone()
    info = {
        "Base de données": "PostgreSQL" if cfg["DB_KIND"] == "postgres" else "SQLite (local)",
        "Mode production": "oui" if cfg["PRODUCTION"] else "non",
        "Cookie sécurisé (HTTPS)": "oui" if cfg["SESSION_COOKIE_SECURE"] else "non",
        "TRUST_PROXY (nombre de proxys)": cfg["TRUST_PROXY"],
        "CLIENT_IP_HEADER": cfg["CLIENT_IP_HEADER"] or "(aucun)",
        "Secret du proxy configuré": "oui" if cfg["PROXY_SHARED_SECRET"] else "non",
        "Secret du proxy reçu et valide": "oui" if security.proxy_secret_ok() else "non",
        "Adresse vue par l'application (remote_addr)": request.remote_addr,
        "Adresse utilisée pour la limitation (empreinte)": security.client_key(),
        "En-tête X-Forwarded-For": request.headers.get("X-Forwarded-For", "(absent)"),
        "Hôte vu": request.host,
        "Schéma vu": request.scheme,
    }
    return render_template("admin/deployment.html", info=info)
