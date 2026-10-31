"""Couche d'accès aux données : SQLite (local) ou PostgreSQL (Render), même code applicatif.

Le choix se fait avec la variable DATABASE_URL (postgresql://...). Sans elle, SQLite est utilisé.
Les requêtes de l'application sont écrites avec des `?` et quelques fonctions SQLite
(datetime('now'), group_concat) : pour PostgreSQL, `translate_sql()` les convertit.
"""
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

from .defaults import DEFAULT_ACTIVITIES, DEFAULT_FAQS, DEFAULT_SETTINGS
from .text_migrations import TEXT_MIGRATIONS

try:  # PostgreSQL est optionnel : seulement nécessaire si DATABASE_URL est défini
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

SCHEMA_VERSION = 3

IntegrityErrors = (sqlite3.IntegrityError,) + ((psycopg.errors.IntegrityError,) if psycopg else ())
DatabaseErrors = (sqlite3.Error,) + ((psycopg.Error,) if psycopg else ())

# Jetons remplacés selon le moteur : {pk} {now} {real} {blob}
SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id            {pk},
    username      TEXT NOT NULL CHECK (length(username) BETWEEN 3 AND 64),
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT {now},
    last_login_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_admins_username ON admins (lower(username));

CREATE TABLE IF NOT EXISTS registrations (
    id                 {pk},
    reference          TEXT NOT NULL UNIQUE,
    parent_name        TEXT NOT NULL CHECK (length(parent_name) BETWEEN 2 AND 100),
    youth_first_name   TEXT NOT NULL CHECK (length(youth_first_name) BETWEEN 2 AND 60),
    age                INTEGER NOT NULL CHECK (age BETWEEN 7 AND 18),
    phone              TEXT NOT NULL,
    email              TEXT NOT NULL,
    preferred_language TEXT NOT NULL CHECK (preferred_language IN ('ar','fr','en')),
    experience_level   TEXT NOT NULL CHECK (experience_level IN ('beginner','intermediate','advanced')),
    message            TEXT NOT NULL DEFAULT '',
    consent            INTEGER NOT NULL CHECK (consent = 1),
    consent_at         TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'new'
                       CHECK (status IN ('new','contacted','waiting','confirmed','archived')),
    admin_note         TEXT NOT NULL DEFAULT '',
    dedupe_hash        TEXT NOT NULL UNIQUE,
    created_at         TEXT NOT NULL DEFAULT {now},
    updated_at         TEXT NOT NULL DEFAULT {now}
);
CREATE INDEX IF NOT EXISTS idx_registrations_created ON registrations(created_at);
CREATE INDEX IF NOT EXISTS idx_registrations_status  ON registrations(status);
CREATE INDEX IF NOT EXISTS idx_registrations_age     ON registrations(age);

CREATE TABLE IF NOT EXISTS registration_interests (
    registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
    interest        TEXT NOT NULL
                    CHECK (interest IN ('robotics','programming','electronics','projects')),
    PRIMARY KEY (registration_id, interest)
);

CREATE TABLE IF NOT EXISTS activities (
    id             {pk},
    title_ar       TEXT NOT NULL,
    title_fr       TEXT NOT NULL,
    title_en       TEXT NOT NULL,
    description_ar TEXT NOT NULL DEFAULT '',
    description_fr TEXT NOT NULL DEFAULT '',
    description_en TEXT NOT NULL DEFAULT '',
    icon           TEXT NOT NULL DEFAULT 'robot',
    image          TEXT NOT NULL DEFAULT '',
    sort_order     INTEGER NOT NULL DEFAULT 0,
    is_published   INTEGER NOT NULL DEFAULT 1 CHECK (is_published IN (0,1)),
    created_at     TEXT NOT NULL DEFAULT {now},
    updated_at     TEXT NOT NULL DEFAULT {now}
);

CREATE TABLE IF NOT EXISTS faqs (
    id           {pk},
    question_ar  TEXT NOT NULL,
    question_fr  TEXT NOT NULL,
    question_en  TEXT NOT NULL,
    answer_ar    TEXT NOT NULL,
    answer_fr    TEXT NOT NULL,
    answer_en    TEXT NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_published INTEGER NOT NULL DEFAULT 1 CHECK (is_published IN (0,1)),
    created_at   TEXT NOT NULL DEFAULT {now},
    updated_at   TEXT NOT NULL DEFAULT {now}
);

