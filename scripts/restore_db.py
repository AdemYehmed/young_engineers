#!/usr/bin/env python3
"""Restaure une sauvegarde. ARRÊTEZ le serveur avant de lancer ce script.

SQLite     : python scripts/restore_db.py instance/backups/young_engineers-manual-XXXX.db
PostgreSQL : python scripts/restore_db.py instance/backups/young_engineers-XXXX.dump   (pg_restore --clean)
Une copie de sécurité est créée avant la restauration SQLite.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from config import build_config  # noqa: E402
from yengineers.db import restore_db  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cfg = build_config()
    backup = Path(sys.argv[1])
    if not backup.is_file():
        sys.exit(f"Fichier introuvable : {backup}")
    kind = "PostgreSQL" if cfg["DB_KIND"] == "postgres" else cfg["DATABASE"]
    print(f"Base actuelle : {kind}\nSauvegarde    : {backup}")
    if input("Tapez RESTAURER pour confirmer : ").strip() != "RESTAURER":
        sys.exit("Annulé.")
    if cfg["DB_KIND"] == "postgres":
        if not shutil.which("pg_restore"):
            sys.exit("pg_restore introuvable : installez le client PostgreSQL.")
        subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner",
                        "--dbname", cfg["DATABASE"], str(backup)], check=True)
    else:
        safety = restore_db(cfg["DATABASE"], backup, cfg["BACKUP_DIR"])
        if safety:
            print("Copie de sécurité de l'ancienne base :", safety)
    print("Restauration terminée.")


if __name__ == "__main__":
    main()
