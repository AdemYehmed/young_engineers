"""Tests automatisés (fonctionnent avec `python -m unittest` ou `pytest`)."""
import csv
import io
import json
import os
import re
import sqlite3
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash  # noqa: E402

from config import build_config  # noqa: E402
from yengineers import create_app  # noqa: E402
from yengineers.db import backup_db, connect, init_db, restore_db  # noqa: E402

ADMIN_USER, ADMIN_PASS = "tester", "correct-horse-battery"
VALID = {
    "parent_name": "Sami Ben Ali", "youth_first_name": "Yassine", "age": "15",
    "phone": "+216 25 676 360", "email": "Parent@Example.com",
    "preferred_language": "fr", "experience_level": "beginner",
    "message": "Bonjour", "consent": "1",
}


def tiny_png():
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


class Base(unittest.TestCase):
    config = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"YE_INSTANCE_DIR": self.tmp.name, "SECRET_KEY": "x" * 40, "YE_ENV": "development"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        cfg = {"TESTING": True, "MIN_FORM_SECONDS": 0, "PROPAGATE_EXCEPTIONS": False}
        cfg.update(self.config)
        self.app = create_app(cfg)
        self.client = self.app.test_client()
        self.addCleanup(self.tmp.cleanup)

    # ---- helpers
    def db(self):
        return connect(self.app.config["DATABASE"])

    def token(self, url, name="csrf_token", client=None):
        html = (client or self.client).get(url).get_data(as_text=True)
        m = re.search(rf'name="{name}" value="([^"]+)"', html)
        self.assertIsNotNone(m, f"{name} introuvable dans {url}")
        return m.group(1)

    def make_admin(self):
        conn = self.db()
        with conn:
            conn.execute("INSERT INTO admins(username, password_hash) VALUES (?,?)",
                         (ADMIN_USER, generate_password_hash(ADMIN_PASS)))
        conn.close()

    def login(self, client=None, password=ADMIN_PASS, user=ADMIN_USER):
        client = client or self.client
        tok = self.token("/admin/login", client=client)
        return client.post("/admin/login", data={"csrf_token": tok, "username": user, "password": password})

    def admin_post(self, url, data=None, **kw):
        data = dict(data or {})
        data["csrf_token"] = self.token("/admin/")
        return self.client.post(url, data=data, **kw)

    def register(self, **overrides):
        data = dict(VALID, interests=["robotics", "electronics"])
        data.update(overrides)
        data["csrf_token"] = self.token("/register")
        data["form_token"] = self.token("/register", name="form_token")
        return self.client.post("/register", data=data)


class TestSetup(Base):
    def test_imports_and_config(self):
        import yengineers.routes.admin, yengineers.routes.public  # noqa: F401,E401
        cfg = build_config({"YE_ENV": "development", "SECRET_KEY": "y" * 40,
                            "YE_INSTANCE_DIR": self.tmp.name})
        self.assertFalse(cfg["PRODUCTION"])

    def test_tables_created_and_no_fake_registrations(self):
        conn = self.db()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("admins", "registrations", "activities", "faqs", "site_settings"):
            self.assertIn(t, tables)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0], 5)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0], 6)

    def test_init_db_is_idempotent_and_keeps_data(self):
        self.register()
        conn = self.db()
        before = conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
        conn.close()
        init_db(self.app.config["DATABASE"])
        init_db(self.app.config["DATABASE"])
        conn = self.db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0], before)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0], 5)

    def test_deleted_activities_not_reseeded(self):
        conn = self.db()
        with conn:
            conn.execute("DELETE FROM activities")
        conn.close()
        init_db(self.app.config["DATABASE"])
        conn = self.db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0], 0)

    def test_production_requires_secret_and_secure_cookie(self):
        with self.assertRaises(RuntimeError):
            build_config({"YE_ENV": "production", "SECRET_KEY": "short", "YE_INSTANCE_DIR": self.tmp.name})
        with self.assertRaises(RuntimeError):
            build_config({"YE_ENV": "production", "SECRET_KEY": "z" * 40, "SESSION_COOKIE_SECURE": "false",
                          "YE_INSTANCE_DIR": self.tmp.name})
        ok = build_config({"YE_ENV": "production", "SECRET_KEY": "z" * 40, "YE_INSTANCE_DIR": self.tmp.name})
        self.assertTrue(ok["SESSION_COOKIE_SECURE"])


