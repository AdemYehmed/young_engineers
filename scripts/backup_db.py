#!/usr/bin/env python3
"""Sauvegarde de la base.

SQLite     : copie cohérente dans instance/backups/.
PostgreSQL : pg_dump (format custom) vers un fichier .dump ; nécessite le client PostgreSQL (pg_dump).

Usage : python scripts/backup_db.py
Pour PostgreSQL, définissez DATABASE_URL (adresse « External » de la base) dans votre terminal.
"""
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from config import build_config  # noqa: E402
from yengineers.db import backup_db  # noqa: E402

cfg = build_config()
if cfg["DB_KIND"] == "postgres":
    if not shutil.which("pg_dump"):
        sys.exit("pg_dump introuvable : installez le client PostgreSQL (postgresql-client).")
    Path(cfg["BACKUP_DIR"]).mkdir(parents=True, exist_ok=True)
    dest = Path(cfg["BACKUP_DIR"]) / f"young_engineers-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.dump"
    # L'adresse est passée en argument de processus local ; ne partagez pas le fichier produit.
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", str(dest), cfg["DATABASE"]], check=True)
    print("Sauvegarde créée :", dest, "(contient des données personnelles : à protéger)")
else:
    if not Path(cfg["DATABASE"]).exists():
        sys.exit("Aucune base à sauvegarder : " + cfg["DATABASE"])
    print("Sauvegarde créée :", backup_db(cfg["DATABASE"], cfg["BACKUP_DIR"], label="manual"))
