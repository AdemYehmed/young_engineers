"""Site public : accueil, préinscription, pages légales, langue, médias."""
import re
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, send_from_directory, session, url_for)

from .. import security
from ..db import DatabaseErrors, get_db
from ..i18n import LANGS, t
from ..services import registrations as regs

bp = Blueprint("public", __name__)

MEDIA_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|gif|webp)$")


@bp.route("/")
def home():
    db = get_db()
    activities = db.execute(
        "SELECT * FROM activities WHERE is_published = 1 ORDER BY sort_order, id"
    ).fetchall()
    faqs = db.execute(
        "SELECT * FROM faqs WHERE is_published = 1 ORDER BY sort_order, id"
    ).fetchall()
    return render_template("index.html", activities=activities, faqs=faqs)


@bp.route("/lang/<code>")
def set_language(code):
    if code in LANGS:
        session["lang"] = code
    target = security.safe_next(request.args.get("next"), prefix="/")
    return redirect(target or url_for("public.home"))


def _render_form(values=None, errors=None, status=200):
    return render_template(
        "register.html",
        values=values or {},
        errors=errors or {},
        form_token=security.make_form_token(),
        interests=regs.INTERESTS,
        levels=regs.LEVELS,
    ), status


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return _render_form()

    form = request.form
    cfg = current_app.config

    # 1) Piège à robots : champ caché que seul un script remplit.
    if form.get("company_website"):
        session["reg_done"] = {"reference": "", "duplicate": False}
        return redirect(url_for("public.register_done"))

    values = {k: form.get(k, "") for k in
              ("parent_name", "youth_first_name", "age", "phone", "email",
               "preferred_language", "experience_level", "message")}
    values["interests"] = form.getlist("interests")
    values["consent"] = form.get("consent")

    # 2) Limitation par connexion (clé HMAC, pas d'IP en clair).
    client = security.client_key()
    if security.rate_count("register", client, 3600) >= cfg["REGISTER_MAX_PER_HOUR"]:
        flash(t("err.rate_limited"), "error")
        return _render_form(values, status=429)

    # 3) Jeton temporel : trop rapide = robot ; trop ancien = formulaire expiré.
    age = security.form_token_age(form.get("form_token"))
    if age is None:
        flash(t("err.expired"), "error")
        return _render_form(values, status=400)
    if age < cfg["MIN_FORM_SECONDS"]:
        flash(t("err.too_fast"), "error")
        return _render_form(values, status=400)

    # 4) Validation serveur (la validation navigateur n'est qu'un confort).
    data, errors = regs.validate(form)
    if errors:
        return _render_form(values, errors, status=422)

    # 5) Enregistrement réel dans SQLite.
    db = get_db()
    try:
        reference = regs.create_registration(db, data)
    except regs.DuplicateRegistration:
        security.rate_add("register", client)
        session["reg_done"] = {"reference": "", "duplicate": True}
        return redirect(url_for("public.register_done"))
    except DatabaseErrors + (RuntimeError,):
        current_app.logger.exception("Échec d'enregistrement d'une préinscription")
        flash(t("err.db"), "error")
        return _render_form(values, status=500)

    security.rate_add("register", client)
    session["reg_done"] = {"reference": reference, "duplicate": False}
    return redirect(url_for("public.register_done"))


@bp.route("/register/done")
def register_done():
    done = session.get("reg_done")
    if not done:
        return redirect(url_for("public.register"))
    return render_template("confirmation.html", done=done)


@bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@bp.route("/legal")
def legal():
    return render_template("legal.html")


@bp.route("/media/<path:filename>")
def media(filename):
    if not MEDIA_RE.match(filename):
        abort(404)
    row = get_db().execute("SELECT mimetype, data FROM media WHERE name = ?", (filename,)).fetchone()
    if row is not None:
        response = Response(bytes(row["data"]), mimetype=row["mimetype"])
    else:  # anciennes installations : images stockées sur le disque
        legacy = Path(current_app.config["UPLOAD_DIR"]) / filename
        if not legacy.is_file():
            abort(404)
        response = send_from_directory(current_app.config["UPLOAD_DIR"], filename)
    # Les noms sont aléatoires et uniques : un nouveau fichier = un nouveau nom, cache long sans risque.
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@bp.route("/robots.txt")
def robots():
    body = "User-agent: *\nDisallow: /admin\nDisallow: /register/done\n"
    return Response(body, mimetype="text/plain")


@bp.route("/healthz")
def healthz():
    get_db().execute("SELECT 1").fetchone()
    return Response("ok", mimetype="text/plain")