class TestPublicSite(Base):
    def test_pages_exist(self):
        for url in ("/", "/register", "/privacy", "/legal", "/robots.txt", "/healthz"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/does-not-exist").status_code, 404)

    def test_default_arabic_rtl_with_required_hero(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('lang="ar" dir="rtl"', html)
        self.assertIn("اكتشف عالم الروبوتيك والتكنولوجيا في قابس!", html)
        self.assertIn("خلّي صغيرك يكتشف البرمجة", html)
        self.assertIn("سجّل اهتمامك الآن", html)
        self.assertIn("اكتشف أنشطتنا", html)

    def test_language_switch_keeps_choice_and_direction(self):
        r = self.client.get("/lang/fr?next=/register")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/register"))
        html = self.client.get("/register").get_data(as_text=True)
        self.assertIn('lang="fr" dir="ltr"', html)
        self.assertIn("Formulaire de préinscription", html)
        self.client.get("/lang/en")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('lang="en" dir="ltr"', html)
        self.assertIn("Discover the world of robotics", html)
        self.client.get("/lang/ar")
        self.assertIn('dir="rtl"', self.client.get("/privacy").get_data(as_text=True))

    def test_language_switch_blocks_open_redirect(self):
        for evil in ("//evil.com", "https://evil.com", "/\\evil.com"):
            r = self.client.get("/lang/fr", query_string={"next": evil})
            self.assertNotIn("evil.com", r.headers["Location"])

    def test_no_mixed_languages_on_french_home(self):
        self.client.get("/lang/fr")
        html = self.client.get("/").get_data(as_text=True)
        html = re.sub(r'<div class="lang-switch".*?</div>', "", html, flags=re.S)  # noms de langues natifs : voulu
        body = re.sub(r"<[^>]+>", " ", html)
        self.assertIsNone(re.search(r"[؀-ۿ]", body), "caractères arabes dans la page française")

    def test_no_public_admin_link(self):
        for lang in ("ar", "fr", "en"):
            self.client.get(f"/lang/{lang}")
            for url in ("/", "/register", "/privacy"):
                self.assertNotIn("/admin", self.client.get(url).get_data(as_text=True))

    def test_all_internal_links_resolve(self):
        html = self.client.get("/").get_data(as_text=True)
        hrefs = set(re.findall(r'href="(/[^"#]*)', html))
        for href in hrefs:
            if href.startswith(("/static/", "/lang/")):
                continue
            self.assertEqual(self.client.get(href).status_code, 200, href)

    def test_translations_have_same_keys(self):
        base = Path(__file__).resolve().parent.parent / "yengineers" / "translations"
        keys = {lg: set(json.loads((base / f"{lg}.json").read_text(encoding="utf-8"))) for lg in ("ar", "fr", "en")}
        self.assertEqual(keys["ar"], keys["fr"])
        self.assertEqual(keys["fr"], keys["en"])

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.client.get("/register").headers["Cache-Control"], "no-store")

    def test_static_assets_served(self):
        for path in ("css/style.css", "js/main.js", "img/logo.svg", "img/hero.svg", "img/icons.svg"):
            self.assertEqual(self.client.get("/static/" + path).status_code, 200, path)


class TestRegistration(Base):
    def test_successful_registration_saved_in_sqlite(self):
        r = self.register()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/register/done"))
        page = self.client.get("/register/done").get_data(as_text=True)
        conn = self.db()
        row = conn.execute("SELECT * FROM registrations").fetchone()
        self.assertEqual(row["parent_name"], "Sami Ben Ali")
        self.assertEqual(row["age"], 15)
        self.assertEqual(row["email"], "parent@example.com")
        self.assertEqual(row["status"], "new")
        self.assertEqual(row["consent"], 1)
        self.assertRegex(row["reference"], r"^YE-[A-Z0-9]{8}$")
        self.assertIn(row["reference"], page)
        interests = {r[0] for r in conn.execute("SELECT interest FROM registration_interests")}
        self.assertEqual(interests, {"robotics", "electronics"})

    def test_confirmation_requires_a_registration_in_session(self):
        r = self.client.get("/register/done")
        self.assertEqual(r.status_code, 302)

    def test_references_are_unique(self):
        self.register()
        self.register(youth_first_name="Amine")
        conn = self.db()
        refs = [r[0] for r in conn.execute("SELECT reference FROM registrations")]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertEqual(len(refs), 2)

    def test_validation_errors_server_side(self):
        cases = {"age": "12", "age2": "19", "email": "pas-un-email", "phone": "abc",
                 "parent_name": "", "youth_first_name": "A", "preferred_language": "de",
                 "experience_level": "expert"}
        for field, value in cases.items():
            real = "age" if field == "age2" else field
            r = self.register(**{real: value})
            self.assertEqual(r.status_code, 422, field)
        r = self.register(interests=[])
        self.assertEqual(r.status_code, 422)
        r = self.register(consent="")
        self.assertEqual(r.status_code, 422)
        r = self.register(message="x" * 1001)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 0)

    def test_validation_messages_follow_language_and_keep_values(self):
        self.client.get("/lang/fr")
        r = self.register(age="12", parent_name="Parent Test")
        import html as htmllib
        html = htmllib.unescape(r.get_data(as_text=True))
        self.assertIn("L'âge doit être un nombre entre 13 et 18.", html)
        self.assertIn("Parent Test", html)

    def test_unknown_interest_values_are_ignored(self):
        self.register(interests=["robotics", "hacking"])
        interests = {r[0] for r in self.db().execute("SELECT interest FROM registration_interests")}
        self.assertEqual(interests, {"robotics"})

    def test_csrf_required(self):
        r = self.client.post("/register", data=dict(VALID, interests=["robotics"]))
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/register", data=dict(VALID, interests=["robotics"], csrf_token="forged"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 0)

    def test_honeypot_silently_drops(self):
        r = self.register(company_website="http://spam.example")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 0)

    def test_duplicate_is_not_inserted_twice(self):
        self.register()
        r = self.register()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 1)
        self.client.get("/lang/fr")
        self.assertIn("existe déjà", self.client.get("/register/done").get_data(as_text=True))

    def test_form_never_reveals_other_registrants(self):
        self.register()
        other = self.app.test_client()
        html = other.get("/register").get_data(as_text=True)
        self.assertNotIn("Yassine", html)
        self.assertNotIn("parent@example.com", html)
        self.assertEqual(other.get("/register/done").status_code, 302)

    def test_db_error_is_handled(self):
        with mock.patch("yengineers.routes.public.regs.create_registration",
                        side_effect=sqlite3.OperationalError("disk I/O error")):
            r = self.register()
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("disk I/O", r.get_data(as_text=True))

    def test_sql_injection_stored_as_text(self):
        self.register(parent_name="Robert'); DROP TABLE registrations;--")
        conn = self.db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 1)

    def test_html_is_escaped_in_admin(self):
        self.register(parent_name="<script>alert(1)</script>")
        self.make_admin()
        self.login()
        html = self.client.get("/admin/registrations").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_rate_limit_per_connection(self):
        self.app.config["REGISTER_MAX_PER_HOUR"] = 2
        self.register(youth_first_name="Aaa")
        self.register(youth_first_name="Bbb")
        r = self.register(youth_first_name="Ccc")
        self.assertEqual(r.status_code, 429)