CREATE TABLE IF NOT EXISTS site_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT {now}
);

CREATE TABLE IF NOT EXISTS media (
    name       TEXT PRIMARY KEY,
    mimetype   TEXT NOT NULL,
    data       {blob} NOT NULL,
    created_at TEXT NOT NULL DEFAULT {now}
);

CREATE TABLE IF NOT EXISTS club_groups (
    id             {pk},
    name           TEXT NOT NULL UNIQUE CHECK (length(name) BETWEEN 2 AND 80),
    age_min        INTEGER NOT NULL CHECK (age_min BETWEEN 3 AND 30),
    age_max        INTEGER NOT NULL CHECK (age_max BETWEEN 3 AND 30),
    default_start  TEXT NOT NULL DEFAULT '',
    default_end    TEXT NOT NULL DEFAULT '',
    fee_millimes   INTEGER NOT NULL DEFAULT 0 CHECK (fee_millimes >= 0),
    notes          TEXT NOT NULL DEFAULT '',
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at     TEXT NOT NULL DEFAULT {now},
    updated_at     TEXT NOT NULL DEFAULT {now}
);

CREATE TABLE IF NOT EXISTS members (
    id                   {pk},
    registration_id      INTEGER UNIQUE REFERENCES registrations(id) ON DELETE SET NULL,
    first_name           TEXT NOT NULL CHECK (length(first_name) BETWEEN 2 AND 60),
    last_name            TEXT NOT NULL DEFAULT '',
    age                  INTEGER NOT NULL CHECK (age BETWEEN 3 AND 30),
    parent_name          TEXT NOT NULL DEFAULT '',
    phone                TEXT NOT NULL DEFAULT '',
    email                TEXT NOT NULL DEFAULT '',
    group_id             INTEGER REFERENCES club_groups(id) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','left')),
    joined_on            TEXT NOT NULL DEFAULT '',
    fee_override_millimes INTEGER CHECK (fee_override_millimes IS NULL OR fee_override_millimes >= 0),
    notes                TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL DEFAULT {now},
    updated_at           TEXT NOT NULL DEFAULT {now}
);
CREATE INDEX IF NOT EXISTS idx_members_group  ON members(group_id);
CREATE INDEX IF NOT EXISTS idx_members_status ON members(status);

CREATE TABLE IF NOT EXISTS club_sessions (
    id           {pk},
    group_id     INTEGER NOT NULL REFERENCES club_groups(id) ON DELETE RESTRICT,
    title        TEXT NOT NULL DEFAULT '',
    session_date TEXT NOT NULL,
    start_time   TEXT NOT NULL DEFAULT '',
    end_time     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','done','cancelled')),
    location     TEXT NOT NULL DEFAULT '',
    comment      TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT {now},
    updated_at   TEXT NOT NULL DEFAULT {now}
);
CREATE INDEX IF NOT EXISTS idx_club_sessions_date  ON club_sessions(session_date);
CREATE INDEX IF NOT EXISTS idx_club_sessions_group ON club_sessions(group_id);

