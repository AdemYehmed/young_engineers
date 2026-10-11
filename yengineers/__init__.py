"""Application Flask Young Engineers (fabrique d'application)."""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import build_config

from . import db as database
from . import i18n, security
from .services.settings import setting


def create_app(test_config=None):
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
        instance_path=None,
    )
    app.config.update(build_config())
    if test_config:
        app.config.update(test_config)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=app.config["ADMIN_SESSION_MINUTES"])
    app.json.ensure_ascii = False

    if app.config["TRUST_PROXY"] > 0:
        n = app.config["TRUST_PROXY"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    for key in ("INSTANCE_DIR", "BACKUP_DIR"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO if app.config["PRODUCTION"] else logging.DEBUG)

    # Base de données : création automatique des tables au premier lancement.
    # init_db est idempotent : elle n'efface et n'écrase jamais de données.
    bootstrap = None
    if app.config["BOOTSTRAP_ADMIN_USERNAME"] and app.config["BOOTSTRAP_ADMIN_PASSWORD_HASH"]:
        bootstrap = (app.config["BOOTSTRAP_ADMIN_USERNAME"], app.config["BOOTSTRAP_ADMIN_PASSWORD_HASH"])
    database.init_db(app.config["DATABASE"], bootstrap_admin=bootstrap)
    app.teardown_appcontext(database.close_db)

    i18n.init_app(app)
    app.before_request(security.enforce_proxy_secret)
    app.before_request(security.csrf_protect)
    app.after_request(security.apply_security_headers)

    # ---------------------------------------------------------- gabarits
    @app.context_processor
    def _globals():
        logo = setting("logo_file")
        return {
            "csrf_token": security.csrf_token,
            "setting": setting,
            "logo_url": (url_for("public.media", filename=logo) if logo
                         else url_for("static", filename="img/logo.svg")),
            "SOCIALS": [(k, setting(f"social_{k}")) for k in
                        ("facebook", "instagram", "youtube", "tiktok", "linkedin")
                        if setting(f"social_{k}")],
        }

    @app.template_filter("localdt")
    def _localdt(value, fmt="%d/%m/%Y %H:%M"):
        if not value:
            return ""
        try:
            dt = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return str(value)
        return (dt + timedelta(hours=app.config["LOCAL_UTC_OFFSET_HOURS"])).strftime(fmt)

    # ---------------------------------------------------------- routes
    from .routes.admin import bp as admin_bp
    from .routes.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # ---------------------------------------------------------- erreurs
    def render_error(code, key):
        try:
            return render_template("error.html", code=code, message_key=key), code
        except Exception:  # dernier filet de sécurité : jamais de détail technique
            return f"Error {code}", code

    @app.errorhandler(400)
    def _400(_e):
        return render_error(400, "error.400.text")

    @app.errorhandler(403)
    def _403(_e):
        return render_error(403, "error.403.text")

    @app.errorhandler(404)
    def _404(_e):
        return render_error(404, "error.404.text")

    @app.errorhandler(413)
    def _413(_e):
        return render_error(413, "error.413.text")

    @app.errorhandler(429)
    def _429(_e):
        return render_error(429, "error.429.text")

    def _db_error(exc):
        app.logger.exception("Erreur base de données : %s", exc)
        return render_error(500, "error.500.text")

    for exc_class in database.DatabaseErrors:
        app.register_error_handler(exc_class, _db_error)

    @app.errorhandler(Exception)
    def _500(exc):
        if isinstance(exc, HTTPException):
            return render_error(exc.code or 500, "error.500.text")
        app.logger.exception("Erreur non gérée : %s", exc)
        return render_error(500, "error.500.text")

    return app
