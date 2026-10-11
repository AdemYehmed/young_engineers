#!/usr/bin/env python3
"""Crée le premier compte administrateur (seul moyen d'en créer un).

Usage interactif :   python create_admin.py
Réinitialiser un mot de passe :   python create_admin.py --username NOM --reset-password
Automatisation : définir YE_ADMIN_PASSWORD dans l'environnement (jamais dans un fichier versionné).

Déploiement sans terminal (Render gratuit) :   python create_admin.py --username NOM --print-hash
  -> affiche UNIQUEMENT une empreinte (hash) à coller dans BOOTSTRAP_ADMIN_PASSWORD_HASH ; rien n'est écrit en base.
"""
import argparse
import getpass
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from werkzeug.security import generate_password_hash  # noqa: E402

from config import build_config  # noqa: E402
from yengineers.db import connect, init_db  # noqa: E402

MIN_LENGTH = 12


def main():
    parser = argparse.ArgumentParser(description="Créer ou réinitialiser un administrateur.")
    parser.add_argument("--username", help="identifiant (3 à 64 caractères)")
    parser.add_argument("--reset-password", action="store_true",
                        help="changer le mot de passe d'un administrateur existant")
    parser.add_argument("--print-hash", action="store_true",
                        help="afficher l'empreinte du mot de passe sans toucher à la base")
    args = parser.parse_args()

    username = (args.username or input("Identifiant administrateur : ")).strip()
    if not 3 <= len(username) <= 64:
        sys.exit("L'identifiant doit contenir entre 3 et 64 caractères.")

    password = os.environ.get("YE_ADMIN_PASSWORD")
    if not password:
        if not sys.stdin.isatty():
            sys.exit("Aucun terminal interactif : définissez YE_ADMIN_PASSWORD.")
        password = getpass.getpass(f"Mot de passe ({MIN_LENGTH} caractères minimum) : ")
        if password != getpass.getpass("Confirmez le mot de passe : "):
            sys.exit("Les mots de passe ne correspondent pas.")
    if len(password) < MIN_LENGTH:
        sys.exit(f"Le mot de passe doit contenir au moins {MIN_LENGTH} caractères.")

    hashed = generate_password_hash(password)
    if args.print_hash:
        print("BOOTSTRAP_ADMIN_USERNAME=" + username)
        print("BOOTSTRAP_ADMIN_PASSWORD_HASH=" + hashed)
        return

    cfg = build_config()
    init_db(cfg["DATABASE"])
    conn = connect(cfg["DATABASE"])
    try:
        row = conn.execute("SELECT id FROM admins WHERE lower(username) = lower(?)", (username,)).fetchone()
        with conn:
            if row and args.reset_password:
                conn.execute("UPDATE admins SET password_hash = ? WHERE id = ?", (hashed, row["id"]))
                print(f"Mot de passe de « {username} » réinitialisé.")
            elif row:
                sys.exit("Cet administrateur existe déjà (utilisez --reset-password pour changer son mot de passe).")
            else:
                conn.execute("INSERT INTO admins(username, password_hash) VALUES (?, ?)", (username, hashed))
                print(f"Administrateur « {username} » créé. Connexion : /admin")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
