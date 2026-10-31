"""Gestion du club : groupes, membres, séances, présences, paiements.

Toutes les fonctions reçoivent la connexion `db` (voir yengineers/db.py) et n'utilisent que du SQL
compatible SQLite et PostgreSQL. Les messages d'erreur sont en français (usage : administration).
"""
import calendar
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from .registrations import EMAIL_RE, PHONE_RE, clean_text

MEMBER_STATUSES = ("active", "paused", "left")
SESSION_STATUSES = ("planned", "done", "cancelled")
ATTENDANCE_STATUSES = ("present", "late", "excused", "absent")
PAYMENT_METHODS = ("cash", "transfer", "other")

MEMBER_LABELS = {"active": "Actif", "paused": "En pause", "left": "Parti"}
SESSION_LABELS = {"planned": "Prévue", "done": "Terminée", "cancelled": "Annulée"}
ATTENDANCE_LABELS = {"present": "Présent", "late": "En retard", "excused": "Excusé", "absent": "Absent"}
METHOD_LABELS = {"cash": "Espèces", "transfer": "Virement", "other": "Autre"}

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_OCCURRENCES = 60
MAX_AMOUNT_MILLIMES = 100_000_000  # 100 000 DT : borne de bon sens contre les fautes de frappe


# ----------------------------------------------------------------- utilitaires
def local_today(offset_hours=1):
    return (datetime.utcnow() + timedelta(hours=int(offset_hours))).date()


def parse_date(value):
    """'YYYY-MM-DD' valide → même chaîne ; sinon None."""
    value = clean_text(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return value


def parse_time(value):
    """'' → '' ; 'HH:MM' valide → même chaîne ; sinon None."""
    value = clean_text(value)
    if not value:
        return ""
    return value if TIME_RE.match(value) else None


def parse_month(value, default=None):
    value = clean_text(value)
    return value if MONTH_RE.match(value) else default


def parse_amount(value, allow_zero=False):
    """'25', '25,5', '25.500', '1 250,000' → millimes (entier). None si invalide."""
    text = clean_text(value).replace(" ", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    millimes = amount * 1000
    if millimes != millimes.to_integral_value() or not millimes.is_finite():
        return None
    millimes = int(millimes)
    if millimes < 0 or (millimes == 0 and not allow_zero) or millimes > MAX_AMOUNT_MILLIMES:
        return None
    return millimes


def format_millimes(millimes):
    """25000 → '25,000' (dinars tunisiens : 3 décimales, espace pour les milliers)."""
    millimes = int(millimes or 0)
    dinars, rest = divmod(abs(millimes), 1000)
    sign = "-" if millimes < 0 else ""
    return f"{sign}{dinars:,}".replace(",", " ") + f",{rest:03d}"


def _int_or_none(value):
    value = clean_text(value)
    return int(value) if value.isdigit() else None


# ----------------------------------------------------------------- groupes
def list_groups(db, active_only=False):
    where = "WHERE g.is_active = 1" if active_only else ""
    return db.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM members m WHERE m.group_id = g.id AND m.status = 'active') "
        f"AS active_members FROM club_groups g {where} ORDER BY g.age_min, g.id").fetchall()


def get_group(db, group_id):
    return db.execute("SELECT * FROM club_groups WHERE id = ?", (group_id,)).fetchone()


def group_for_age(db, age):
    row = db.execute(
        "SELECT id FROM club_groups WHERE is_active = 1 AND age_min <= ? AND age_max >= ? "
        "ORDER BY age_min, id LIMIT 1", (age, age)).fetchone()
    return row["id"] if row else None


