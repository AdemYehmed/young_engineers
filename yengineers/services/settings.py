"""Accès aux paramètres du site (table site_settings)."""
import re

from flask import g

from ..db import get_db
from ..defaults import DEFAULT_SETTINGS
from ..i18n import DEFAULT_LANG, LANGS, current_lang

URL_RE = re.compile(r"^https://[^\s<>\"']{3,300}$", re.IGNORECASE)

# Champs éditables, regroupés pour le formulaire d'administration.
# type : text | textarea | url | email | int
SETTING_GROUPS = [
    ("Section principale (hero)", [
        ("hero_title", "Titre principal", "text", True),
        ("hero_subtitle", "Sous-titre", "textarea", True),
        ("hero_cta_primary", "Bouton principal", "text", True),
        ("hero_cta_secondary", "Bouton secondaire", "text", True),
        ("launch_notice", "Message sur la date de lancement", "textarea", True),
    ]),
    ("Présentation du club", [
        ("about_title", "Titre de la présentation", "text", True),
        ("about_text", "Texte de présentation", "textarea", True),
    ]),
    ("Section préinscription", [
        ("prereg_title", "Titre", "text", True),
        ("prereg_text", "Texte explicatif", "textarea", True),
    ]),
    ("Coordonnées", [
        ("club_name", "Nom du club", "text", False),
        ("email", "Email de contact", "email", False),
        ("phone", "Téléphone", "text", False),
        ("location", "Ville / localisation affichée", "text", True),
    ]),
    ("Réseaux sociaux (liens https:// — laisser vide pour masquer)", [
        ("social_facebook", "Facebook", "url", False),
        ("social_instagram", "Instagram", "url", False),
        ("social_youtube", "YouTube", "url", False),
        ("social_tiktok", "TikTok", "url", False),
        ("social_linkedin", "LinkedIn", "url", False),
    ]),
    ("Pages légales", [
        ("data_retention_months", "Durée de conservation des données (mois)", "int", False),
        ("legal_extra", "Texte complémentaire des mentions légales (hébergeur, etc.)", "textarea", True),
    ]),
]


def all_settings():
    if "settings" not in g:
        rows = get_db().execute("SELECT key, value FROM site_settings").fetchall()
        merged = dict(DEFAULT_SETTINGS)
        merged.update({r["key"]: r["value"] for r in rows})
        g.settings = merged
    return g.settings


def setting(key, lang=None):
    """Valeur d'un paramètre. Si `key` est traduisible, renvoie la langue courante."""
    values = all_settings()
    if key in values:
        return values[key]
    lang = lang or current_lang()
    value = values.get(f"{key}_{lang}")
    if value is None:  # clé absente seulement : une valeur vide reste vide (pas de mélange de langues)
        value = values.get(f"{key}_{DEFAULT_LANG}", "")
    return value


def validate_and_collect(form):
    """Retourne (valeurs à enregistrer, erreurs)."""
    values, errors = {}, []
    for _group, fields in SETTING_GROUPS:
        for key, label, kind, translatable in fields:
            names = [f"{key}_{lg}" for lg in LANGS] if translatable else [key]
            for name in names:
                raw = " ".join((form.get(name) or "").split()) if kind != "textarea" \
                    else (form.get(name) or "").replace("\r\n", "\n").strip()
                suffix = f" ({name[-2:].upper()})" if translatable else ""
                if len(raw) > 2000:
                    errors.append(f"{label}{suffix} : texte trop long.")
                    continue
                if kind == "url" and raw and not URL_RE.match(raw):
                    errors.append(f"{label} : saisissez une adresse commençant par https://")
                    continue
                if kind == "email" and raw and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", raw):
                    errors.append(f"{label} : adresse email invalide.")
                    continue
                if kind == "int":
                    if not raw.isdigit() or not 1 <= int(raw) <= 120:
                        errors.append(f"{label} : nombre entre 1 et 120.")
                        continue
                required = key in {"club_name", "email"} or (
                    translatable and key not in {"legal_extra", "launch_notice"}
                )
                if required and not raw:
                    errors.append(f"{label}{suffix} : champ obligatoire.")
                    continue
                values[name] = raw
    return values, errors


def save_settings(values):
    db = get_db()
    with db:
        for key, value in values.items():
            db.execute(
                "INSERT INTO site_settings(key, value, updated_at) VALUES (?,?,datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value),
            )
    g.pop("settings", None)
