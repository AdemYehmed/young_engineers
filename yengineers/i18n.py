"""Internationalisation : arabe (défaut, RTL), français et anglais (LTR)."""
import json
from pathlib import Path

from flask import g, session

LANGS = ("ar", "fr", "en")
DEFAULT_LANG = "ar"
DIRECTIONS = {"ar": "rtl", "fr": "ltr", "en": "ltr"}
NATIVE_NAMES = {"ar": "العربية", "fr": "Français", "en": "English"}

_DIR = Path(__file__).resolve().parent / "translations"
_cache = {}


def load(lang):
    if lang not in _cache:
        with open(_DIR / f"{lang}.json", encoding="utf-8") as fh:
            _cache[lang] = json.load(fh)
    return _cache[lang]


def translate(lang, key, **kwargs):
    text = load(lang).get(key)
    if text is None:
        text = load(DEFAULT_LANG).get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def current_lang():
    lang = getattr(g, "lang", None)
    return lang if lang in LANGS else DEFAULT_LANG


def t(key, **kwargs):
    return translate(current_lang(), key, **kwargs)


def pick(row, field, lang=None):
    """Valeur localisée d'une ligne SQL (field_ar / field_fr / field_en)."""
    lang = lang or current_lang()
    try:
        value = row[f"{field}_{lang}"]
    except (KeyError, IndexError):
        value = ""
    if not value:
        try:
            value = row[f"{field}_{DEFAULT_LANG}"]
        except (KeyError, IndexError):
            value = ""
    return value or ""


def init_app(app):
    @app.before_request
    def _set_language():
        lang = session.get("lang", DEFAULT_LANG)
        g.lang = lang if lang in LANGS else DEFAULT_LANG

    @app.context_processor
    def _inject():
        lang = current_lang()
        return {
            "t": t,
            "lang": lang,
            "text_dir": DIRECTIONS[lang],
            "LANGS": LANGS,
            "NATIVE_NAMES": NATIVE_NAMES,
            "pick": pick,
        }
