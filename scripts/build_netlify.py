#!/usr/bin/env python3
"""Génère le dossier netlify_front/ (fichiers statiques + règles de proxy vers Render).

Usage : python scripts/build_netlify.py https://VOTRE-SERVICE.onrender.com [--secret VALEUR]
--secret : active le « secret de proxy » (voir DEPLOIEMENT.md, étape optionnelle). Le fichier
netlify.toml produit contient alors ce secret : dépôt GitHub PRIVÉ obligatoire.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "netlify_front"

parser = argparse.ArgumentParser()
parser.add_argument("render_url")
parser.add_argument("--secret", default="")
args = parser.parse_args()

url = args.render_url.strip().rstrip("/")
if not re.fullmatch(r"https://[a-z0-9.-]+\.[a-z]{2,}", url):
    sys.exit("L'adresse doit ressembler à https://xxxx.onrender.com")
if args.secret and len(args.secret) < 24:
    sys.exit("Le secret doit faire au moins 24 caractères.")

static_out = OUT / "static"
if static_out.exists():
    shutil.rmtree(static_out)
shutil.copytree(ROOT / "yengineers" / "static", static_out)

headers = f'\n  [redirects.headers]\n    X-Proxy-Secret = "{args.secret}"\n' if args.secret else "\n"
(OUT / "netlify.toml").write_text(f'''[build]
  publish = "."

# Les fichiers de /static sont servis directement par Netlify (CDN) ;
# tout le reste est transmis à l'application Flask sur Render.
[[redirects]]
  from = "/static/*"
  to = "/static/:splat"
  status = 200

[[redirects]]
  from = "/*"
  to = "{url}/:splat"
  status = 200
  force = true{headers}''', encoding="utf-8")

(OUT / "_headers").write_text("""/static/*
  Cache-Control: public, max-age=3600
""", encoding="utf-8")
print("netlify_front/ généré pour", url, "(secret de proxy :", "oui" if args.secret else "non", ")")