class TestFormTiming(Base):
    config = {"MIN_FORM_SECONDS": 3}

    def test_too_fast_submission_rejected(self):
        r = self.register()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 0)

    def test_forged_form_token_rejected(self):
        data = dict(VALID, interests=["robotics"], csrf_token=self.token("/register"), form_token="forged")
        self.assertEqual(self.client.post("/register", data=data).status_code, 400)


class TestAdminAccess(Base):
    def setUp(self):
        super().setUp()
        self.make_admin()

    def test_unauthenticated_get_redirects_to_login(self):
        count = 0
        for rule in self.app.url_map.iter_rules():
            if not rule.rule.startswith("/admin") or rule.endpoint == "admin.login" or "GET" not in rule.methods:
                continue
            url = re.sub(r"<int:\w+>", "1", rule.rule)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/admin/login", r.headers["Location"], url)
            count += 1
        self.assertGreater(count, 10)

    def test_unauthenticated_post_is_refused(self):
        tok = self.token("/admin/login")
        for rule in self.app.url_map.iter_rules():
            if not rule.rule.startswith("/admin") or rule.endpoint == "admin.login" or "POST" not in rule.methods:
                continue
            url = re.sub(r"<int:\w+>", "1", rule.rule)
            r = self.client.post(url, data={"csrf_token": tok, "confirm": "yes"})
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/admin/login", r.headers["Location"], url)
            r = self.client.post(url, data={})  # sans CSRF
            self.assertEqual(r.status_code, 400, url)

    def test_csv_not_public(self):
        self.register()
        r = self.client.get("/admin/registrations/export.csv")
        self.assertEqual(r.status_code, 302)

    def test_login_wrong_and_right(self):
        r = self.login(password="wrong-password-123")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        r = self.login()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_password_stored_hashed_only(self):
        h = self.db().execute("SELECT password_hash FROM admins").fetchone()[0]
        self.assertNotIn(ADMIN_PASS, h)
        self.assertTrue(h.startswith(("scrypt:", "pbkdf2:")))

    def test_login_lockout(self):
        for _ in range(5):
            self.login(password="bad-password-1234")
        r = self.login()  # même le bon mot de passe est refusé pendant le blocage
        self.assertEqual(r.status_code, 429)

    def test_logout_ends_session(self):
        self.login()
        self.admin_post("/admin/logout")
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_logout_requires_post_and_csrf(self):
        self.login()
        self.assertEqual(self.client.get("/admin/logout").status_code, 405)
        self.assertEqual(self.client.post("/admin/logout").status_code, 400)

    def test_login_next_open_redirect_blocked(self):
        tok = self.token("/admin/login")
        r = self.client.post("/admin/login?next=https://evil.com",
                             data={"csrf_token": tok, "username": ADMIN_USER, "password": ADMIN_PASS})
        self.assertNotIn("evil.com", r.headers["Location"])

    def test_session_cookie_flags(self):
        r = self.client.get("/admin/login")
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_deleted_admin_loses_access(self):
        self.login()
        conn = self.db()
        with conn:
            conn.execute("DELETE FROM admins")
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_change_password(self):
        self.login()
        r = self.admin_post("/admin/password", {"current_password": ADMIN_PASS,
                                                "new_password": "another-strong-pass", "confirm_password": "another-strong-pass"})
        self.assertEqual(r.status_code, 302)
        other = self.app.test_client()
        self.assertEqual(self.login(other, password=ADMIN_PASS).status_code, 401)
        self.assertEqual(self.login(other, password="another-strong-pass").status_code, 302)


