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
- Backend : 58 tests pytest, ruff et mypy OK. Couverture : calculs, remise, déduction marque/catégorie/couleur, import du vrai Excel avec totaux identiques à la synthèse (investi 800,90 €, CA 814,70 €, stock 453,52 €), export puis réimport, auth (cookie, blocage, expiration, renouvellement), API stock, batches, preuves, compta, URSSAF.
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
- **Les 2 lignes incohérentes sont bien vendues** (confirmé le 21/10/2026).
- **Ventes importées sans date** : à l'import, chaque vente reçoit une date tirée au hasard entre le 01/10/2026 et le 16/10/2026 (période modifiable dans l'aperçu), entre 9 h et 22 h (heure de Paris), jamais avant la date d'achat. Ces articles portent la note « date de vente estimée ». Aucune ligne `Vente` n'est créée pour eux (la table `Vente` sert aux ventes détectées par mail).
- **Compta** : les flux (CA, marge réalisée, cotisations) sont filtrés sur la date de vente (Europe/Paris). Les valeurs de stock (investi, stock, coefficient global, sell-through) sont un instantané à date.
- **Sell-through** = vendus / publiés (confirmé le 21/10/2026) : un article jamais mis en ligne ne compte pas.
- **Import unique** : refusé si des articles existent déjà.
- **Excel réel de test** dans `backend/tests/data/suivi-revente.xlsx`, non versionné (données privées). Le test est ignoré si le fichier est absent.
- **Uploads** : PDF, JPG, PNG, WEBP et HEIC, 15 Mo maximum, type vérifié par signature de fichier. Stockés dans `/data/preuves/…`.
- **Rewrites Next** figés au build : `BACKEND_URL` doit être défini au moment du build (Vercel, Docker).
- **npm** au lieu de pnpm (pnpm n'est pas installé sur la machine).
- **Graphiques** : CA en teal `#00897a` et marge en indigo `#6b74c9` (variantes plus claires en sombre), palette validée pour le daltonisme et le contraste.

## Étape 2 : lecture des mails et envois ✅

### Fait
- **Configuration IMAP** (Paramètres → Mails) : préréglages Gmail, Outlook et Orange, mot de passe chiffré avec Fernet, bouton « Tester la connexion » avec des messages clairs (en particulier pour le mot de passe d'application Gmail).
- **Synchronisation** toutes les 5 minutes (APScheduler) et bouton « Synchroniser maintenant ». Seuls les expéditeurs Vinted configurés sont lus, depuis la dernière synchro. Le dossier est ouvert en lecture seule (EXAMINE) et les mails sont lus avec BODY.PEEK[] : jamais supprimés, déplacés ni marqués comme lus. Dédoublonnage par Message-ID, journal de synchro.
- **Classement** par règles configurables avec priorités ; 9 règles initiales larges. Page **Mails** (non classés, à rattacher, tous) avec aperçu isolé du HTML, classement manuel, rattachement à un article et assistant « créer une règle à partir de ce mail » (conditions et regex proposées, test, puis reclassement automatique des mails non classés). Page **Règles des mails**.
- **Fixtures** : `backend/fixtures/emails/<type>/*.eml`, avec un test paramétré sur chaque fichier. Un `.json` du même nom à côté du `.eml` permet aussi de vérifier les valeurs extraites.
- **Rapprochement des ventes** : recherche floue sur le titre extrait, bonus si le prix correspond. Rapprochement automatique s'il n'y a qu'un candidat nettement devant, signalé et annulable ; sinon la vente apparaît dans « Ventes à confirmer » (choix en un clic). La confirmation crée la Vente, passe l'article en `vendu` à la date et heure exactes du mail et crée l'Envoi.
- **Envois** : bordereau récupéré en PDF joint ou en lien ; badges « En retard », « Aujourd'hui », « Demain » ; téléchargement de tous les bordereaux fusionnés (A4 ou 10x15), qui les marque imprimés ; statuts à imprimer → imprimé → déposé → livré, avec mise à jour du statut de l'article. Le passage à « livré » se fait aussi automatiquement avec le mail de livraison. Section « Bordereaux à rattacher ».
- **Litiges** : un mail de litige passe l'article en `litige`, qui apparaît dans le header et sur l'écran du jour. Les preuves se téléchargent en zip depuis la fiche article (déjà fait à l'étape 1).
- **Messages et offres** : enregistrés dès maintenant (table `Message`) et rattachés à l'article ; leur page arrive à l'étape 3.
- **Écran du jour** : nouvelles cartes « Colis à envoyer », « Ventes à confirmer » et « Mails non classés ».

### Tests
- Backend : 96 tests (1 ignoré tant qu'aucun `.eml` réel n'est déposé). Couverture : classement et extraction sur 9 types de mails synthétiques, dates limites, cycle complet vente → bordereau → expédié → livré, litige, offre, vente ambiguë puis confirmée, annulation, rattachement manuel, distinction des couleurs au rapprochement, synchro IMAP sur un faux serveur qui refuse toute écriture, dédoublonnage, message d'erreur Gmail, chiffrement, fusion PDF et 10x15, CRUD et test des règles.
- Frontend : ESLint, Prettier, `tsc`, Vitest et build OK. Parcours manuel dans le navigateur (desktop et mobile) sans erreur console.

### À tester toi-même
1. Génère une `FERNET_KEY` (voir README), mets-la dans `.env`, puis relance `docker compose up --build`.
2. Paramètres → Mails : clique Gmail, saisis ton adresse et un mot de passe d'application, puis « Tester la connexion » et « Enregistrer ».
3. Lance « Synchroniser maintenant » et regarde ce qui est reconnu dans Mails, Ventes et Envois.
4. **Le plus utile** : dépose quelques vrais `.eml` Vinted (vente, bordereau, expédié, livré, offre, message, litige…) dans `backend/fixtures/emails/<type>/` et lance `uv run pytest tests/test_classifieur.py`. J'ajusterai les règles sur cette base.
5. Vérifie qu'un bordereau réel s'imprime bien en 10x15 sur ton imprimante.

### Décisions prises (étape 2)
- **Première synchro** : les 30 derniers jours. Ensuite, depuis la dernière synchro moins 1 jour (le dédoublonnage évite les doublons).
- **Filtre expéditeur** : `vinted` par défaut dans les règles ; `vinted.fr, vinted.com` dans la recherche IMAP (modifiable).
- **Date limite d'envoi** : celle du mail si elle est trouvée, sinon date de la vente + 5 jours ouvrés (délai Vinted).
- **Score de rapprochement** : moyenne de `token_set_ratio` et `token_sort_ratio` (sans ponctuation, sans accents), + 10 si le prix correspond à 50 centimes près. Automatique si le score est ≥ 90 avec un écart ≥ 15 sur le 2e candidat. Le score n'est plafonné qu'à l'affichage.
- **Statut de traitement** : `nouveau` = type reconnu mais action en attente (vente à confirmer, bordereau ou livraison à rattacher) ; `a_classer` = aucune règle ; `traite` ; `ignore`.
- **Bordereaux à rattacher** : rattachés par numéro de commande, sinon par titre, sinon au seul envoi sans bordereau s'il n'y en a qu'un ; sinon choix manuel.
- **Format 10x15** : la page entière est mise à l'échelle (et tournée si paysage). À ajuster (recadrage sur l'étiquette) quand j'aurai un vrai bordereau Vinted.
- **Notifications** de vente, litige et offre : branchées sur un point d'entrée unique (`services/notifications.py`), qui se contente de journaliser jusqu'à l'étape 4 (push).
- **Annulation d'une vente** impossible une fois le colis déposé.
- **Annulation d'une vente auto-rapprochée** : l'article repasse `en_ligne` et le mail revient dans « Ventes à confirmer ».
## Étape 3 : annonces et messages avec l'IA (à venir)
## Étape 4 : écran du jour et notifications push (à venir)
