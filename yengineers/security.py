"""Sécurité : CSRF, limitation de tentatives, en-têtes HTTP, mots de passe."""
import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import urlsplit

from flask import abort, current_app, request, session
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .db import get_db

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ----------------------------------------------------------------- CSRF
def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def rotate_csrf():
    session["_csrf"] = secrets.token_urlsafe(32)


def csrf_protect():
    """before_request : toute requête qui modifie des données doit porter le jeton."""
    if request.method in SAFE_METHODS:
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken") or ""
    expected = session.get("_csrf") or ""
    if not sent or not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="csrf")


# ----------------------------------------------------- limitation de débit
def proxy_secret_ok():
    """Vrai si la requête porte le secret partagé que Netlify ajoute à chaque requête proxifiée."""
    secret = current_app.config.get("PROXY_SHARED_SECRET")
    sent = request.headers.get("X-Proxy-Secret", "")
    return bool(secret) and hmac.compare_digest(sent, secret)


def enforce_proxy_secret():
    """before_request : si un secret est configuré, seul le front Netlify peut joindre l'application."""
    if current_app.config.get("PROXY_SHARED_SECRET") and request.path != "/healthz" \
            and not proxy_secret_ok():
        abort(403)


def visitor_ip(req=None):
    """IP du visiteur. L'en-tête personnalisé n'est cru que s'il porte le secret du proxy."""
    req = req or request
    header = current_app.config.get("CLIENT_IP_HEADER")
    if header and proxy_secret_ok():
        value = req.headers.get(header, "").split(",")[0].strip()
        if value:
            return value
    return req.remote_addr or "unknown"


def client_key(request_obj=None):
    """Condensé HMAC de l'IP : on ne stocke jamais l'adresse IP en clair."""
    ip = visitor_ip(request_obj)
    return hmac.new(
        current_app.config["SECRET_KEY"].encode(), ip.encode(), hashlib.sha256
    ).hexdigest()[:24]


def key_for(value):
    return hmac.new(
        current_app.config["SECRET_KEY"].encode(), value.lower().encode(), hashlib.sha256
    ).hexdigest()[:24]


def rate_count(kind, key, window_seconds):
    row = get_db().execute(
        "SELECT COUNT(*) AS n FROM rate_events WHERE kind = ? AND key = ? AND created_at > ?",
        (kind, key, time.time() - window_seconds),
    ).fetchone()
    return row["n"]


def rate_add(kind, key):
    db = get_db()
    with db:
        db.execute(
            "INSERT INTO rate_events(kind, key, created_at) VALUES (?,?,?)",
            (kind, key, time.time()),
        )
        # Nettoyage opportuniste des événements de plus de 24 h
        db.execute("DELETE FROM rate_events WHERE created_at < ?", (time.time() - 86400,))


def rate_clear(kind, key):
    db = get_db()
    with db:
        db.execute("DELETE FROM rate_events WHERE kind = ? AND key = ?", (kind, key))


# ------------------------------------------- jeton temporel du formulaire
def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="ye-form-timer")


def make_form_token():
    return _serializer().dumps({"t": int(time.time())})


def form_token_age(token, max_age=7200):
    """Âge en secondes du formulaire, ou None si le jeton est invalide/expiré."""
    try:
        data, ts = _serializer().loads(token or "", max_age=max_age, return_timestamp=True)
    except BadSignature:
        return None
    return max(0.0, time.time() - ts.timestamp())


# --------------------------------------------------------------- divers
def safe_next(target, prefix="/admin"):
    """Empêche les redirections ouvertes : on n'accepte que des chemins internes."""
    if not target or not isinstance(target, str):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith(prefix) or target.startswith("//"):
        return None
    if "\\" in target or re.search(r"[\r\n]", target):
        return None
    return target


def apply_security_headers(response):
    csp = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    response.headers.setdefault("Content-Security-Policy", csp)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if current_app.config.get("PRODUCTION"):
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    path = request.path
    if path.startswith("/admin") or path.startswith("/register"):
        response.headers["Cache-Control"] = "no-store"
    elif response.mimetype == "text/html":
        # Pages dépendant de la langue (cookie) : jamais mises en cache par un CDN (Netlify)
        response.headers.setdefault("Cache-Control", "no-store")
    return response