class TestAdminRegistrations(Base):
    def setUp(self):
        super().setUp()
        self.make_admin()
        for name, age, interests, email in (("Yassine", "15", ["robotics"], "a@example.com"),
                                            ("Lina", "13", ["programming", "electronics"], "b@example.com"),
                                            ("Omar", "17", ["projects"], "c@example.com")):
            c = self.app.test_client()
            data = dict(VALID, youth_first_name=name, age=age, interests=interests, email=email)
            data["csrf_token"] = self.token("/register", client=c)
            data["form_token"] = self.token("/register", name="form_token", client=c)
            self.assertEqual(c.post("/register", data=data).status_code, 302)
        self.login()

    def test_dashboard_stats_computed_from_database(self):
        html = self.client.get("/admin/").get_data(as_text=True)
        self.assertRegex(html, r'<span class="stat-n">3</span><span>Préinscriptions au total')
        self.assertRegex(html, r'<span class="stat-n">3</span><span>Reçues ces 7')
        self.assertIn('value="1"', html)
        from yengineers.services.registrations import dashboard_stats
        conn = self.db()
        s = dashboard_stats(conn)
        self.assertEqual(s["by_age"][15], 1)
        self.assertEqual(s["by_age"][14], 0)
        self.assertEqual(s["by_interest"]["electronics"], 1)
        self.assertEqual(s["by_interest"]["robotics"], 1)

    def test_search_and_filters(self):
        def names(q):
            html = self.client.get("/admin/registrations", query_string=q).get_data(as_text=True)
            return {n for n in ("Yassine", "Lina", "Omar") if n in html}
        self.assertEqual(names({}), {"Yassine", "Lina", "Omar"})
        self.assertEqual(names({"q": "lina"}), {"Lina"})
        self.assertEqual(names({"q": "c@example"}), {"Omar"})
        self.assertEqual(names({"age": "15"}), {"Yassine"})
        self.assertEqual(names({"interest": "electronics"}), {"Lina"})
        self.assertEqual(names({"status": "archived"}), set())
        self.assertEqual(names({"date_from": "2999-01-01"}), set())
        self.assertEqual(names({"date_from": "2000-01-01", "date_to": "2999-01-01"}), {"Yassine", "Lina", "Omar"})
        self.assertEqual(names({"q": "%"}), set())  # le joker est échappé

    def rid(self, name):
        return self.db().execute("SELECT id FROM registrations WHERE youth_first_name=?", (name,)).fetchone()[0]

    def test_detail_edit_note_status(self):
        rid = self.rid("Lina")
        self.assertEqual(self.client.get(f"/admin/registrations/{rid}").status_code, 200)
        data = dict(VALID, youth_first_name="Lina2", age="14", interests=["projects"],
                    status="contacted", admin_note="Appelée lundi", email="b@example.com")
        r = self.admin_post(f"/admin/registrations/{rid}", data)
        self.assertEqual(r.status_code, 302)
        row = self.db().execute("SELECT * FROM registrations WHERE id=?", (rid,)).fetchone()
        self.assertEqual((row["youth_first_name"], row["age"], row["status"], row["admin_note"]),
                         ("Lina2", 14, "contacted", "Appelée lundi"))
        ints = {r[0] for r in self.db().execute(
            "SELECT interest FROM registration_interests WHERE registration_id=?", (rid,))}
        self.assertEqual(ints, {"projects"})

    def test_edit_validation_error(self):
        rid = self.rid("Lina")
        r = self.admin_post(f"/admin/registrations/{rid}", dict(VALID, age="99", interests=["robotics"], status="new"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("flash-error", r.get_data(as_text=True))

    def test_quick_status_change_and_invalid_status(self):
        rid = self.rid("Omar")
        self.assertEqual(self.admin_post(f"/admin/registrations/{rid}/status", {"status": "waiting"}).status_code, 302)
        self.assertEqual(self.db().execute("SELECT status FROM registrations WHERE id=?", (rid,)).fetchone()[0], "waiting")
        self.assertEqual(self.admin_post(f"/admin/registrations/{rid}/status", {"status": "hacked"}).status_code, 400)

    def test_delete_requires_confirmation_and_makes_backup(self):
        rid = self.rid("Omar")
        self.assertEqual(self.client.get(f"/admin/registrations/{rid}/delete").status_code, 200)
        self.assertEqual(self.client.get(f"/admin/registrations/{rid}").status_code, 200)
        self.assertEqual(self.admin_post(f"/admin/registrations/{rid}/delete", {}).status_code, 400)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 3)
        r = self.admin_post(f"/admin/registrations/{rid}/delete", {"confirm": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 2)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registration_interests WHERE registration_id=?", (rid,)).fetchone()[0], 0)
        backups = list(Path(self.app.config["BACKUP_DIR"]).glob("*before-delete*.db"))
        self.assertEqual(len(backups), 1)
        conn = sqlite3.connect(backups[0])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 3)

    def test_unknown_registration_404(self):
        self.assertEqual(self.client.get("/admin/registrations/99999").status_code, 404)

    def test_csv_export(self):
        r = self.client.get("/admin/registrations/export.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["Content-Type"])
        self.assertIn("attachment", r.headers["Content-Disposition"])
        text = r.get_data(as_text=True)
        self.assertTrue(text.startswith("﻿"))
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][0], "Référence")
        self.assertEqual({r[4] for r in rows[1:]}, {"Yassine", "Lina", "Omar"})
        filtered = self.client.get("/admin/registrations/export.csv?age=13").get_data(as_text=True)
        self.assertEqual(len(list(csv.reader(io.StringIO(filtered.lstrip("﻿")), delimiter=";"))), 2)

    def test_csv_formula_injection_neutralised(self):
        rid = self.rid("Omar")
        self.admin_post(f"/admin/registrations/{rid}", dict(VALID, parent_name="=HYPERLINK(\"http://x\")",
                        youth_first_name="Omar", age="17", interests=["projects"], status="new",
                        email="c@example.com"))
        text = self.client.get("/admin/registrations/export.csv").get_data(as_text=True)
        self.assertIn("'=HYPERLINK", text)
        self.assertNotIn(";\"=HYPERLINK", text)