def validate_group(db, form, group_id=None):
    errors, data = [], {}
    name = clean_text(form.get("name"))
    if not 2 <= len(name) <= 80:
        errors.append("Le nom du groupe doit contenir entre 2 et 80 caractères.")
    data["name"] = name
    for key, label in (("age_min", "Âge minimum"), ("age_max", "Âge maximum")):
        value = _int_or_none(form.get(key))
        if value is None or not 3 <= value <= 30:
            errors.append(f"{label} : nombre entre 3 et 30.")
        data[key] = value
    if data["age_min"] is not None and data["age_max"] is not None and data["age_min"] > data["age_max"]:
        errors.append("L'âge minimum doit être inférieur ou égal à l'âge maximum.")
    for key, label in (("default_start", "Heure de début"), ("default_end", "Heure de fin")):
        value = parse_time(form.get(key))
        if value is None:
            errors.append(f"{label} : format HH:MM (ex. 09:00).")
            value = ""
        data[key] = value
    if data["default_start"] and data["default_end"] and data["default_end"] <= data["default_start"]:
        errors.append("L'heure de fin doit être après l'heure de début.")
    fee_raw = clean_text(form.get("fee"))
    if fee_raw:
        fee = parse_amount(fee_raw, allow_zero=True)
        if fee is None:
            errors.append("Tarif : montant valide en dinars (ex. 40 ou 40,500).")
        data["fee_millimes"] = fee or 0
    else:
        data["fee_millimes"] = 0
    data["notes"] = clean_text(form.get("notes"), multiline=True)[:1000]
    data["is_active"] = 1 if form.get("is_active") else 0
    if name and not errors:
        other = db.execute("SELECT id FROM club_groups WHERE lower(name) = lower(?)", (name,)).fetchone()
        if other and other["id"] != group_id:
            errors.append("Un groupe porte déjà ce nom.")
    return data, errors


def save_group(db, data, group_id=None):
    with db:
        if group_id is None:
            return db.insert(
                "INSERT INTO club_groups(name, age_min, age_max, default_start, default_end, "
                "fee_millimes, notes, is_active) VALUES (?,?,?,?,?,?,?,?)",
                (data["name"], data["age_min"], data["age_max"], data["default_start"],
                 data["default_end"], data["fee_millimes"], data["notes"], data["is_active"]))
        db.execute(
            "UPDATE club_groups SET name=?, age_min=?, age_max=?, default_start=?, default_end=?, "
            "fee_millimes=?, notes=?, is_active=?, updated_at=datetime('now') WHERE id=?",
            (data["name"], data["age_min"], data["age_max"], data["default_start"], data["default_end"],
             data["fee_millimes"], data["notes"], data["is_active"], group_id))
        return group_id


def delete_group(db, group_id):
    """Retourne None si supprimé, sinon le message d'erreur."""
    if db.execute("SELECT COUNT(*) AS n FROM club_sessions WHERE group_id = ?", (group_id,)).fetchone()["n"]:
        return "Ce groupe a des séances : désactivez-le plutôt que de le supprimer."
    with db:
        db.execute("DELETE FROM club_groups WHERE id = ?", (group_id,))
    return None


