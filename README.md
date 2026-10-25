# Revente : gestion de l'activité Vinted

Application personnelle (un seul utilisateur) qui remplace l'Excel « Suivi revente » : stock, batches, compta, sourcing, lecture des mails Vinted, envois et bordereaux, annonces et réponses aux acheteurs avec l'IA, écran du jour et notifications push (PWA installable).

- `backend/` : FastAPI, SQLAlchemy 2, Alembic, PostgreSQL
- `frontend/` : Next.js 15, Tailwind 4, shadcn/ui

L'avancement et les décisions prises sont dans [PROGRESS.md](PROGRESS.md).

---

## Lancer en local

Prérequis : Docker Desktop.

```bash
cp .env.example .env          # garder les valeurs par défaut en local
docker compose up --build     # db + backend (:8000) + frontend (:3000)
docker compose exec backend python -m app.cli create-user
```

Ouvre ensuite http://localhost:3000, connecte-toi, puis va dans **Import / export** pour importer ton Excel.

Pour changer le mot de passe : `docker compose exec backend python -m app.cli reset-password`.

Pour essayer l'interface sans tes données (base vide uniquement) :
`docker compose exec backend python -m app.cli seed-demo`.

### Développement sans Docker

```bash
# Postgres (n'importe lequel), puis :
cd backend
uv sync
export DATABASE_URL=postgresql+psycopg://vm:vm@localhost:5432/vm DATA_DIR=./data COOKIE_SECURE=false
uv run alembic upgrade head
uv run python -m app.cli create-user
uv run uvicorn app.main:app --reload

cd frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev
```

### Tests et qualité

```bash
# Backend : tests sur une base Postgres dédiée (vidée à chaque test)
cd backend
docker run -d --name vm-pg-test -e POSTGRES_USER=vm -e POSTGRES_PASSWORD=vm -e POSTGRES_DB=vm_test -p 54329:5432 postgres:16-alpine
cp ~/Downloads/"Suivi revente Vinted.xlsx" tests/data/suivi-revente.xlsx   # non versionné
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy app

# Extension Chrome
cd extension
npm install && npm test && npm run typecheck && npm run lint && npm run build

# Frontend
cd frontend
npm run lint && npm run typecheck && npm test
npm run e2e   # app lancée, base vide, utilisateur demo@example.com / demo-motdepasse (variables E2E_*)
```

---

## Déploiement

### 1. Railway (backend + base de données)

1. Crée un compte sur https://railway.app, puis **New Project → Deploy from GitHub repo** et choisis ce dépôt.
2. Dans le service créé : **Settings → Root Directory** = `backend`. Railway détecte le `Dockerfile`.
3. **+ New → Database → PostgreSQL** dans le même projet.
4. **Volume** : sur le service backend, **Settings → Volumes → Add Volume**, point de montage `/data`. Les preuves d'achat, bordereaux et pièces jointes y sont stockés.
5. **Variables** du service backend :

   | Variable | Valeur |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (référence Railway ; le préfixe est converti automatiquement) |
   | `DATA_DIR` | `/data` |
   | `COOKIE_SECURE` | `true` |
   | `FERNET_KEY` | voir plus bas (obligatoire pour configurer la boîte mail) |
   | `LOG_LEVEL` | `INFO` |
   | `ANTHROPIC_API_KEY` | clé API Anthropic (console.anthropic.com), pour les annonces et réponses |
   | `ANTHROPIC_MODEL` | `claude-haiku-5-5` (optionnel) |
   | `REPLICATE_API_TOKEN` | token Replicate (replicate.com → Account → API tokens), pour la retouche des photos |
   | `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` | notifications push (voir plus bas) |

6. **Settings → Networking → Generate Domain** pour obtenir l'URL publique, par exemple `https://revente-backend.up.railway.app`.
7. Une seule instance (ne pas augmenter les réplicas) : le planificateur de tâches tourne dans le même process. Les migrations Alembic sont lancées automatiquement à chaque démarrage.
8. Crée ton utilisateur : dans Railway, ouvre le service puis **⋯ → Shell** (ou `railway run` avec la CLI) et lance
   ```bash
   python -m app.cli create-user
   ```

### 2. Vercel (frontend)

1. Crée un compte sur https://vercel.com, puis **Add New → Project** et importe le dépôt.
2. **Root Directory** = `frontend` (framework Next.js détecté).
3. Variable d'environnement : `BACKEND_URL` = l'URL Railway de l'étape 6 (sans `/` final). Elle est utilisée **au build** par les rewrites `/api/*` : redéploie si tu la changes.
4. Déploie. Le navigateur ne parle qu'à Vercel, qui relaie `/api` vers Railway : le cookie de session reste sur ton domaine Vercel.

### Générer les clés

```bash
# Clé Fernet (chiffrement des identifiants IMAP)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Clés VAPID (notifications push)
docker compose exec backend python -m app.cli vapid-keys   # ou : cd backend && uv run python -m app.cli vapid-keys
```