CREATE TABLE IF NOT EXISTS attendance (
    session_id INTEGER NOT NULL REFERENCES club_sessions(id) ON DELETE CASCADE,
    member_id  INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    status     TEXT NOT NULL CHECK (status IN ('present','absent','excused','late')),
    note       TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT {now},
    PRIMARY KEY (session_id, member_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id              {pk},
    member_id       INTEGER NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
    amount_millimes INTEGER NOT NULL CHECK (amount_millimes > 0),
    paid_on         TEXT NOT NULL,
    period          TEXT NOT NULL DEFAULT '',
    method          TEXT NOT NULL DEFAULT 'cash' CHECK (method IN ('cash','transfer','other')),
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT {now}
);
CREATE INDEX IF NOT EXISTS idx_payments_member ON payments(member_id);
CREATE INDEX IF NOT EXISTS idx_payments_period ON payments(period);

CREATE TABLE IF NOT EXISTS media_items (
    id                {pk},
    kind              TEXT NOT NULL CHECK (kind IN ('photo','video')),
    filename          TEXT NOT NULL UNIQUE,
    original_name     TEXT NOT NULL DEFAULT '',
    mimetype          TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL DEFAULT 0,
    title             TEXT NOT NULL DEFAULT '',
    caption           TEXT NOT NULL DEFAULT '',
    session_id        INTEGER REFERENCES club_sessions(id) ON DELETE SET NULL,
    is_public         INTEGER NOT NULL DEFAULT 0 CHECK (is_public IN (0,1)),
    consent_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (consent_confirmed IN (0,1)),
    created_at        TEXT NOT NULL DEFAULT {now},
    updated_at        TEXT NOT NULL DEFAULT {now},
    CHECK (is_public = 0 OR consent_confirmed = 1)
);
CREATE INDEX IF NOT EXISTS idx_media_items_public ON media_items(is_public, created_at);

CREATE TABLE IF NOT EXISTS rate_events (
    id         {pk},
    kind       TEXT NOT NULL,
    key        TEXT NOT NULL,
    created_at {real} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_events ON rate_events(kind, key, created_at)
"""

_PG_NOW = "to_char((now() at time zone 'utc'), 'YYYY-MM-DD HH24:MI:SS')"
_TOKENS = {
    "sqlite": {"pk": "INTEGER PRIMARY KEY AUTOINCREMENT", "now": "(datetime('now'))",
               "real": "REAL", "blob": "BLOB"},
    "postgres": {"pk": "SERIAL PRIMARY KEY", "now": f"({_PG_NOW})",
                 "real": "DOUBLE PRECISION", "blob": "BYTEA"},
}


DEFAULT_GROUPS = (
    # Groupes décrits par le club : 12-18 ans (séances de 9h à 12h) et 7-11 ans (horaires à définir).
    {"name": "12–18 ans", "age_min": 12, "age_max": 18, "default_start": "09:00", "default_end": "12:00"},
    {"name": "7–11 ans", "age_min": 7, "age_max": 11, "default_start": "", "default_end": ""},
)


def kind_of(target):
    return "postgres" if str(target).startswith(("postgres://", "postgresql://")) else "sqlite"


def schema_statements(kind):
    text = SCHEMA
    for token, value in _TOKENS[kind].items():
        text = text.replace("{" + token + "}", value)
    return [s.strip() for s in text.split(";\n") if s.strip()]


def translate_sql(sql):
    """SQLite → PostgreSQL pour les rares différences utilisées par l'application."""
    sql = sql.replace("%", "%%").replace("?", "%s")
    sql = sql.replace("datetime('now')", _PG_NOW)
    sql = sql.replace("group_concat(", "string_agg(")
    sql = sql.replace(" LIKE ", " ILIKE ")  # LIKE est sensible à la casse sous PostgreSQL
    return sql


class Row(dict):
    """Ligne PostgreSQL : accès par nom (row['age']) ou par position (row[0]) comme sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    names = [c.name for c in (cursor.description or [])]

    def make(values):
        return Row(zip(names, values))
    return make


class Database:
    """Enveloppe commune SQLite/PostgreSQL : execute(), transactions via `with db:`."""

    def __init__(self, raw, kind):
        self.raw, self.kind = raw, kind

    def execute(self, sql, params=()):
        if self.kind == "postgres":
            return self.raw.execute(translate_sql(sql), params if params else None)
        return self.raw.execute(sql, params)

    def executemany(self, sql, seq):
        if self.kind == "postgres":
            cur = self.raw.cursor()
            cur.executemany(translate_sql(sql), list(seq))
            return cur
        return self.raw.executemany(sql, seq)

    def insert(self, sql, params=()):
        """INSERT dans une table dotée d'une colonne `id` ; retourne l'identifiant créé."""
        if self.kind == "postgres":
            return self.execute(sql + " RETURNING id", params).fetchone()["id"]
        return self.execute(sql, params).lastrowid

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        return False

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def connect(target):
    kind = kind_of(target)
    if kind == "postgres":
        if psycopg is None:
            raise RuntimeError("PostgreSQL demandé mais le paquet « psycopg » n'est pas installé "
                               "(pip install -r requirements-prod.txt).")
        raw = psycopg.connect(str(target), row_factory=_row_factory, connect_timeout=10,
                              prepare_threshold=None)  # compatible avec les « poolers » (Supabase, pgbouncer)
        return Database(raw, "postgres")
    raw = sqlite3.connect(str(target), timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("PRAGMA busy_timeout = 15000")
    try:
        raw.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:
        pass
    return Database(raw, "sqlite")


def get_db():
    """Connexion liée à la requête courante."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.close()
        except DatabaseErrors:
            pass


# --------------------------------------------------------------------------
# Migrations (anciennes bases : âge 13-18 et statuts sans « confirmed »)
# --------------------------------------------------------------------------
def _migrate_registrations_sqlite(db):
    """SQLite ne peut pas modifier une contrainte CHECK : on reconstruit la table (données conservées)."""
    row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='registrations'").fetchone()
    if row is None:
        return
    ddl = row[0] or ""
    if "BETWEEN 13 AND 18" not in ddl and "'confirmed'" in ddl:
        return
    create = next(st for st in schema_statements("sqlite")
                  if st.startswith("CREATE TABLE IF NOT EXISTS registrations ("))
    create = create.replace("CREATE TABLE IF NOT EXISTS registrations (",
                            "CREATE TABLE registrations_new (", 1)
    cols = [r[1] for r in db.execute("PRAGMA table_info(registrations)")]
    col_list = ", ".join(cols)
    db.raw.execute("PRAGMA foreign_keys = OFF")  # sinon DROP TABLE effacerait les intérêts liés (CASCADE)
    try:
        db.raw.execute("BEGIN IMMEDIATE")
        try:
            db.raw.execute("DROP TABLE IF EXISTS registrations_new")
            db.raw.execute(create)
            db.raw.execute(f"INSERT INTO registrations_new ({col_list}) SELECT {col_list} FROM registrations")
            db.raw.execute("DROP TABLE registrations")
            db.raw.execute("ALTER TABLE registrations_new RENAME TO registrations")
            db.raw.execute("COMMIT")
        except Exception:
            db.raw.execute("ROLLBACK")
            raise
    finally:
        db.raw.execute("PRAGMA foreign_keys = ON")


def _migrate_registrations_postgres(db):
    rows = db.execute(
        "SELECT conname, pg_get_constraintdef(oid) AS d FROM pg_constraint "
        "WHERE conrelid = 'registrations'::regclass AND contype = 'c'").fetchall()
    for r in rows:
        name, d = r["conname"], r["d"]
        if "age" in d and "13" in d:
            db.execute(f'ALTER TABLE registrations DROP CONSTRAINT "{name}"')
            db.execute("ALTER TABLE registrations ADD CONSTRAINT registrations_age_check "
                       "CHECK (age BETWEEN 7 AND 18)")
        elif "archived" in d and "confirmed" not in d:
            db.execute(f'ALTER TABLE registrations DROP CONSTRAINT "{name}"')
            db.execute("ALTER TABLE registrations ADD CONSTRAINT registrations_status_check "
                       "CHECK (status IN ('new','contacted','waiting','confirmed','archived'))")


def _apply_text_migrations(db):
    """Met à jour les textes par défaut devenus obsolètes, SEULEMENT s'ils n'ont pas été modifiés à la main."""
    for key, old, new in TEXT_MIGRATIONS["settings"]:
        db.execute("UPDATE site_settings SET value = ? WHERE key = ? AND value = ?", (new, key, old))
    for column, old, new in TEXT_MIGRATIONS["faqs"]:
        db.execute(f"UPDATE faqs SET {column} = ? WHERE {column} = ?", (new, old))


# --------------------------------------------------------------------------
# Initialisation (idempotente : ne supprime ni n'écrase jamais de données)
# --------------------------------------------------------------------------
def init_db(target, bootstrap_admin=None):
    """Crée les tables si nécessaire et ajoute le contenu initial manquant.

    bootstrap_admin = (identifiant, hash_du_mot_de_passe) : créé seulement s'il n'y a aucun admin.
    """
    kind = kind_of(target)
    if kind == "sqlite":
        Path(str(target)).parent.mkdir(parents=True, exist_ok=True)
    db = connect(target)
    try:
        if kind == "sqlite":
            _migrate_registrations_sqlite(db)
        with db:  # une seule transaction : tout ou rien
            if kind == "postgres":  # plusieurs workers au démarrage : un seul initialise à la fois
                db.execute("SELECT pg_advisory_xact_lock(8472911)")
            for statement in schema_statements(kind):
                db.execute(statement)
            if kind == "postgres":
                _migrate_registrations_postgres(db)
            for key, value in DEFAULT_SETTINGS.items():
                db.execute("INSERT INTO site_settings(key, value) VALUES (?, ?) "
                           "ON CONFLICT(key) DO NOTHING", (key, value))
            seeded = db.execute("SELECT 1 FROM site_settings WHERE key = '_content_seeded'").fetchone()
            if not seeded:
                # Contenu éditorial de départ (jamais de faux inscrits).
                for i, a in enumerate(DEFAULT_ACTIVITIES, start=1):
                    db.execute(
                        """INSERT INTO activities
                           (title_ar,title_fr,title_en,description_ar,description_fr,
                            description_en,icon,sort_order,is_published)
                           VALUES (?,?,?,?,?,?,?,?,1)""",
                        (a["title_ar"], a["title_fr"], a["title_en"], a["description_ar"],
                         a["description_fr"], a["description_en"], a["icon"], i * 10))
                for i, f in enumerate(DEFAULT_FAQS, start=1):
                    db.execute(
                        """INSERT INTO faqs
                           (question_ar,question_fr,question_en,answer_ar,answer_fr,
                            answer_en,sort_order,is_published)
                           VALUES (?,?,?,?,?,?,?,1)""",
                        (f["question_ar"], f["question_fr"], f["question_en"], f["answer_ar"],
                         f["answer_fr"], f["answer_en"], i * 10))
                db.execute("INSERT INTO site_settings(key, value) VALUES ('_content_seeded', '1')")
            if not db.execute("SELECT 1 FROM site_settings WHERE key = '_groups_seeded'").fetchone():
                if db.execute("SELECT COUNT(*) AS n FROM club_groups").fetchone()["n"] == 0:
                    for g_ in DEFAULT_GROUPS:
                        db.execute("INSERT INTO club_groups(name, age_min, age_max, default_start, default_end) "
                                   "VALUES (?,?,?,?,?)", (g_["name"], g_["age_min"], g_["age_max"],
                                                          g_["default_start"], g_["default_end"]))
                db.execute("INSERT INTO site_settings(key, value) VALUES ('_groups_seeded', '1')")
            _apply_text_migrations(db)
            if bootstrap_admin:
                username, password_hash = bootstrap_admin
                if db.execute("SELECT COUNT(*) AS n FROM admins").fetchone()["n"] == 0:
                    db.execute("INSERT INTO admins(username, password_hash) VALUES (?, ?)",
                               (username, password_hash))
            if kind == "sqlite":
                db.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
    finally:
        db.close()


# --------------------------------------------------------------------------
# Sauvegarde / restauration SQLite (pour PostgreSQL : pg_dump, voir scripts/backup_db.py)
# --------------------------------------------------------------------------
_LABEL_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def backup_db(db_path, backup_dir, label="manual", keep=30):
    """Copie cohérente de la base SQLite (API de sauvegarde, sûre même serveur actif)."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    label = _LABEL_RE.sub("-", label)[:30] or "manual"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    dest = backup_dir / f"young_engineers-{label}-{stamp}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    try:
        dest.chmod(0o600)
    except OSError:
        pass
    backups = sorted(backup_dir.glob("young_engineers-*.db"))
    for old in backups[:-keep] if keep and len(backups) > keep else []:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def list_backups(backup_dir):
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return []
    items = []
    for p in sorted(backup_dir.glob("young_engineers-*.db"), reverse=True):
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size,
                      "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc)})
    return items


def restore_db(db_path, backup_file, backup_dir):
    """Restaure une sauvegarde SQLite après copie de sécurité de la base actuelle."""
    backup_file = Path(backup_file)
    if not backup_file.is_file():
        raise FileNotFoundError(f"Sauvegarde introuvable : {backup_file}")
    probe = sqlite3.connect(f"file:{backup_file}?mode=ro", uri=True)
    try:
        if probe.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("La sauvegarde est corrompue (integrity_check).")
        tables = {r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = {"admins", "registrations", "activities", "faqs", "site_settings"} - tables
        if missing:
            raise ValueError(f"Fichier invalide, tables manquantes : {', '.join(sorted(missing))}")
    finally:
        probe.close()

    safety = None
    if Path(db_path).exists():
        safety = backup_db(db_path, backup_dir, label="before-restore")
    src = sqlite3.connect(f"file:{backup_file}?mode=ro", uri=True)
    dst = sqlite3.connect(str(db_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return safety