# ----------------------------------------------------------------- membres
def validate_member(db, form):
    errors, data = [], {}
    first = clean_text(form.get("first_name"))
    if not 2 <= len(first) <= 60:
        errors.append("Prénom : entre 2 et 60 caractères.")
    data["first_name"] = first
    last = clean_text(form.get("last_name"))
    if len(last) > 60:
        errors.append("Nom : 60 caractères maximum.")
    data["last_name"] = last
    age = _int_or_none(form.get("age"))
    if age is None or not 3 <= age <= 30:
        errors.append("Âge : nombre entre 3 et 30.")
    data["age"] = age
    parent = clean_text(form.get("parent_name"))
    if len(parent) > 100:
        errors.append("Nom du parent : 100 caractères maximum.")
    data["parent_name"] = parent
    phone = clean_text(form.get("phone"))
    if phone and (not PHONE_RE.match(phone) or not 8 <= len(re.sub(r"\D", "", phone)) <= 15):
        errors.append("Téléphone invalide.")
    data["phone"] = phone
    email = clean_text(form.get("email")).lower()
    if email and (len(email) > 254 or not EMAIL_RE.match(email)):
        errors.append("Email invalide.")
    data["email"] = email
    group_raw = clean_text(form.get("group_id"))
    group_id = None
    if group_raw:
        group_id = _int_or_none(group_raw)
        if group_id is None or get_group(db, group_id) is None:
            errors.append("Groupe inconnu.")
            group_id = None
    data["group_id"] = group_id
    status = clean_text(form.get("status")) or "active"
    if status not in MEMBER_STATUSES:
        errors.append("Statut invalide.")
        status = "active"
    data["status"] = status
    joined = clean_text(form.get("joined_on"))
    if joined and parse_date(joined) is None:
        errors.append("Date d'inscription invalide.")
        joined = ""
    data["joined_on"] = joined
    fee_raw = clean_text(form.get("fee_override"))
    if fee_raw:
        fee = parse_amount(fee_raw, allow_zero=True)
        if fee is None:
            errors.append("Tarif particulier : montant valide en dinars.")
        data["fee_override_millimes"] = fee
    else:
        data["fee_override_millimes"] = None
    data["notes"] = clean_text(form.get("notes"), multiline=True)[:2000]
    return data, errors


def get_member(db, member_id):
    return db.execute(
        "SELECT m.*, g.name AS group_name FROM members m "
        "LEFT JOIN club_groups g ON g.id = m.group_id WHERE m.id = ?", (member_id,)).fetchone()


def list_members(db, args):
    where, params = [], []
    q = clean_text(args.get("q"))
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(m.first_name LIKE ? ESCAPE '\\' OR m.last_name LIKE ? ESCAPE '\\' "
                     "OR m.parent_name LIKE ? ESCAPE '\\' OR m.phone LIKE ? ESCAPE '\\')")
        params += [like] * 4
    group = _int_or_none(args.get("group"))
    if group is not None:
        where.append("m.group_id = ?")
        params.append(group)
    elif clean_text(args.get("group")) == "none":
        where.append("m.group_id IS NULL")
    status = clean_text(args.get("status"))
    if status in MEMBER_STATUSES:
        where.append("m.status = ?")
        params.append(status)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return db.execute(
        "SELECT m.*, g.name AS group_name FROM members m "
        f"LEFT JOIN club_groups g ON g.id = m.group_id {clause} "
        "ORDER BY g.age_min, m.first_name, m.last_name, m.id", params).fetchall()


def create_member(db, data, registration_id=None):
    with db:
        return db.insert(
            "INSERT INTO members(registration_id, first_name, last_name, age, parent_name, phone, email, "
            "group_id, status, joined_on, fee_override_millimes, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (registration_id, data["first_name"], data["last_name"], data["age"], data["parent_name"],
             data["phone"], data["email"], data["group_id"], data["status"], data["joined_on"],
             data["fee_override_millimes"], data["notes"]))


def update_member(db, member_id, data):
    with db:
        db.execute(
            "UPDATE members SET first_name=?, last_name=?, age=?, parent_name=?, phone=?, email=?, "
            "group_id=?, status=?, joined_on=?, fee_override_millimes=?, notes=?, "
            "updated_at=datetime('now') WHERE id=?",
            (data["first_name"], data["last_name"], data["age"], data["parent_name"], data["phone"],
             data["email"], data["group_id"], data["status"], data["joined_on"],
             data["fee_override_millimes"], data["notes"], member_id))


def delete_member(db, member_id):
    """None si supprimé ; sinon message d'erreur (les paiements ne sont jamais effacés par accident)."""
    if db.execute("SELECT COUNT(*) AS n FROM payments WHERE member_id = ?", (member_id,)).fetchone()["n"]:
        return "Ce membre a des paiements enregistrés : passez-le au statut « Parti » plutôt que de le supprimer."
    with db:
        db.execute("DELETE FROM members WHERE id = ?", (member_id,))
    return None


