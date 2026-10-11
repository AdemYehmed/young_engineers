"""Validation et enregistrement des préinscriptions."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta

from ..db import IntegrityErrors

INTERESTS = ("robotics", "programming", "electronics", "projects")
LEVELS = ("beginner", "intermediate", "advanced")
LANG_CHOICES = ("ar", "fr", "en")
STATUSES = ("new", "contacted", "waiting", "archived")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 .\-()]{6,24}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sans caractères ambigus (0/O, 1/I/L)


def clean_text(value, multiline=False):
    value = CONTROL_RE.sub("", (value or "").replace("\r\n", "\n").replace("\r", "\n"))
    if not multiline:
        value = " ".join(value.split())
    return value.strip()


def validate(form, *, require_consent=True):
    """Retourne (données nettoyées, erreurs). Erreurs = {champ: (clé_message, paramètres)}."""
    errors = {}
    data = {}

    def text_field(name, minimum, maximum):
        value = clean_text(form.get(name))
        if not value:
            errors[name] = ("err.required", {})
        elif len(value) < minimum:
            errors[name] = ("err.too_short", {"n": minimum})
        elif len(value) > maximum:
            errors[name] = ("err.too_long", {"n": maximum})
        data[name] = value

    text_field("parent_name", 2, 100)
    text_field("youth_first_name", 2, 60)

    raw_age = clean_text(form.get("age"))
    try:
        age = int(raw_age)
        if not 13 <= age <= 18:
            raise ValueError
        data["age"] = age
    except ValueError:
        data["age"] = raw_age
        errors["age"] = ("err.age", {})

    phone = clean_text(form.get("phone"))
    digits = re.sub(r"\D", "", phone)
    if not phone:
        errors["phone"] = ("err.required", {})
    elif not PHONE_RE.match(phone) or not 8 <= len(digits) <= 15:
        errors["phone"] = ("err.phone", {})
    data["phone"] = phone

    email = clean_text(form.get("email")).lower()
    if not email:
        errors["email"] = ("err.required", {})
    elif len(email) > 254 or not EMAIL_RE.match(email):
        errors["email"] = ("err.email", {})
    data["email"] = email

    language = clean_text(form.get("preferred_language"))
    if language not in LANG_CHOICES:
        errors["preferred_language"] = ("err.language", {})
    data["preferred_language"] = language

    # Liste blanche : toute valeur inconnue est ignorée
    interests = [i for i in INTERESTS if i in set(form.getlist("interests"))]
    if not interests:
        errors["interests"] = ("err.interests", {})
    data["interests"] = interests

    level = clean_text(form.get("experience_level"))
    if level not in LEVELS:
        errors["experience_level"] = ("err.level", {})
    data["experience_level"] = level

    message = clean_text(form.get("message"), multiline=True)
    if len(message) > 1000:
        errors["message"] = ("err.too_long", {"n": 1000})
    data["message"] = message

    if require_consent:
        data["consent"] = form.get("consent") in ("1", "on", "true", "yes")
        if not data["consent"]:
            errors["consent"] = ("err.consent", {})

    return data, errors


def dedupe_hash(email, first_name):
    raw = f"{email.strip().lower()}|{first_name.strip().casefold()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_reference():
    return "YE-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(8))


class DuplicateRegistration(Exception):
    pass


def create_registration(db, data):
    """Insère une préinscription dans une transaction. Retourne la référence."""
    digest = dedupe_hash(data["email"], data["youth_first_name"])
    for _attempt in range(5):
        reference = new_reference()
        try:
            with db:  # commit si OK, rollback si exception
                if db.execute(
                    "SELECT 1 FROM registrations WHERE dedupe_hash = ?", (digest,)
                ).fetchone():
                    raise DuplicateRegistration()
                new_id = db.insert(
                    """INSERT INTO registrations
                       (reference, parent_name, youth_first_name, age, phone, email,
                        preferred_language, experience_level, message, consent,
                        consent_at, dedupe_hash)
                       VALUES (?,?,?,?,?,?,?,?,?,1,datetime('now'),?)""",
                    (reference, data["parent_name"], data["youth_first_name"], data["age"],
                     data["phone"], data["email"], data["preferred_language"],
                     data["experience_level"], data["message"], digest),
                )
                db.executemany(
                    "INSERT INTO registration_interests(registration_id, interest) VALUES (?,?)",
                    [(new_id, i) for i in data["interests"]],
                )
            return reference
        except IntegrityErrors as exc:
            message = str(exc)
            if "dedupe_hash" in message:
                raise DuplicateRegistration() from exc
            if "reference" in message:
                continue  # collision de référence (très improbable) : on retente
            raise
    raise RuntimeError("Impossible de générer une référence unique.")


def update_registration(db, reg_id, data, status, admin_note):
    """Mise à jour par l'administrateur (transaction)."""
    digest = dedupe_hash(data["email"], data["youth_first_name"])
    with db:
        db.execute(
            """UPDATE registrations SET parent_name=?, youth_first_name=?, age=?, phone=?,
               email=?, preferred_language=?, experience_level=?, message=?, status=?,
               admin_note=?, dedupe_hash=?, updated_at=datetime('now') WHERE id=?""",
            (data["parent_name"], data["youth_first_name"], data["age"], data["phone"],
             data["email"], data["preferred_language"], data["experience_level"],
             data["message"], status, admin_note, digest, reg_id),
        )
        db.execute("DELETE FROM registration_interests WHERE registration_id = ?", (reg_id,))
        db.executemany(
            "INSERT INTO registration_interests(registration_id, interest) VALUES (?,?)",
            [(reg_id, i) for i in data["interests"]],
        )


