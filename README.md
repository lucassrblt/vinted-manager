# Revente : gestion de l'activité Vinted

Application personnelle (un seul utilisateur) qui remplace l'Excel « Suivi revente » : stock, batches, compta, sourcing, puis (étapes suivantes) lecture des mails Vinted, envois, annonces avec l'IA et notifications push.

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
   | `FERNET_KEY` | voir plus bas (nécessaire à l'étape 2) |
   | `LOG_LEVEL` | `INFO` |
   | `ANTHROPIC_API_KEY` | étape 3 |
   | `ANTHROPIC_MODEL` | `claude-haiku-5-5` (étape 3, optionnel) |
   | `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` | étape 4 |

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

# Clés VAPID (notifications push, étape 4)
npx web-push generate-vapid-keys
```

Garde ces clés en lieu sûr : sans la même `FERNET_KEY`, les identifiants IMAP enregistrés ne peuvent plus être déchiffrés.

### Mot de passe d'application Gmail (étape 2)

Gmail refuse ton mot de passe habituel en IMAP :
1. Active la validation en deux étapes : https://myaccount.google.com/security
2. Va sur https://myaccount.google.com/apppasswords, crée un mot de passe nommé « Revente » et copie les 16 caractères.
3. Dans l'app : **Paramètres → Mails**, serveur `imap.gmail.com`, port `993`, ton adresse et ce mot de passe d'application.

### Améliorer la reconnaissance des mails Vinted (étape 2)

Dépose de vrais mails Vinted au format `.eml` (dans Gmail : ⋮ → **Télécharger le message**) dans `backend/fixtures/emails/<type>/` :
`vente`, `bordereau`, `message`, `offre`, `expedie`, `livre`, `argent_disponible`, `evaluation`, `litige`, `autre`.
Les tests vérifient automatiquement le classement et l'extraction sur chacun de ces fichiers. Ils ne sont pas versionnés (données personnelles).