def confirm_registration(db, registration_id, offset_hours=1):
    """Confirme une préinscription et crée le membre (groupe choisi selon l'âge).

    Retourne (member_id, created). Idempotent : confirmer deux fois ne crée pas deux membres.
    """
    reg = db.execute("SELECT * FROM registrations WHERE id = ?", (registration_id,)).fetchone()
    if reg is None:
        return None, False
    existing = db.execute("SELECT id FROM members WHERE registration_id = ?", (registration_id,)).fetchone()
    with db:
        db.execute("UPDATE registrations SET status = 'confirmed', updated_at = datetime('now') WHERE id = ?",
                   (registration_id,))
    if existing:
        return existing["id"], False
    data = {
        "first_name": reg["youth_first_name"], "last_name": "", "age": reg["age"],
        "parent_name": reg["parent_name"], "phone": reg["phone"], "email": reg["email"],
        "group_id": group_for_age(db, reg["age"]), "status": "active",
        "joined_on": local_today(offset_hours).isoformat(), "fee_override_millimes": None,
        "notes": "",
    }
    return create_member(db, data, registration_id=registration_id), True


# ----------------------------------------------------------------- séances
def validate_session(db, form):
    errors, data = [], {}
    group_id = _int_or_none(form.get("group_id"))
    group = get_group(db, group_id) if group_id is not None else None
    if group is None:
        errors.append("Choisissez un groupe.")
    data["group_id"] = group_id
    title = clean_text(form.get("title"))
    if len(title) > 120:
        errors.append("Titre : 120 caractères maximum.")
    data["title"] = title
    session_date = parse_date(form.get("session_date"))
    if session_date is None:
        errors.append("Date de séance invalide (format AAAA-MM-JJ).")
    data["session_date"] = session_date
    start, end = parse_time(form.get("start_time")), parse_time(form.get("end_time"))
    if start is None or end is None:
        errors.append("Heures : format HH:MM (ex. 09:00).")
        start, end = start or "", end or ""
    if group is not None and not start and not end:  # horaires par défaut du groupe
        start, end = group["default_start"], group["default_end"]
    if start and end and end <= start:
        errors.append("L'heure de fin doit être après l'heure de début.")
    data["start_time"], data["end_time"] = start, end
    status = clean_text(form.get("status")) or "planned"
    if status not in SESSION_STATUSES:
        errors.append("Statut de séance invalide.")
        status = "planned"
    data["status"] = status
    data["location"] = clean_text(form.get("location"))[:200]
    data["comment"] = clean_text(form.get("comment"), multiline=True)[:4000]
    repeat = clean_text(form.get("repeat_until"))
    data["repeat_until"] = None
    if repeat:
        repeat_date = parse_date(repeat)
        if repeat_date is None:
            errors.append("Date de fin de répétition invalide.")
        elif session_date and repeat_date < session_date:
            errors.append("La répétition doit se terminer après la première séance.")
        else:
            data["repeat_until"] = repeat_date
    return data, errors


def occurrence_dates(first_date, repeat_until):
    """Dates hebdomadaires de first_date à repeat_until inclus (maximum MAX_OCCURRENCES)."""
    current = datetime.strptime(first_date, "%Y-%m-%d").date()
    last = datetime.strptime(repeat_until, "%Y-%m-%d").date() if repeat_until else current
    dates = []
    while current <= last and len(dates) < MAX_OCCURRENCES:
        dates.append(current.isoformat())
        current += timedelta(days=7)
    return dates


def create_sessions(db, data):
    ids = []
    with db:
        for day in occurrence_dates(data["session_date"], data["repeat_until"]):
            ids.append(db.insert(
                "INSERT INTO club_sessions(group_id, title, session_date, start_time, end_time, status, "
                "location, comment) VALUES (?,?,?,?,?,?,?,?)",
                (data["group_id"], data["title"], day, data["start_time"], data["end_time"],
                 data["status"], data["location"], data["comment"])))
    return ids


