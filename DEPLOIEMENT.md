# Déploiement : Netlify (front) + Render (backend) + PostgreSQL

## Comment ça marche
```
Visiteur → Netlify (young-engineers.netlify.app)
              ├─ /static/*  → servi par Netlify (CSS, JS, images, polices)
              └─ tout le reste → proxy → Render (Flask + gunicorn) → PostgreSQL
```
Les visiteurs ne voient qu'**une seule adresse** (Netlify). Les cookies de session et la protection
CSRF restent donc « même site ». Le backend Flask génère les pages (arabe/français/anglais) ;
Netlify ne contient que les fichiers statiques et la règle de proxy.
**Point à vérifier** : la documentation Netlify ne dit pas explicitement que les cookies `Set-Cookie` traversent un proxy ; c'est le contrôle C ci-dessous. Si ça échoue : Plan B.

**Ce qui n'a pas pu être testé ici** : un vrai déploiement Netlify/Render (pas d'accès à vos comptes) et
la connexion Python↔PostgreSQL (le paquet `psycopg` n'est pas installable dans mon environnement).
Testés : 77 tests sur SQLite, et le schéma + les requêtes traduites exécutés sur un vrai PostgreSQL 16 via `psql`.
D'où les **points de contrôle** ci-dessous : faites-les dans l'ordre.

---

## Étape 0 — Préparer le code sur GitHub
1. Créez un compte sur github.com puis un dépôt **privé** `young-engineers`.
2. Dans le dossier du projet :
   ```bash
   git init && git add . && git commit -m "Site Young Engineers"
   git branch -M main
   git remote add origin https://github.com/VOTRE_COMPTE/young-engineers.git
   git push -u origin main
   ```
   (`.env`, bases de données et sauvegardes sont exclus par `.gitignore`.)

## Étape 1 — Générer le hash du mot de passe administrateur (sur votre ordinateur)
Render gratuit n'offre pas de terminal : le compte admin est créé au démarrage depuis 2 variables.
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python create_admin.py --username VOTRE_IDENTIFIANT --print-hash
```
Saisissez un mot de passe d'au moins 12 caractères. Le script affiche `BOOTSTRAP_ADMIN_USERNAME=…` et
`BOOTSTRAP_ADMIN_PASSWORD_HASH=scrypt:…` : **gardez ces deux lignes** (le mot de passe lui-même n'est jamais enregistré).

## Étape 2 — Render : base PostgreSQL + backend
**Option A — Blueprint (le plus simple)**
1. render.com → *New* → *Blueprint* → connectez GitHub → choisissez le dépôt. Render lit `render.yaml`.
2. Il vous demande `BOOTSTRAP_ADMIN_USERNAME` et `BOOTSTRAP_ADMIN_PASSWORD_HASH` : collez les valeurs de l'étape 1.
3. *Apply*. Render crée la base `young-engineers-db` et le service `young-engineers-api`.

**Option B — manuelle**
1. *New* → *PostgreSQL* : nom `young-engineers-db`, région la plus proche (Frankfurt). Copiez l'**Internal Database URL**.
2. *New* → *Web Service* → votre dépôt. Runtime **Python 3** ; Build : `pip install -r requirements-prod.txt` ;
   Start : `gunicorn app:app --workers 2 --threads 2 --timeout 60 --bind 0.0.0.0:$PORT` ; Health check path : `/healthz`.
3. Variables d'environnement :

| Variable | Valeur |
|---|---|
| `YE_ENV` | `production` |
| `SECRET_KEY` | 64 caractères aléatoires (`python3 -c "import secrets;print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | l'Internal Database URL |
| `SESSION_COOKIE_SECURE` | `true` |
| `TRUST_PROXY` | `2` (à vérifier, étape 5) |
| `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD_HASH` | étape 1 |

Les tables et le contenu de départ (activités, FAQ, paramètres) sont créés automatiquement au premier démarrage.

> ✅ **Contrôle A** : ouvrez `https://VOTRE-SERVICE.onrender.com/healthz` → « ok ».
> Puis `…/` → le site s'affiche. Si une erreur 500 apparaît, lisez *Logs* sur Render (le message dit si `psycopg` ou la base pose problème).

## Étape 3 — Netlify : le front
1. Sur votre ordinateur, générez le dossier front avec l'adresse Render :
   ```bash
   python scripts/build_netlify.py https://VOTRE-SERVICE.onrender.com
   git add netlify_front && git commit -m "Front Netlify" && git push
   ```
2. app.netlify.com → *Add new site* → *Import an existing project* → GitHub → votre dépôt.
3. **Base directory** : `netlify_front` ; **Build command** : (vide) ; **Publish directory** : `netlify_front`. *Deploy*.
4. (Optionnel) *Site configuration → Change site name* pour avoir `young-engineers.netlify.app`.

> ✅ **Contrôle B** : ouvrez l'adresse Netlify → le site s'affiche avec les styles. Changez de langue (AR/FR/EN) : la langue doit rester.
> ✅ **Contrôle C** : envoyez une préinscription de test (le formulaire doit afficher la confirmation avec une référence `YE-…`).
> Si les cookies ne passent pas par le proxy (formulaire « expiré », connexion admin impossible), voir « Plan B ».

## Étape 4 — Se connecter à l'administration
`https://VOTRE-SITE.netlify.app/admin` avec l'identifiant et le mot de passe de l'étape 1.
Puis, sur Render → *Environment*, **supprimez** `BOOTSTRAP_ADMIN_PASSWORD_HASH` (il n'est plus utile).
Supprimez ensuite votre préinscription de test depuis l'admin.

## Étape 5 — Vérifier l'adresse IP des visiteurs (anti-spam)
Dans l'admin → **Déploiement**. Vérifiez : schéma `https`, base `PostgreSQL`, et comparez l'« empreinte » obtenue depuis deux appareils
différents (4G et Wi-Fi) : elles doivent **différer**. Si elles sont identiques, tous les visiteurs partagent la même limite
(3 préinscriptions/heure au total) : ajustez `TRUST_PROXY` (essayez 1, 2 ou 3) ou utilisez l'étape 7.

## Étape 6 — Éviter la mise en veille (Render gratuit)
Un service gratuit s'endort après 15 min sans visite et met environ 1 minute à redémarrer ; Netlify coupe un proxy à 26 s :
le premier visiteur peut voir une erreur. Solutions : plan payant Render (le plus fiable), ou un service de « ping » qui appelle
`https://VOTRE-SERVICE.onrender.com/healthz` toutes les 10 min (attention : les heures gratuites mensuelles de Render sont limitées).

## Étape 7 — (Optionnel) Verrouiller le backend : seul Netlify peut l'appeler
1. Générez un secret : `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`.
2. Sur votre ordinateur : `python scripts/build_netlify.py https://VOTRE-SERVICE.onrender.com --secret LE_SECRET` puis commit/push.
   **Le dépôt doit être privé** (le secret est dans `netlify_front/netlify.toml`).
3. Render → *Environment* : `PROXY_SHARED_SECRET` = le secret ; `CLIENT_IP_HEADER` = `X-Nf-Client-Connection-Ip`
   — **nom non confirmé par la documentation du proxy Netlify** : testez-le dans la page *Déploiement* (deux appareils ⇒ deux empreintes
   différentes). Sans résultat, laissez `CLIENT_IP_HEADER` vide et réglez `TRUST_PROXY`.
4. Contrôle : l'adresse `onrender.com` directe répond 403, l'adresse Netlify fonctionne.

---

## Plan B — tout servir depuis Render (si le proxy Netlify pose problème)
Le backend sert déjà le site complet. Utilisez simplement `https://VOTRE-SERVICE.onrender.com` (ou un domaine perso pointé vers Render)
et laissez de côté Netlify. Rien d'autre à changer.

## Données et coûts — à lire
- **Base gratuite Render : elle expire 30 jours après sa création** (14 jours de grâce avant suppression), 1 Go, **sans sauvegarde**.
  Pour un vrai club : plan payant (sauvegardes incluses) ou une autre base PostgreSQL gratuite (ex. Neon) : il suffit de remplacer `DATABASE_URL`.
- Sauvegarde manuelle (PostgreSQL) : `DATABASE_URL=<External URL> python scripts/backup_db.py` (nécessite `pg_dump`).
  Restauration : `python scripts/restore_db.py fichier.dump`. Le fichier contient des données personnelles de mineurs : ne le partagez pas.
- Export rapide : admin → Préinscriptions → CSV.
- Les images (logo, activités) sont stockées **dans PostgreSQL** (le disque Render est effacé à chaque redémarrage).
- Les plans et limites changent : vérifiez les pages officielles avant de choisir (liens dans le README).

## Dépannage
| Symptôme | Piste |
|---|---|
| 500 immédiat | Render → Logs. `psycopg` absent ⇒ vérifiez `requirements-prod.txt` ; `DATABASE_URL` manquante en production sur Render ⇒ l'app refuse volontairement SQLite. |
| « Formulaire expiré » / connexion admin impossible via Netlify | Cookies non transmis : Plan B. |
| 403 partout | `PROXY_SHARED_SECRET` défini sans que Netlify envoie l'en-tête : rebuild avec `--secret` ou videz la variable. |
| Première page très lente / 504 | Réveil de Render (étape 6). |
| Admin : « limite atteinte » pour tout le monde | `TRUST_PROXY` / `CLIENT_IP_HEADER` (étape 5). |
