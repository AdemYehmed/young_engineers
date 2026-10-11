# Young Engineers — site web du club (Gabès, Tunisie)

Site public multilingue (arabe par défaut en RTL, français et anglais en LTR), formulaire de
préinscription enregistré dans SQLite (local) ou PostgreSQL (production) et espace d'administration privé (`/admin`).
Technologies : Python 3, Flask, SQLite, Jinja2, HTML/CSS/JavaScript. Aucun service cloud, aucun Node.js.

> Une fois lancé en local, le site n'est accessible que depuis votre ordinateur
> (`http://127.0.0.1:5000`). Il n'est **pas** en ligne sur Internet tant que vous ne l'avez pas
> hébergé (voir « Mise en production »).

---

> **Mise en ligne Netlify + Render + PostgreSQL : voir [DEPLOIEMENT.md](DEPLOIEMENT.md).**
> Sources officielles : <https://render.com/docs/free> · <https://render.com/docs/blueprint-spec> · <https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/>

## 1. Installation sur Ubuntu (pas à pas)

```bash
# 1) Extraire l'archive
unzip young_engineers.zip
cd young_engineers

# 2) Installer Python et les outils si nécessaire
sudo apt update
sudo apt install -y python3 python3-venv python3-pip unzip

# 3) Environnement virtuel + dépendances
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4) Configuration
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # copiez le résultat dans SECRET_KEY=
nano .env

# 5) Base de données (crée les tables ; ne supprime jamais de données existantes)
python init_db.py

# 6) Créer le compte administrateur (mot de passe demandé de façon masquée, 12 caractères minimum)
python create_admin.py

# 7) Démarrer
python app.py
```

Ouvrez ensuite :

* Site public : <http://127.0.0.1:5000>
* Administration : <http://127.0.0.1:5000/admin> (aucun lien public n'y mène)

### Raccourci : `run.sh`

```bash
chmod +x run.sh
./run.sh
```

`run.sh` vérifie Python (3.9+), crée `.venv` si besoin, installe les dépendances seulement si
`requirements.txt` a changé, crée `.env` avec une clé secrète aléatoire s'il n'existe pas,
initialise la base **sans jamais l'écraser**, signale s'il n'y a pas encore d'administrateur,
puis lance le serveur de développement. Il ne crée pas l'administrateur à votre place :
lancez `.venv/bin/python create_admin.py` dans un autre terminal.

Variables utiles : `YE_PORT=5001 ./run.sh` (autre port) et `YE_OFFLINE=1 ./run.sh`
(n'installe rien depuis Internet et utilise les paquets Python du système).

## 2. Configuration (`.env`)

| Variable | Rôle |
|---|---|
| `YE_ENV` | `development` (défaut) ou `production` |
| `SECRET_KEY` | Clé des sessions. **Obligatoire en production** (32 caractères minimum) |
| `SESSION_COOKIE_SECURE` | Cookies HTTPS uniquement. Obligatoire en production |
| `DATABASE_PATH`, `UPLOAD_DIR`, `BACKUP_DIR` | Emplacements (défaut : dossier `instance/`) |
| `MAX_UPLOAD_MB` | Taille maximale des images envoyées (défaut 3) |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_MINUTES` | Limitation des tentatives de connexion (5 / 15 min) |
| `REGISTER_MAX_PER_HOUR` | Envois de formulaire par connexion et par heure (10) |
| `TRUST_PROXY` | Nombre de reverse proxys de confiance (0 en local) |

En production, l'application **refuse de démarrer** si `SECRET_KEY` est absente/faible ou si les
cookies sécurisés sont désactivés.

## 3. Utilisation de l'administration

Connexion sur `/admin` avec le compte créé par `create_admin.py`.

* **Tableau de bord** : total, préinscriptions des 7 derniers jours, répartition par âge, centre
  d'intérêt et statut, dernières demandes (tout est calculé depuis la base).
* **Préinscriptions** : recherche (nom, email, téléphone, référence), filtres (âge, centre
  d'intérêt, statut, dates), détail, modification, note privée, statut (nouveau / contacté / en
  attente / archivé), suppression avec page de confirmation, **export CSV** (UTF-8 avec BOM pour
  Excel ; les cellules commençant par `= + - @` sont neutralisées contre l'injection de formules,
  d'où l'apostrophe devant les numéros commençant par `+`).
* **Activités** : ajout, modification, suppression avec confirmation, publier/masquer, titre et
  description en 3 langues, image (PNG/JPG/WEBP/GIF), ordre d'affichage.
* **FAQ** : mêmes fonctions, en 3 langues.
* **Contenu du site** : textes du hero, présentation, préinscription, coordonnées, réseaux
  sociaux (liens `https://` ; un lien vide n'est pas affiché), durée de conservation des données,
  texte complémentaire des mentions légales, **logo**.
* **Sauvegardes** et **Mot de passe**.

Mot de passe oublié : `python create_admin.py --username NOM --reset-password`.

### Logo
Remplacez `yengineers/static/img/logo.svg` par le logo officiel (même nom), ou envoyez-le depuis
*Contenu du site → Logo*.

### Images et polices
Le site fonctionne **sans ressource distante**. Les illustrations (robot, circuit, icônes) sont des
SVG originaux inclus dans le projet. Pour ajouter de vraies photos d'atelier, envoyez-les comme
image d'une activité. Les polices sont celles du système (pile adaptée à l'arabe) ; vous pouvez
ajouter vos fichiers `.woff2` dans `yengineers/static/fonts/` et les déclarer avec `@font-face`.