class TestAdminContent(Base):
    def setUp(self):
        super().setUp()
        self.make_admin()
        self.login()

    FORM = {"title_ar": "عنوان", "title_fr": "Titre", "title_en": "Title",
            "description_ar": "وصف", "description_fr": "Description", "description_en": "Description EN",
            "icon": "chip", "sort_order": "5", "is_published": "1"}

    def test_activity_crud_and_public_visibility(self):
        self.assertEqual(self.client.get("/admin/activities").status_code, 200)
        r = self.admin_post("/admin/activities/new", dict(self.FORM, title_fr="Atelier Drones"),
                            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        conn = self.db()
        aid = conn.execute("SELECT id FROM activities WHERE title_fr='Atelier Drones'").fetchone()[0]
        self.client.get("/lang/fr")
        self.assertIn("Atelier Drones", self.client.get("/").get_data(as_text=True))

        r = self.admin_post(f"/admin/activities/{aid}/edit", dict(self.FORM, title_fr="Atelier Drones 2"),
                            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        self.assertIn("Atelier Drones 2", self.client.get("/").get_data(as_text=True))

        self.admin_post(f"/admin/activities/{aid}/toggle")
        self.assertNotIn("Atelier Drones 2", self.client.get("/").get_data(as_text=True))
        self.admin_post(f"/admin/activities/{aid}/toggle")
        self.assertIn("Atelier Drones 2", self.client.get("/").get_data(as_text=True))

        self.assertEqual(self.admin_post(f"/admin/activities/{aid}/delete", {}).status_code, 400)
        self.assertEqual(self.admin_post(f"/admin/activities/{aid}/delete", {"confirm": "yes"}).status_code, 302)
        self.assertNotIn("Atelier Drones 2", self.client.get("/").get_data(as_text=True))

    def test_activity_requires_three_languages(self):
        r = self.admin_post("/admin/activities/new", dict(self.FORM, title_en=""), content_type="multipart/form-data")
        self.assertEqual(r.status_code, 422)

    def test_activity_display_order(self):
        self.client.get("/lang/en")
        self.admin_post("/admin/activities/new", dict(self.FORM, title_en="ZZZ First", sort_order="1"),
                        content_type="multipart/form-data")
        html = self.client.get("/").get_data(as_text=True)
        self.assertLess(html.index("ZZZ First"), html.index("<h3>Robotics</h3>"))

    def test_image_upload_validation(self):
        good = (io.BytesIO(tiny_png()), "pic.png")
        r = self.admin_post("/admin/activities/new", dict(self.FORM, title_fr="Avec image", image=good),
                            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        name = self.db().execute("SELECT image FROM activities WHERE title_fr='Avec image'").fetchone()[0]
        self.assertRegex(name, r"^[0-9a-f]{32}\.png$")
        served = self.client.get(f"/media/{name}")
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.mimetype, "image/png")

        for bad in ((io.BytesIO(b"<svg onload=alert(1)>"), "x.svg"),
                    (io.BytesIO(b"<?php echo 1; ?>"), "shell.php"),
                    (io.BytesIO(b"not really a png"), "fake.png"),
                    (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024)), "huge.png")):
            r = self.admin_post("/admin/activities/new", dict(self.FORM, title_fr="Mauvais", image=bad),
                                content_type="multipart/form-data")
            self.assertIn(r.status_code, (413, 422), bad[1])
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM activities WHERE title_fr='Mauvais'").fetchone()[0], 0)
        self.assertEqual(self.client.get("/media/../../etc/passwd").status_code, 404)
        self.assertEqual(self.client.get("/media/notvalid.png").status_code, 404)

    def test_faq_crud(self):
        data = {"question_ar": "س", "question_fr": "Question test ?", "question_en": "Q?",
                "answer_ar": "ج", "answer_fr": "Réponse test", "answer_en": "A", "sort_order": "1", "is_published": "1"}
        self.assertEqual(self.admin_post("/admin/faqs/new", data).status_code, 302)
        self.client.get("/lang/fr")
        self.assertIn("Question test ?", self.client.get("/").get_data(as_text=True))
        fid = self.db().execute("SELECT id FROM faqs WHERE question_fr='Question test ?'").fetchone()[0]
        self.admin_post(f"/admin/faqs/{fid}/edit", dict(data, answer_fr="Réponse modifiée"))
        self.assertIn("Réponse modifiée", self.client.get("/").get_data(as_text=True))
        self.admin_post(f"/admin/faqs/{fid}/toggle")
        self.assertNotIn("Question test ?", self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.admin_post(f"/admin/faqs/{fid}/delete", {"confirm": "yes"}).status_code, 302)

    def current_settings_form(self):
        html = self.client.get("/admin/settings").get_data(as_text=True)
        data = {}
        for m in re.finditer(r'<input id="([^"]+)" name="\1"[^>]*value="([^"]*)"', html):
            data[m.group(1)] = m.group(2)
        for m in re.finditer(r'<textarea id="([^"]+)" name="\1"[^>]*>(.*?)</textarea>', html, re.S):
            data[m.group(1)] = m.group(2)
        import html as h
        return {k: h.unescape(v) for k, v in data.items()}

    def test_settings_edit_reflected_publicly(self):
        data = self.current_settings_form()
        self.assertGreater(len(data), 30)
        data["phone"] = "+216 99 999 999"
        data["hero_title_fr"] = "Nouveau titre FR"
        data["social_facebook"] = "https://facebook.com/youngengineers"
        r = self.admin_post("/admin/settings", data, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        self.client.get("/lang/fr")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Nouveau titre FR", html)
        self.assertIn("+216 99 999 999", html)
        self.assertIn("https://facebook.com/youngengineers", html)

    def test_settings_validation(self):
        data = self.current_settings_form()
        data["social_instagram"] = "javascript:alert(1)"
        r = self.admin_post("/admin/settings", data, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertIn("flash-error", r.get_data(as_text=True))
        self.assertNotIn("javascript:alert", self.client.get("/").get_data(as_text=True))

    def test_empty_social_links_hidden(self):
        self.assertNotIn("Facebook", self.client.get("/").get_data(as_text=True))

    def test_backup_page(self):
        self.assertEqual(self.client.get("/admin/backups").status_code, 200)
        self.assertEqual(self.admin_post("/admin/backups").status_code, 302)
        self.assertEqual(len(list(Path(self.app.config["BACKUP_DIR"]).glob("*.db"))), 1)


class TestBackupRestore(Base):
    def test_backup_and_restore_roundtrip(self):
        self.register()
        cfg = self.app.config
        backup = backup_db(cfg["DATABASE"], cfg["BACKUP_DIR"])
        conn = self.db()
        with conn:
            conn.execute("DELETE FROM registrations")
        conn.close()
        safety = restore_db(cfg["DATABASE"], backup, cfg["BACKUP_DIR"])
        self.assertTrue(Path(safety).exists())
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0], 1)

    def test_restore_rejects_invalid_file(self):
        bogus = Path(self.tmp.name) / "bogus.db"
        bogus.write_bytes(b"this is not sqlite")
        with self.assertRaises(Exception):
            restore_db(self.app.config["DATABASE"], bogus, self.app.config["BACKUP_DIR"])
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM activities").fetchone()[0], 5)


