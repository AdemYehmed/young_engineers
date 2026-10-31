# Déploiement gratuit : Vercel (site + backend Flask) + Supabase (PostgreSQL)

Une seule adresse publique (`https://xxx.vercel.app`). Pas de Netlify, pas de Render.
Vercel exécute l'application Flask (`app.py`) et sert `public/static` depuis son CDN. Supabase stocke les données.

**Non testé ici** : un vrai déploiement Vercel/Supabase (pas d'accès à vos comptes). Les contrôles ci-dessous servent à le vérifier.

## Étape 1 — Hash du mot de passe admin (sur votre ordinateur)
```bash
cd ~/test_club/young_engineers
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python create_admin.py --username monadmin --print-hash
```
Gardez les deux lignes affichées (`BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD_HASH`).

## Étape 2 — Supabase (base de données)
Voir DEPLOIEMENT.md, « Étape 2 » : créer le projet, puis **Connect → Session pooler** et copier l'adresse
`postgresql://postgres.XXXX:MOTDEPASSE@aws-0-REGION.pooler.supabase.com:5432/postgres`.

## Étape 3 — Préparer et envoyer le code
```bash
python scripts/build_public.py      # copie les fichiers CSS/JS/images dans public/static
git add .
git commit -m "Vercel"
git push
```

## Étape 4 — Vercel
1. https://vercel.com → *Sign up* avec GitHub → **Add New… → Project** → importez `young-engineers`.
2. Framework : Vercel détecte Flask (fichier `app.py`). Ne changez rien aux commandes.
3. **Environment Variables** (ajoutez-les avant de déployer) :

| Nom | Valeur |
|---|---|
| `YE_ENV` | `production` |
| `SECRET_KEY` | 64 caractères aléatoires : `python3 -c "import secrets;print(secrets.token_hex(32))"` |
| `DATABASE_URL` | l'adresse Supabase *Session pooler* |
| `SESSION_COOKIE_SECURE` | `true` |
| `TRUST_PROXY` | `1` |
| `YE_INSTANCE_DIR` | `/tmp/ye` |
| `BOOTSTRAP_ADMIN_USERNAME` | l'identifiant de l'étape 1 |
| `BOOTSTRAP_ADMIN_PASSWORD_HASH` | le hash de l'étape 1 (commence par `scrypt:`) |

4. Cliquez sur **Deploy**.

✅ **Contrôle A** : `https://VOTRE-PROJET.vercel.app/healthz` → « ok ». Supabase → *Table Editor* : les tables sont apparues.
✅ **Contrôle B** : la page d'accueil s'affiche avec ses styles ; changer de langue fonctionne.
✅ **Contrôle C** : une préinscription de test affiche la confirmation `YE-…`.
✅ **Contrôle D** : `/admin` → connexion → page **Déploiement** : deux appareils différents doivent donner des empreintes différentes (sinon essayez `TRUST_PROXY` = 2).

Ensuite : supprimez la préinscription de test et la variable `BOOTSTRAP_ADMIN_PASSWORD_HASH` (Vercel → Settings → Environment Variables, puis *Redeploy*).

## Limites à connaître
- Vercel : les fonctions sont « serverless » (pas de fichiers durables) ; c'est pourquoi les images sont stockées dans la base. Durée max d'une requête fixée à 30 s (`vercel.json`) ; les limites du plan gratuit changent : vérifiez-les sur vercel.com/pricing. Vérifiez aussi les conditions d'usage du plan gratuit (usage non commercial) si le club est une activité payante.
- Supabase gratuit : 500 Mo, pause après 1 semaine d'inactivité, aucune sauvegarde (exportez le CSV régulièrement).
- Si vous modifiez CSS/JS/images : relancez `python scripts/build_public.py` avant le commit.

## Dépannage
| Symptôme | Piste |
|---|---|
| Build échoue | Vercel → Deployments → le déploiement → *Build logs*. |
| 500 au chargement | *Runtime logs* : erreur de `DATABASE_URL` (mot de passe, adresse directe IPv6 au lieu du *Session pooler*). |
| Pas de styles | `public/static` absent du dépôt : `python scripts/build_public.py`, commit, push. |
| Formulaire « expiré » | Rechargez la page ; vérifiez que `SECRET_KEY` n'a pas changé entre déploiements. |
