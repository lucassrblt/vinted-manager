# Avancement

## Étape 1 : socle, import Excel, stock et compta ✅

### Fait
- **Socle** : monorepo `backend/` (FastAPI, SQLAlchemy 2, Alembic, Postgres) + `frontend/` (Next.js 15, Tailwind 4, shadcn/ui), `docker-compose.yml`, `/health`.
- **Auth** : utilisateur unique créé en CLI (`python -m app.cli create-user`), argon2, session en cookie httpOnly/SameSite=Lax de 30 jours renouvelée à l'usage, blocage 15 min après 5 échecs, redirection vers `/login`.
- **Schéma complet** (toutes les tables des étapes 1 à 4) dans une migration initiale.
- **Calculs métier** dans `backend/app/services/calculs.py` (marge, marge %, coefficient, indicateur, délai, sell-through) et répartition de la remise dans `remise.py`.
- **Import Excel** avec aperçu corrigeable (rien n'est écrit avant validation), dont les onglets « Batch 2 », « Sourcing tests » et « Sourcing - Recherche ».
- **Export Excel** : onglets Suivi revente, Synthèse, Performance par batch et Sourcing ; le fichier exporté se réimporte.
- **Pages** : Aujourd'hui (version simple), Stock (filtres, tri, recherche, pagination, édition inline, actions groupées, ajout d'article et de batch), fiche article (timeline, preuves par glisser-déposer, zip), Batches et fiche batch, Compta (KPIs, périodes, graphiques, CSV URSSAF), Sourcing (éditable, avec les performances réelles), Import / export, Paramètres (onglet général).
- **Interface** : recherche globale Cmd/Ctrl+K, thème clair/sombre, sidebar repliable, vue mobile en cartes, skeletons, états vides, toasts.

### Tests
- Backend : 56 tests pytest, ruff et mypy OK. Couverture : calculs, remise, déduction marque/catégorie/couleur, import du vrai Excel avec totaux identiques à la synthèse (investi 800,90 €, CA 814,70 €, stock 453,52 €), export puis réimport, auth (cookie, blocage, expiration, renouvellement), API stock, batches, preuves, compta, URSSAF.
- Frontend : 11 tests Vitest, ESLint, Prettier, `tsc` et build Next OK.
- E2E Playwright : connexion puis import (`frontend/e2e/parcours.spec.ts`).

### À tester toi-même
1. `docker compose up --build`, puis `docker compose exec backend python -m app.cli create-user`.
2. Ouvrir http://localhost:3000, te connecter, importer `Suivi revente Vinted.xlsx` et vérifier l'aperçu (en particulier les 2 lignes « Vendu = oui » marquées à vérifier).
3. Comparer la page Compta avec ta synthèse Excel.
4. Ajouter un batch avec une remise, déposer une facture sur un article, exporter l'Excel.

## Décisions prises
- **Stack** : les sections 1-2 du cahier des charges n'ont pas été reçues, la stack a été déduite (FastAPI + Next.js 15).
- **Sessions** stockées en base (token hashé SHA-256), pas de JWT : on peut les révoquer, et la prolongation est écrite au plus une fois par heure.
- **Statuts et types** stockés en `VARCHAR` plutôt qu'en enum Postgres, pour simplifier les migrations.
- **Incohérence « Vendu = oui » / statut Excel** (Patagonia colorblock, Carhartt demi-zip sweat) : la colonne « Vendu » fait foi, comme dans les totaux de l'Excel. Ces lignes sont proposées en `vendu` avec un avertissement, et le statut reste modifiable dans l'aperçu.
- **Onglet « Batch 2 »** : il sert seulement à compléter le prix de vente cible des articles non vendus de « Batch 2 ».
- **Batch 1** n'a pas de prix brut : brut = net et remise = 0. La remise globale d'un batch importé est la somme des remises par ligne.
- **Prix de vente** : `prix_vente_reel` pour un article vendu, sinon `prix_vente_cible`. Marge et coefficient s'affichent aussi sur le prix cible (prévisionnel).
- **Ventes importées sans date** : elles comptent dans la vue « Tout » de la compta mais dans aucune période ; aucune ligne `Vente` n'est créée pour elles (la table `Vente` sert aux ventes détectées par mail).
- **Compta** : les flux (CA, marge réalisée, cotisations) sont filtrés sur la date de vente (Europe/Paris). Les valeurs de stock (investi, stock, coefficient global, sell-through) sont un instantané à date.
- **Sell-through** = vendus / publiés, comme demandé. L'Excel affichait vendus / total (44,8 %) ; l'app affiche 78,8 %.
- **Import unique** : refusé si des articles existent déjà.
- **Excel réel de test** dans `backend/tests/data/suivi-revente.xlsx`, non versionné (données privées). Le test est ignoré si le fichier est absent.
- **Uploads** : PDF, JPG, PNG, WEBP et HEIC, 15 Mo maximum, type vérifié par signature de fichier. Stockés dans `/data/preuves/…`.
- **Rewrites Next** figés au build : `BACKEND_URL` doit être défini au moment du build (Vercel, Docker).
- **npm** au lieu de pnpm (pnpm n'est pas installé sur la machine).
- **Graphiques** : CA en teal `#00897a` et marge en indigo `#6b74c9` (variantes plus claires en sombre), palette validée pour le daltonisme et le contraste.

## Étape 2 : mails et envois (à venir)
## Étape 3 : annonces et messages avec l'IA (à venir)
## Étape 4 : écran du jour et notifications push (à venir)