class TestTranslateSql(unittest.TestCase):
    def test_placeholders_and_functions(self):
        from yengineers.db import translate_sql
        out = translate_sql("SELECT group_concat(a, ',') FROM t WHERE x = ? AND y LIKE ? ESCAPE '\\'")
        self.assertIn("string_agg(", out)
        self.assertIn("%s", out)
        self.assertNotIn("?", out)
        self.assertIn("ILIKE", out)
        self.assertNotIn("datetime('now')", translate_sql("UPDATE t SET d=datetime('now')"))

    def test_kind_detection(self):
        from yengineers.db import kind_of
        self.assertEqual(kind_of("postgres://u:p@h/db"), "postgres")
        self.assertEqual(kind_of("postgresql://u:p@h/db"), "postgres")
        self.assertEqual(kind_of("/tmp/x.db"), "sqlite")


class TestConfigDeploy(unittest.TestCase):
    def env(self, **kw):
        base = {"SECRET_KEY": "x" * 40, "YE_ENV": "production", "SESSION_COOKIE_SECURE": "true"}
        base.update(kw)
        return mock.patch.dict(os.environ, base, clear=True)

    def test_database_url_selects_postgres(self):
        with self.env(DATABASE_URL="postgresql://u:p@h:5432/db"):
            cfg = build_config()
        self.assertEqual(cfg["DB_KIND"], "postgres")

    def test_render_with_sqlite_is_refused(self):
        with self.env(RENDER="true"):
            with self.assertRaises(Exception):
                build_config()

    def test_short_secret_refused_in_production(self):
        with self.env(SECRET_KEY="court", DATABASE_URL="postgresql://u:p@h/db"):
            with self.assertRaises(Exception):
                build_config()