Copie les 3 lignes affichées (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` avec ton adresse) dans les variables du backend (Railway, ou `.env` en local), puis redémarre.

Garde ces clés en lieu sûr : sans la même `FERNET_KEY`, les identifiants IMAP enregistrés ne peuvent plus être déchiffrés.

### Installer l'app sur le téléphone et activer les notifications

1. Ouvre l'URL Vercel sur ton téléphone et connecte-toi.
2. **iPhone** : dans Safari, bouton Partager → « Sur l'écran d'accueil », puis ouvre Revente **depuis l'icône** (sur iPhone, les notifications ne fonctionnent que dans l'app installée). **Android** : menu de Chrome → « Installer l'application ».
3. Dans l'app : Paramètres → Notifications → « Activer les notifications sur cet appareil », puis « Envoyer une notification de test ».
4. Choisis les notifications voulues : nouvelle vente, nouveau litige, nouvelle offre, rappel de 9 h des colis à envoyer.

### Photos des articles (retouche IA)

1. Paramètres → Photos : dépose une photo de ton tapis **seul**, prise de dessus, qui remplit tout le cadre. Elle sert de fond à toutes les photos.
2. Sur la fiche article (ou dans le générateur d'annonce) : dépose les photos **devant, dos, étiquette, logo**, ou toutes d'un coup, et éventuellement des photos de **défaut**, qui ne sont jamais retouchées.
3. Clique sur « Retoucher les photos ». Compte ~10 s par photo, et environ 0,07 $ par photo avec Nano Banana 2.
4. Vérifie chaque photo (bascule Originale / Retouchée, « Régénérer » pour une autre disposition), puis « Tout télécharger » pour récupérer le zip dans l'ordre Vinted.

Avec moins de 5 $ de crédit, Replicate limite à 6 générations par minute : l'app attend automatiquement, mais la génération est alors plus lente.

### Sauvegarde

Paramètres → Sauvegarde → « Télécharger la sauvegarde complète » : un zip avec l'export Excel, toute la base en JSON (sans mots de passe) et tous les fichiers (preuves, bordereaux, pièces jointes).

### Mot de passe d'application Gmail

Gmail refuse ton mot de passe habituel en IMAP :
1. Active la validation en deux étapes : https://myaccount.google.com/security
2. Va sur https://myaccount.google.com/apppasswords, crée un mot de passe nommé « Revente » et copie les 16 caractères.
3. Dans l'app : **Paramètres → Mails → Ajouter une boîte**, donne un nom au compte Vinted, puis ton adresse et ce mot de passe d'application (Gmail est présélectionné).

Une boîte par compte Vinted : refais l'opération pour chaque compte (le mot de passe d'application se crée sur le compte Google de chaque adresse).

### Améliorer la reconnaissance des mails Vinted

Dépose de vrais mails Vinted au format `.eml` (dans Gmail : ⋮ → **Télécharger le message**) dans `backend/fixtures/emails/<type>/` :
`vente`, `bordereau`, `message`, `offre`, `expedie`, `livre`, `argent_disponible`, `evaluation`, `litige`, `autre`.
Les tests vérifient automatiquement le classement et l'extraction sur chacun de ces fichiers. Ils ne sont pas versionnés (données personnelles).

Pour vérifier aussi les valeurs extraites, ajoute à côté un `.json` du même nom :

```json
{ "prix": "45.00", "titre_article": "Pull demi-zip polaire Ralph Lauren - Noir", "numero_commande": "8812345678" }
```

```bash
cd backend && uv run pytest tests/test_classifieur.py -v
```

Les règles s'ajustent ensuite dans l'app (**Règles des mails**) ou dans `backend/app/seed/regles.py` pour les règles par défaut.

### Extension Chrome (automatisation Vinted)

L'extension (`extension/`) exécute sur Vinted ce que décide vinted-manager : brouillons, réponses aux messages et
aux offres, relances des favoris, republications, baisses de prix, remerciements après vente. Un profil Chrome par
compte Vinted, chacun avec son jeton. Détails et décisions : `SPEC_EXTENSION.md` et `PROGRESS.md`.

1. `cd extension && npm install && npm run build`.
2. Chrome → `chrome://extensions` → mode développeur → « Charger l'extension non empaquetée » → `extension/dist`.
3. vinted-manager → Paramètres → Automatisation → « Générer un jeton d'extension » ; dans les options de l'extension,
   saisir l'URL du backend et ce jeton.
4. Ouvrir www.vinted.fr dans ce profil, puis confirmer le compte vu par l'extension (« C'est bien ce compte »).
5. Telegram (facultatif) : `TELEGRAM_BOT_TOKEN` dans les variables du backend, puis « Relier Telegram » et
   `/start <code>` au bot.

Arrêt d'urgence : interrupteur général dans Paramètres → Automatisation, `/stop` sur Telegram, ou bouton Pause de
l'extension.
