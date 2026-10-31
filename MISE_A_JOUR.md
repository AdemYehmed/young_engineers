# Mise à jour : gestion du club (membres, séances, présences, paiements, galerie)

## Ce qui change
- Préinscriptions : âges **7 à 18 ans**. Deux groupes créés automatiquement : **12–18 ans (09:00–12:00)** et **7–11 ans**.
- Admin : bouton **Confirmer** sur une préinscription → crée le membre dans le bon groupe.
- Admin : **Membres, Séances (répétition chaque semaine), Calendrier, Présences + commentaire de séance, Paiements par mois, Galerie** photos/vidéos.
- Site public : page **Galerie** (visible seulement s'il y a des médias publics ; case « accord des parents » obligatoire pour publier).
- Données dans la base (Supabase). Photos et vidéos : **sur le disque du VPS** (`instance/media`), seules leurs informations sont en base.
- La base existante est migrée automatiquement au redémarrage : aucune donnée perdue.

## Limites à connaître
- Les fichiers du dossier `media` ne sont **pas** dans la sauvegarde de la base : copiez-les de temps en temps.
- Supabase gratuit : 500 Mo, pas de sauvegarde automatique.
- Envoi de vidéos via Netlify : Netlify coupe les requêtes longues (~26 s). Les photos et petites vidéos passent ; testez une vidéo courte d'abord.
- Testé ici : 82 tests sur SQLite, schéma PostgreSQL 16 (création + migration). Non testé : votre VPS, Supabase et Netlify réels.

## Étapes (une par une)
1. **Sur votre ordinateur** : copier le nouveau code sur votre dépôt local, `git add -A`, `git commit`, `git push`.
2. **Sur le VPS** : `cd` dans le dossier du site, `git pull`, `source .venv/bin/activate` (ou votre venv), `pip install -r requirements-prod.txt`.
3. **Sur le VPS**, ajouter dans `.env` (sans jamais montrer ce fichier) :
   `MEDIA_BASE_URL=https://169-58-195-202.sslip.io`
4. **nginx** : dans le bloc `server` du site, ajouter `client_max_body_size 320M;` puis `sudo nginx -t && sudo systemctl reload nginx`.
5. `sudo systemctl restart young-engineers` puis `sudo journalctl -u young-engineers -n 30`.
6. **Front Netlify** : `python3 scripts/build_netlify.py`, puis commit/push → Netlify se met à jour.
7. Vérifier : /admin → Membres, Séances, Paiements, Galerie.