def update_session(db, session_id, data):
    with db:
        db.execute(
            "UPDATE club_sessions SET group_id=?, title=?, session_date=?, start_time=?, end_time=?, "
            "status=?, location=?, comment=?, updated_at=datetime('now') WHERE id=?",
            (data["group_id"], data["title"], data["session_date"], data["start_time"], data["end_time"],
             data["status"], data["location"], data["comment"], session_id))


def delete_session(db, session_id):
    with db:
        db.execute("DELETE FROM club_sessions WHERE id = ?", (session_id,))


_SESSION_SELECT = (
    "SELECT s.*, g.name AS group_name, "
    "(SELECT COUNT(*) FROM attendance a WHERE a.session_id = s.id AND a.status IN ('present','late')) AS present_count, "
    "(SELECT COUNT(*) FROM attendance a WHERE a.session_id = s.id) AS marked_count "
    "FROM club_sessions s JOIN club_groups g ON g.id = s.group_id"
)


def get_session(db, session_id):
    return db.execute(_SESSION_SELECT + " WHERE s.id = ?", (session_id,)).fetchone()


def list_sessions(db, args, today=None):
    where, params = [], []
    group = _int_or_none(args.get("group"))
    if group is not None:
        where.append("s.group_id = ?")
        params.append(group)
    status = clean_text(args.get("status"))
    if status in SESSION_STATUSES:
        where.append("s.status = ?")
        params.append(status)
    when = clean_text(args.get("when"))
    if today and when == "upcoming":
        where.append("s.session_date >= ?")
        params.append(today)
    elif today and when == "past":
        where.append("s.session_date < ?")
        params.append(today)
    for arg, op in (("date_from", ">="), ("date_to", "<=")):
        value = parse_date(args.get(arg))
        if value:
            where.append(f"s.session_date {op} ?")
            params.append(value)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    order = "ASC" if when == "upcoming" else "DESC"
    return db.execute(
        f"{_SESSION_SELECT} {clause} ORDER BY s.session_date {order}, s.start_time {order}, s.id {order} LIMIT 300",
        params).fetchall()


def month_calendar(db, year, month, group_id=None):
    """Grille du mois (semaines du lundi au dimanche) avec les séances de chaque jour."""
    weeks_dates = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    first, last = weeks_dates[0][0], weeks_dates[-1][-1]
    params = [first.isoformat(), last.isoformat()]
    extra = ""
    if group_id is not None:
        extra = " AND s.group_id = ?"
        params.append(group_id)
    rows = db.execute(
        f"{_SESSION_SELECT} WHERE s.session_date >= ? AND s.session_date <= ?{extra} "
        "ORDER BY s.session_date, s.start_time, s.id", params).fetchall()
    by_day = {}
    for r in rows:
        by_day.setdefault(r["session_date"], []).append(r)
    return [[{"date": d, "iso": d.isoformat(), "in_month": d.month == month,
              "sessions": by_day.get(d.isoformat(), [])} for d in week] for week in weeks_dates]