## 4. Sauvegarde et restauration

```bash
python scripts/backup_db.py                       # sauvegarde cohérente dans instance/backups/
# Arrêtez le serveur, puis :
python scripts/restore_db.py instance/backups/young_engineers-manual-XXXX.db
```

La restauration demande de taper `RESTAURER`, vérifie l'intégrité de la sauvegarde et crée
d'abord une copie de sécurité de la base actuelle. Une sauvegarde automatique est aussi créée
avant chaque suppression d'une préinscription. Pensez à copier régulièrement `instance/backups/`
sur un autre support : ce dossier contient des données personnelles.

## 5. Mise en production (hébergement en ligne)

Prérequis : un serveur (VPS), un nom de domaine, **HTTPS** (certificat Let's Encrypt).

```bash
pip install -r requirements-prod.txt
# .env : YE_ENV=production, SECRET_KEY=<32+ caractères>, SESSION_COOKIE_SECURE=true, TRUST_PROXY=1
gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
```

Placez ensuite Nginx ou Caddy devant Gunicorn (reverse proxy + HTTPS), en transmettant
`X-Forwarded-For`, `X-Forwarded-Proto` et `Host`. Lancez Gunicorn avec `systemd` pour qu'il
redémarre automatiquement, et sauvegardez `instance/` (base, images, sauvegardes).
Le serveur intégré `python app.py` est réservé au développement local.

Évolution vers une base distante : tout l'accès aux données passe par `yengineers/db.py` et les
requêtes SQL des modules `services/` et `routes/` ; la migration vers PostgreSQL/MySQL consistera
à adapter ces couches (le schéma est dans `db.py`).

## 6. Sécurité et confidentialité (ce qui est implémenté)

* Protection CSRF sur tous les envois (jeton de session, comparaison à temps constant).
* Mots de passe hachés (Werkzeug/scrypt) ; vérification à temps constant même si l'identifiant
  n'existe pas ; nouvelle session à chaque connexion ; cookies `HttpOnly`, `SameSite=Lax`,
  `Secure` en production ; durée de session limitée.
* Limitation des tentatives de connexion (par connexion et par identifiant), sans stocker d'IP en
  clair (condensé HMAC).
* Contrôle d'accès serveur sur **toutes** les routes `/admin` (filtre central) ; redirection vers
  la connexion si non authentifié ; aucune création de compte publique.
* Requêtes SQL paramétrées uniquement ; échappement automatique Jinja2 ; en-têtes de sécurité
  (CSP stricte sans script ni style inline, `X-Frame-Options`, `nosniff`, HSTS en production).
* Formulaire public : validation serveur et navigateur, champ piège (honeypot), jeton de
  temporisation, limitation par connexion, détection des doublons, aucune donnée d'autres
  inscrits jamais affichée, numéro de confirmation propre à la session.
* Images : extension et signature vérifiées, SVG refusé, taille limitée, nom aléatoire.
* Aucune donnée envoyée à un service externe ; pas de cookie publicitaire ni de traceur.
* Erreurs : pages génériques, les détails techniques restent dans les journaux du serveur.

**À vérifier par vous :** la politique de confidentialité et les mentions légales sont des
**modèles** rédigés d'après le fonctionnement réel du site (durée de conservation par défaut :
12 mois, modifiable dans l'administration). Faites-les relire pour la réglementation tunisienne
sur les données personnelles (notamment pour des mineurs) avant publication. Les réponses de la
FAQ sont aussi des textes de départ à relire. Aucune date, aucun tarif, aucune adresse précise,
aucun témoignage ni certification n'a été inventé.

## 7. Tests

```bash
python -m unittest discover -s tests -v      # aucune dépendance supplémentaire
# pytest peut aussi les lancer (pip install -r requirements-dev.txt) ; la suite a été exécutée avec unittest
```

63 tests couvrent : démarrage et création des tables, idempotence de l'initialisation, pages et
liens, arabe/RTL et français-anglais/LTR, changement de langue, absence de mélange de langues,
formulaire (validation, CSRF, honeypot, doublons, limitation, erreur de base), enregistrement
SQLite, accès administrateur (toutes les routes refusées sans session), connexion et blocage,
tableau de bord, recherche/filtres, modification, suppression avec confirmation et sauvegarde,
export CSV, CRUD des activités et FAQ, envoi d'images (formats et taille), paramètres, sauvegarde
et restauration, configuration de production.

## 8. Structure

```
young_engineers/
├── app.py  config.py  init_db.py  create_admin.py  run.sh
├── requirements.txt  requirements-prod.txt  requirements-dev.txt  .env.example  .gitignore
├── yengineers/
│   ├── __init__.py        fabrique d'application, erreurs, filtres
│   ├── db.py              schéma SQLite, init, sauvegarde/restauration
│   ├── defaults.py        contenu éditorial initial (sans donnée inventée)
│   ├── security.py        CSRF, limitation, en-têtes
│   ├── i18n.py            langues et direction RTL/LTR
│   ├── routes/            public.py, admin.py
│   ├── services/          registrations.py, settings.py, uploads.py
│   ├── translations/      ar.json, fr.json, en.json
│   ├── templates/         site public + admin/
│   └── static/            css/, js/, img/, fonts/
├── instance/              base, images et sauvegardes créées localement (non versionnées)
├── scripts/               backup_db.py, restore_db.py
└── tests/
```

(Le dossier `models/` du plan initial est remplacé par `services/`, qui regroupe la logique
métier et les requêtes.)