class TestProxySecret(Base):
    config = {"PROXY_SHARED_SECRET": "s" * 32, "CLIENT_IP_HEADER": "X-Nf-Client-Connection-Ip"}

    def test_refused_without_secret(self):
        self.assertEqual(self.client.get("/").status_code, 403)

    def test_refused_with_wrong_secret(self):
        self.assertEqual(self.client.get("/", headers={"X-Proxy-Secret": "nope"}).status_code, 403)

    def test_accepted_with_secret_and_health_exempt(self):
        self.assertEqual(self.client.get("/", headers={"X-Proxy-Secret": "s" * 32}).status_code, 200)
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_client_ip_header_only_trusted_with_secret(self):
        from yengineers import security
        with self.app.test_request_context("/", headers={"X-Nf-Client-Connection-Ip": "9.9.9.9"},
                                           environ_base={"REMOTE_ADDR": "1.1.1.1"}):
            self.assertEqual(security.visitor_ip(), "1.1.1.1")
        with self.app.test_request_context(
                "/", headers={"X-Nf-Client-Connection-Ip": "9.9.9.9", "X-Proxy-Secret": "s" * 32},
                environ_base={"REMOTE_ADDR": "1.1.1.1"}):
            self.assertEqual(security.visitor_ip(), "9.9.9.9")


