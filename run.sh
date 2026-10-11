#!/usr/bin/env bash
# Lance Young Engineers en local (développement). Ne réinitialise ni n'écrase jamais la base.
# Options d'environnement :
#   YE_OFFLINE=1   n'installe rien depuis Internet (utilise les paquets Python du système)
#   YE_PORT=5000   port d'écoute      YE_HOST=127.0.0.1   adresse d'écoute
set -euo pipefail
cd "$(dirname "$0")"

# 1) Python 3.9+
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 est introuvable. Sur Ubuntu : sudo apt update && sudo apt install -y python3 python3-venv python3-pip" >&2
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "Python 3.9 ou plus récent est requis (version trouvée : $(python3 -V))." >&2
  exit 1
fi

# 2) Environnement virtuel
if [ ! -x .venv/bin/python ]; then
  echo "Création de l'environnement virtuel (.venv)…"
  if [ "${YE_OFFLINE:-0}" = "1" ]; then
    python3 -m venv --system-site-packages .venv
  else
    python3 -m venv .venv || { echo "Échec : installez python3-venv (sudo apt install -y python3-venv)." >&2; exit 1; }
  fi
fi
PY=.venv/bin/python

# 3) Dépendances (réinstallées seulement si requirements.txt a changé)
if [ "${YE_OFFLINE:-0}" != "1" ]; then
  STAMP=.requirements.stamp
  HASH=$(sha256sum requirements.txt | cut -d' ' -f1)
  if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$HASH" ]; then
    echo "Installation des dépendances…"
    $PY -m pip install --quiet --upgrade pip
    $PY -m pip install --quiet -r requirements.txt
    echo "$HASH" > "$STAMP"
  fi
fi

# 4) Fichier .env (créé une seule fois, avec une clé secrète aléatoire)
if [ ! -f .env ]; then
  cp .env.example .env
  KEY=$($PY -c 'import secrets; print(secrets.token_hex(32))')
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${KEY}|" .env
  chmod 600 .env
  echo "Fichier .env créé avec une clé secrète aléatoire."
fi

# 5) Base de données (idempotent : conserve les données existantes)
$PY init_db.py

# 6) Compte administrateur
if [ "$($PY -c 'from dotenv import load_dotenv; load_dotenv(); from config import build_config; from yengineers.db import connect; c=connect(build_config()["DATABASE"]); print(c.execute("SELECT COUNT(*) FROM admins").fetchone()[0])')" = "0" ]; then
  echo
  echo "Aucun administrateur n'existe encore. Dans un autre terminal, lancez :"
  echo "    cd $(pwd) && .venv/bin/python create_admin.py"
  echo
fi

HOST="${YE_HOST:-127.0.0.1}"; PORT="${YE_PORT:-5000}"
echo "Site public    : http://${HOST}:${PORT}"
echo "Administration : http://${HOST}:${PORT}/admin"
echo "(Accessible seulement sur cet ordinateur. Ctrl+C pour arrêter.)"
YE_HOST="$HOST" YE_PORT="$PORT" exec $PY app.py