def shift_month(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


# ----------------------------------------------------------------- présences
def session_roster(db, session):
    """Membres à pointer : membres actifs du groupe + ceux déjà pointés sur cette séance."""
    return db.execute(
        "SELECT m.*, a.status AS att_status, a.note AS att_note FROM members m "
        "LEFT JOIN attendance a ON a.member_id = m.id AND a.session_id = ? "
        "WHERE (m.group_id = ? AND m.status = 'active') OR a.session_id IS NOT NULL "
        "ORDER BY m.first_name, m.last_name, m.id", (session["id"], session["group_id"])).fetchall()


def save_attendance(db, session, form):
    """Enregistre les présences postées. Sans statut choisi : pas de pointage (ligne supprimée)."""
    roster = session_roster(db, session)
    mark_all = form.get("mark_all") == "present"
    with db:
        for m in roster:
            status = clean_text(form.get(f"status_{m['id']}"))
            if status not in ATTENDANCE_STATUSES:
                status = "present" if mark_all else ""
            note = clean_text(form.get(f"note_{m['id']}"))[:300]
            if not status:
                db.execute("DELETE FROM attendance WHERE session_id = ? AND member_id = ?",
                           (session["id"], m["id"]))
                continue
            db.execute(
                "INSERT INTO attendance(session_id, member_id, status, note) VALUES (?,?,?,?) "
                "ON CONFLICT(session_id, member_id) DO UPDATE SET status = excluded.status, "
                "note = excluded.note, updated_at = datetime('now')",
                (session["id"], m["id"], status, note))
        if form.get("mark_done") and session["status"] == "planned":
            db.execute("UPDATE club_sessions SET status = 'done', updated_at = datetime('now') WHERE id = ?",
                       (session["id"],))
    return len(roster)


def member_attendance(db, member_id, limit=30):
    summary = {s: 0 for s in ATTENDANCE_STATUSES}
    for r in db.execute("SELECT status, COUNT(*) AS n FROM attendance WHERE member_id = ? GROUP BY status",
                        (member_id,)):
        summary[r["status"]] = r["n"]
    rows = db.execute(
        "SELECT a.status, a.note, s.id AS session_id, s.session_date, s.title, g.name AS group_name "
        "FROM attendance a JOIN club_sessions s ON s.id = a.session_id "
        "JOIN club_groups g ON g.id = s.group_id WHERE a.member_id = ? "
        "ORDER BY s.session_date DESC, s.id DESC LIMIT ?", (member_id, limit)).fetchall()
    return summary, rows


# ----------------------------------------------------------------- paiements
def validate_payment(db, form, offset_hours=1):
    errors, data = [], {}
    member_id = _int_or_none(form.get("member_id"))
    if member_id is None or get_member(db, member_id) is None:
        errors.append("Choisissez un membre.")
        member_id = None
    data["member_id"] = member_id
    amount = parse_amount(form.get("amount"))
    if amount is None:
        errors.append("Montant invalide (en dinars, ex. 40 ou 40,500).")
    data["amount_millimes"] = amount
    paid_on = parse_date(form.get("paid_on")) or (
        local_today(offset_hours).isoformat() if not clean_text(form.get("paid_on")) else None)
    if paid_on is None:
        errors.append("Date de paiement invalide.")
    data["paid_on"] = paid_on
    period = clean_text(form.get("period"))
    if period and not MONTH_RE.match(period):
        errors.append("Période invalide (format AAAA-MM).")
        period = ""
    if not period and paid_on:
        period = paid_on[:7]
    data["period"] = period
    method = clean_text(form.get("method")) or "cash"
    if method not in PAYMENT_METHODS:
        errors.append("Mode de paiement invalide.")
        method = "cash"
    data["method"] = method
    data["note"] = clean_text(form.get("note"))[:300]
    return data, errors


def add_payment(db, data):
    with db:
        return db.insert(
            "INSERT INTO payments(member_id, amount_millimes, paid_on, period, method, note) "
            "VALUES (?,?,?,?,?,?)",
            (data["member_id"], data["amount_millimes"], data["paid_on"], data["period"],
             data["method"], data["note"]))


def update_payment(db, payment_id, data):
    with db:
        db.execute("UPDATE payments SET member_id=?, amount_millimes=?, paid_on=?, period=?, method=?, "
                   "note=? WHERE id=?",
                   (data["member_id"], data["amount_millimes"], data["paid_on"], data["period"],
                    data["method"], data["note"], payment_id))


def delete_payment(db, payment_id):
    with db:
        db.execute("DELETE FROM payments WHERE id = ?", (payment_id,))


def get_payment(db, payment_id):
    return db.execute(
        "SELECT p.*, m.first_name, m.last_name FROM payments p JOIN members m ON m.id = p.member_id "
        "WHERE p.id = ?", (payment_id,)).fetchone()


def member_payments(db, member_id):
    rows = db.execute("SELECT * FROM payments WHERE member_id = ? ORDER BY paid_on DESC, id DESC",
                      (member_id,)).fetchall()
    return rows, sum(r["amount_millimes"] for r in rows)


def list_payments(db, period=None, member_id=None, limit=300):
    where, params = [], []
    if period:
        where.append("p.period = ?")
        params.append(period)
    if member_id:
        where.append("p.member_id = ?")
        params.append(member_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return db.execute(
        "SELECT p.*, m.first_name, m.last_name FROM payments p JOIN members m ON m.id = p.member_id "
        f"{clause} ORDER BY p.paid_on DESC, p.id DESC LIMIT ?", params + [limit]).fetchall()


def payment_state(fee, paid):
    """Sans tarif défini (0) : « payé » dès qu'un paiement existe pour la période."""
    if fee > 0:
        if paid >= fee:
            return "paid"
        return "partial" if paid > 0 else "unpaid"
    return "paid" if paid > 0 else "unpaid"


def month_overview(db, period, group_id=None):
    """Situation du mois : pour chaque membre actif, tarif attendu, montant payé, état."""
    params = [period]
    extra = ""
    if group_id is not None:
        extra = " AND m.group_id = ?"
        params.append(group_id)
    rows = db.execute(
        "SELECT m.id, m.first_name, m.last_name, g.name AS group_name, "
        "COALESCE(m.fee_override_millimes, g.fee_millimes, 0) AS fee, "
        "(SELECT COALESCE(SUM(p.amount_millimes), 0) FROM payments p "
        " WHERE p.member_id = m.id AND p.period = ?) AS paid "
        "FROM members m LEFT JOIN club_groups g ON g.id = m.group_id "
        f"WHERE m.status = 'active'{extra} ORDER BY g.age_min, m.first_name, m.last_name, m.id",
        params).fetchall()
    items = []
    for r in rows:
        fee, paid = int(r["fee"]), int(r["paid"])
        items.append({"id": r["id"], "name": f"{r['first_name']} {r['last_name']}".strip(),
                      "group_name": r["group_name"] or "—", "fee": fee, "paid": paid,
                      "state": payment_state(fee, paid)})
    totals = {
        "paid": sum(i["paid"] for i in items),
        "expected": sum(i["fee"] for i in items),
        "unpaid": sum(1 for i in items if i["state"] == "unpaid"),
        "partial": sum(1 for i in items if i["state"] == "partial"),
    }
    return items, totals


# ----------------------------------------------------------------- tableau de bord
def club_summary(db, today_iso, period):
    one = lambda sql, params=(): db.execute(sql, params).fetchone()[0]  # noqa: E731
    active = one("SELECT COUNT(*) FROM members WHERE status = 'active'")
    by_group = db.execute(
        "SELECT g.name, COUNT(m.id) AS n FROM club_groups g "
        "LEFT JOIN members m ON m.group_id = g.id AND m.status = 'active' "
        "WHERE g.is_active = 1 GROUP BY g.id, g.name, g.age_min ORDER BY g.age_min").fetchall()
    upcoming = db.execute(
        f"{_SESSION_SELECT} WHERE s.session_date >= ? AND s.status = 'planned' "
        "ORDER BY s.session_date, s.start_time, s.id LIMIT 5", (today_iso,)).fetchall()
    paid_month = one("SELECT COALESCE(SUM(amount_millimes), 0) FROM payments WHERE period = ?", (period,))
    pending = one("SELECT COUNT(*) FROM registrations WHERE status IN ('new','contacted','waiting')")
    return {"active": active, "by_group": by_group, "upcoming": upcoming,
            "paid_month": int(paid_month), "pending_registrations": pending}