class TestDeployFeatures(Base):
    def test_html_not_cached_but_media_cached(self):
        r = self.client.get("/")
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_media_served_from_database(self):
        from yengineers.services.uploads import delete_image, save_image
        from werkzeug.datastructures import FileStorage
        with self.app.app_context():
            from yengineers.db import get_db
            db = get_db()
            name = save_image(db, FileStorage(io.BytesIO(tiny_png()), filename="a.png"), 1024 * 1024)
            r = self.client.get(f"/media/{name}")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.mimetype, "image/png")
            self.assertIn("max-age", r.headers["Cache-Control"])
            self.assertEqual(r.data, tiny_png())
            delete_image(db, name)
        self.assertEqual(self.client.get(f"/media/{name}").status_code, 404)

    def test_deployment_page_requires_login_and_hides_secrets(self):
        self.make_admin()
        self.assertEqual(self.client.get("/admin/deployment").status_code, 302)
        self.login()
        html = self.client.get("/admin/deployment").get_data(as_text=True)
        self.assertIn("SQLite", html)
        self.assertNotIn("x" * 40, html)

    def test_bootstrap_admin_created_once(self):
        path = str(Path(self.tmp.name) / "boot.db")
        h = generate_password_hash(ADMIN_PASS)
        init_db(path, bootstrap_admin=("Boot", h))
        init_db(path, bootstrap_admin=("Autre", h))  # ignoré : un admin existe déjà
        conn = connect(path)
        names = [r[0] for r in conn.execute("SELECT username FROM admins")]
        conn.close()
        self.assertEqual(names, ["Boot"])

    def test_login_is_case_insensitive(self):
        self.make_admin()
        self.assertEqual(self.login(user=ADMIN_USER.upper()).status_code, 302)


if __name__ == "__main__":
    unittest.main()