# ---------------------------------------------------------------- requêtes admin
def _like(term):
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def build_filters(args, offset_hours=1):
    """Construit la clause WHERE (requêtes paramétrées uniquement)."""
    where, params = [], []
    q = clean_text(args.get("q"))
    if q:
        like = _like(q)
        where.append(
            "(r.parent_name LIKE ? ESCAPE '\\' OR r.youth_first_name LIKE ? ESCAPE '\\' "
            "OR r.email LIKE ? ESCAPE '\\' OR r.phone LIKE ? ESCAPE '\\' "
            "OR r.reference LIKE ? ESCAPE '\\')"
        )
        params += [like] * 5
    age = clean_text(args.get("age"))
    if age.isdigit() and 13 <= int(age) <= 18:
        where.append("r.age = ?")
        params.append(int(age))
    interest = clean_text(args.get("interest"))
    if interest in INTERESTS:
        where.append(
            "EXISTS (SELECT 1 FROM registration_interests ri "
            "WHERE ri.registration_id = r.id AND ri.interest = ?)"
        )
        params.append(interest)
    status = clean_text(args.get("status"))
    if status in STATUSES:
        where.append("r.status = ?")
        params.append(status)
    for arg, op in (("date_from", ">="), ("date_to", "<")):
        value = clean_text(args.get(arg))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                start = datetime.strptime(value, "%Y-%m-%d") - timedelta(hours=int(offset_hours))
            except ValueError:
                continue
            bound = start if arg == "date_from" else start + timedelta(days=1)
            where.append(f"r.created_at {op} ?")
            params.append(bound.strftime("%Y-%m-%d %H:%M:%S"))
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return clause, params


INTEREST_AGG = (
    "(SELECT group_concat(interest, ',') FROM registration_interests ri "
    "WHERE ri.registration_id = r.id) AS interests"
)


def list_registrations(db, args, page, page_size, offset_hours=1):
    clause, params = build_filters(args, offset_hours)
    total = db.execute(f"SELECT COUNT(*) AS n FROM registrations r {clause}", params).fetchone()["n"]
    rows = db.execute(
        f"SELECT r.*, {INTEREST_AGG} FROM registrations r {clause} "
        "ORDER BY r.created_at DESC, r.id DESC LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    return rows, total


def dashboard_stats(db):
    one = lambda sql: db.execute(sql).fetchone()[0]  # noqa: E731
    total = one("SELECT COUNT(*) FROM registrations")
    cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    recent = db.execute("SELECT COUNT(*) FROM registrations WHERE created_at >= ?", (cutoff,)).fetchone()[0]
    by_status = {s: 0 for s in STATUSES}
    for r in db.execute("SELECT status, COUNT(*) AS n FROM registrations GROUP BY status"):
        by_status[r["status"]] = r["n"]
    by_age = {a: 0 for a in range(13, 19)}
    for r in db.execute("SELECT age, COUNT(*) AS n FROM registrations GROUP BY age"):
        by_age[r["age"]] = r["n"]
    by_interest = {i: 0 for i in INTERESTS}
    for r in db.execute(
        "SELECT interest, COUNT(*) AS n FROM registration_interests GROUP BY interest"
    ):
        by_interest[r["interest"]] = r["n"]
    by_level = {lv: 0 for lv in LEVELS}
    for r in db.execute("SELECT experience_level, COUNT(*) AS n FROM registrations GROUP BY 1"):
        by_level[r["experience_level"]] = r["n"]
    latest = db.execute(
        f"SELECT r.*, {INTEREST_AGG} FROM registrations r ORDER BY r.created_at DESC, r.id DESC LIMIT 8"
    ).fetchall()
    return {"total": total, "recent": recent, "by_status": by_status, "by_age": by_age,
            "by_interest": by_interest, "by_level": by_level, "latest": latest}


CSV_RISKY = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Neutralise l'injection de formules dans Excel/LibreOffice."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(CSV_RISKY) else text
