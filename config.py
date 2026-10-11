"""Configuration centralisée du site Young Engineers.

Toutes les valeurs sensibles viennent de variables d'environnement
(fichier .env en local). Aucun secret n'est codé en dur.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PLACEHOLDER_SECRETS = {"", "change-me", "changeme", "change-me-with-a-long-random-value"}


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "oui"}


def _int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _dev_secret(instance_dir: Path) -> str:
    """Clé de développement persistée localement (jamais utilisée en production)."""
    instance_dir.mkdir(parents=True, exist_ok=True)
    path = instance_dir / ".dev_secret_key"
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    value = secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value


def build_config(env=None):
    """Construit le dictionnaire de configuration à partir de l'environnement."""
    env = os.environ if env is None else env
    mode = (env.get("YE_ENV") or "development").strip().lower()
    production = mode == "production"

    instance_dir = Path(env.get("YE_INSTANCE_DIR") or (BASE_DIR / "instance"))
    max_upload_mb = max(1, _int(env.get("MAX_UPLOAD_MB"), 3))
    database_url = (env.get("DATABASE_URL") or "").strip()
    if database_url.startswith(("postgres://", "postgresql://")):
        db_target, db_kind = database_url, "postgres"
    elif database_url:
        raise RuntimeError("DATABASE_URL doit commencer par postgresql:// (ou être vide pour SQLite).")
    else:
        db_target, db_kind = env.get("DATABASE_PATH") or str(instance_dir / "young_engineers.db"), "sqlite"
    if production and env.get("RENDER") and db_kind == "sqlite":
        raise RuntimeError(
            "Sur Render, le disque est effacé à chaque redémarrage : définissez DATABASE_URL (PostgreSQL)."
        )

    secret = (env.get("SECRET_KEY") or "").strip()
    if production:
        if secret in PLACEHOLDER_SECRETS or len(secret) < 32:
            raise RuntimeError(
                "Production : SECRET_KEY doit être défini (32 caractères minimum). "
                "Générez-en une avec : python3 -c 'import secrets; print(secrets.token_hex(32))'"
            )
        cookie_secure = _bool(env.get("SESSION_COOKIE_SECURE"), True)
        if not cookie_secure:
            raise RuntimeError(
                "Production : SESSION_COOKIE_SECURE doit rester activé (HTTPS obligatoire)."
            )
    else:
        if secret in PLACEHOLDER_SECRETS:
            secret = _dev_secret(instance_dir)
        cookie_secure = _bool(env.get("SESSION_COOKIE_SECURE"), False)

    return {
        "YE_ENV": mode,
        "PRODUCTION": production,
        "SECRET_KEY": secret,
        "INSTANCE_DIR": str(instance_dir),
        # Base de données : SQLite par défaut. Pour une base distante ultérieure,
        # il suffit de remplacer la couche yengineers/db.py (voir README).
        "DATABASE": db_target,
        "DB_KIND": db_kind,
        "UPLOAD_DIR": env.get("UPLOAD_DIR") or str(instance_dir / "uploads"),
        "BACKUP_DIR": env.get("BACKUP_DIR") or str(instance_dir / "backups"),
        "MAX_UPLOAD_MB": max_upload_mb,
        "MAX_CONTENT_LENGTH": (max_upload_mb + 1) * 1024 * 1024,
        # Sessions / cookies
        "SESSION_COOKIE_NAME": "ye_session",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": cookie_secure,
        "ADMIN_SESSION_MINUTES": _int(env.get("ADMIN_SESSION_MINUTES"), 120),
        # Limitation des tentatives
        "LOGIN_MAX_ATTEMPTS": _int(env.get("LOGIN_MAX_ATTEMPTS"), 5),
        "LOGIN_WINDOW_MINUTES": _int(env.get("LOGIN_WINDOW_MINUTES"), 15),
        "REGISTER_MAX_PER_HOUR": _int(env.get("REGISTER_MAX_PER_HOUR"), 10),
        "MIN_FORM_SECONDS": _int(env.get("MIN_FORM_SECONDS"), 3),
        # Compte administrateur créé au premier démarrage si aucun n'existe (hébergeur sans terminal)
        "BOOTSTRAP_ADMIN_USERNAME": (env.get("BOOTSTRAP_ADMIN_USERNAME") or "").strip(),
        "BOOTSTRAP_ADMIN_PASSWORD_HASH": (env.get("BOOTSTRAP_ADMIN_PASSWORD_HASH") or "").strip(),
        # Front Netlify devant Render : secret partagé et en-tête portant l'IP réelle du visiteur
        "PROXY_SHARED_SECRET": (env.get("PROXY_SHARED_SECRET") or "").strip(),
        "CLIENT_IP_HEADER": (env.get("CLIENT_IP_HEADER") or "").strip(),
        # Derrière un reverse proxy (nginx, Caddy) : nombre de proxys de confiance
        "TRUST_PROXY": _int(env.get("TRUST_PROXY"), 0),
        # Tunisie : UTC+1 toute l'année (pas d'heure d'été)
        "LOCAL_UTC_OFFSET_HOURS": _int(env.get("LOCAL_UTC_OFFSET_HOURS"), 1),
        "PAGE_SIZE": 25,
        "TESTING": False,
    }
