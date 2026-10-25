# Avancement

## Étape 1 : socle, import Excel, stock et compta ✅

### Fait
- **Socle** : monorepo `backend/` (FastAPI, SQLAlchemy 2, Alembic, Postgres) + `frontend/` (Next.js 15, Tailwind 4, shadcn/ui), `docker-compose.yml`, `/health`.
- **Auth** : utilisateur unique créé en CLI (`python -m app.cli create-user`), argon2, session en cookie httpOnly/SameSite=Lax de 30 jours renouvelée à l'usage, redirection vers `/login`.
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
## Étape 3 : annonces et messages avec l'IA ✅

### Fait
- **IA** : SDK Anthropic, modèle `ANTHROPIC_MODEL` (défaut `claude-haiku-5-5`), clé `ANTHROPIC_API_KEY`. Les prompts système sont dans `backend/app/prompts/` (`annonce_systeme.txt`, `reponse_message.txt`) et relus à chaque appel. La sortie JSON est imposée par schéma. Chaque erreur a un message clair en français : clé absente ou refusée, limite de débit, crédit épuisé, service surchargé, réseau, refus du modèle, réponse coupée.
- **Création d'annonce** (page Annonces, ou bouton sur la fiche article) :
  - formulaire prérempli (marque, modèle, catégorie, taille, couleur, état, matière, défauts, mesures, modèle d'annonce) ;
  - titre de 60 caractères maximum (coupé proprement si l'IA dépasse), description, mots-clés ;
  - boutons Régénérer, Copier le titre, Copier la description, Copier tout, Marquer comme publié (passe l'article en ligne avec la date et l'heure) ;
  - le prompt interdit d'affirmer une information absente de la fiche ; la fiche saisie est enregistrée sur l'article, même si l'IA échoue.
- **Prix conseillé** (backend, jamais par l'IA) : ventes de même marque et catégorie, sinon même catégorie, sinon même marque (3 ventes minimum) ; médiane, fourchette (quartiles dès 4 ventes), délai moyen, contrôle du coefficient (prix relevé si sous l'objectif) ; arrondi configurable ; raisonnement affiché. Sinon, une estimation signalée comme telle.
- **Messages et offres** : regroupés par article. Pour une offre, la décision (accepter, contre-proposer avec montant, refuser poliment) est calculée par le backend, avec la marge et le coefficient résultants ; l'IA rédige la réponse en respectant cette décision. Réponse modifiable, copiable, « marquer répondu » ou ignorer. Rien n'est jamais envoyé automatiquement.
- **Modèles** d'annonce et de réponse éditables (page Modèles), avec un jeu par défaut installé au premier démarrage.
- **Écran du jour** : carte « Messages et offres » et prix suggéré pour les articles qui traînent.

### Tests
- Backend : 123 tests. Couverture : arrondi, prix conseillé (niveaux, médiane, raisonnement, relèvement, estimation), analyse d'offre, appel IA avec un client simulé (prompt, schéma, titre coupé), mapping des erreurs, refus et clé absente, parcours annonce → publié, conservation de la fiche quand l'IA échoue, messages groupés, suggestion, CRUD des modèles, rattachement d'un message à un exemplaire en double.
- E2E Playwright : connexion → import → création d'annonce → marquer publié (backend lancé avec `IA_FACTICE=true`).

### À tester toi-même
1. Ajoute `ANTHROPIC_API_KEY` dans `.env`, relance, puis ouvre Annonces : choisis un article, complète l'état (et les défauts s'il y en a), clique « Générer l'annonce ».
2. Vérifie que la description n'invente rien (matière, authenticité…) et ajuste `backend/app/prompts/annonce_systeme.txt` si besoin.
3. Messages : clique « Suggérer une réponse » sur une offre et vérifie la marge affichée.

### Décisions prises (étape 3)
- **Effort `low`** pour les rédactions (tâches courtes : plus rapide et moins cher sur Haiku).
- **Décision sur les offres** : accepter si l'offre atteint le prix minimum (coefficient minimal, arrondi) et au moins 90 % du prix affiché ; refuser si elle est sous 70 % du minimum ; sinon contre-proposer à mi-chemin entre l'offre et le prix affiché, jamais sous le minimum.
- **Estimation sans historique** : coefficient minimal + 0,5 (soit 2,5).
- **Article qui traîne** : prix suggéré = −10 % (ou le prix conseillé s'il est plus bas), jamais sous le minimum.
- **Rattachement d'un message** : on cherche d'abord parmi les articles en ligne ; les exemplaires identiques (même nom, même prix) sont acceptés.
- **`IA_FACTICE=true`** : textes déterministes sans appel à l'API, uniquement pour la démo et les tests e2e. Ne pas activer en production.
## Étape 4 : écran du jour et notifications push ✅

### Fait
- **Écran du jour** (page d'accueil), avec des cartes cliquables :
  - colis à envoyer (aujourd'hui et en retard), ventes à confirmer, articles reçus à publier, messages et offres, mails non classés, commandes en attente ;
  - litiges ouverts, avec un bandeau rouge dès qu'il y en a un ;
  - articles en ligne depuis plus de 7 jours, avec un nouveau prix suggéré ;
  - CA, marge et ventes de la semaine comparés à la semaine précédente (arrêtée au même jour) ;
  - objectif de ventes du jour (configurable, 3 par défaut).
- **PWA** : manifeste, icônes (générées par `frontend/scripts/generer_icones.py`, dont une version « maskable » et l'icône Apple), service worker. L'app s'installe sur l'écran d'accueil.
- **Web Push** (VAPID, `pywebpush`) : nouvelle vente, nouveau litige, nouvelle offre, et rappel à 9 h (heure de Paris) des colis du jour et en retard. Chaque type peut être activé ou désactivé. Les appareils expirés (404/410) sont supprimés automatiquement. Les notifications sont envoyées après l'enregistrement du mail : un échec d'envoi ne casse jamais le traitement.
- **Paramètres → Notifications** : bouton « Activer les notifications sur cet appareil », liste des appareils abonnés, notification de test, et explication pour iPhone (le bouton reste désactivé tant que l'app n'est pas installée).
- **Qualité (section 10)** :
  - sauvegarde complète en zip (Excel + base en JSON sans secrets + fichiers du volume) ;
  - démo `python -m app.cli seed-demo` (base vide uniquement) ;
  - génération des clés `python -m app.cli vapid-keys`.

### Tests
- Backend : 132 tests. Couverture : format des clés VAPID, abonnement idempotent et notification de test, envoi après le commit sur une vente et un litige, préférences, suppression d'un abonnement expiré, rappel de 9 h, contenu de la sauvegarde (sans secrets), démo.
- Frontend : lint, types, Vitest, build. Vérification dans le navigateur (bureau et iPhone simulé) : manifeste, service worker enregistré, onglet Notifications, téléchargement de la sauvegarde, écran du jour sur la démo.

### À tester toi-même
1. `python -m app.cli vapid-keys`, puis ajoute les 3 variables et redémarre.
2. Sur ton iPhone : installe l'app sur l'écran d'accueil (sur l'URL Vercel en HTTPS), ouvre-la depuis l'icône, active les notifications et envoie une notification de test.
3. Vérifie demain à 9 h que le rappel des colis arrive (s'il y a des colis à déposer).

### Décisions prises (étape 4)
- **Pas de cache hors ligne** dans le service worker : les données doivent toujours être fraîches. Le gestionnaire `fetch` sert seulement à rendre l'app installable.
- **Rappel de 9 h** : envoyé seulement s'il y a des colis du jour ou en retard (pas de notification « rien à faire »).
- **Sauvegarde** : génération dans un fichier temporaire supprimé après le téléchargement ; les tables de session et de tentatives de connexion sont exclues, ainsi que le hash du mot de passe et le mot de passe IMAP chiffré.

## Photos IA (ajout du 21/10/2026) ✅

### Fait
- **Photos par article** (fiche article et générateur d'annonce) : 4 emplacements (devant, dos, étiquette, logo), dépôt groupé, détails, et photos de défaut publiées telles quelles. Bascule Originale / Retouchée, régénération photo par photo, zip numéroté dans l'ordre Vinted, coût affiché.
- **Retouche via Replicate**, modèle configurable (Paramètres → Photos), **Nano Banana 2** par défaut :
  - le fond est toujours la photo de tapis des paramètres ;
  - la disposition (manches, rotation, cadrage) est tirée au hasard pour chaque photo, avec la même lumière sur toute l'annonce ;
  - consigne stricte de fidélité (couleur, texte d'étiquette, logo, usure, défauts) ;
  - pour les gros plans, la photo « devant » sert de référence de couleur, et l'IA a interdiction d'élargir le cadrage.
- **Préparation des photos** (Pillow) : redressement selon l'orientation EXIF, réduction à 2048 px, conversion en JPEG et suppression de toutes les métadonnées, **dont le GPS**, avant stockage et envoi.
- **Génération en tâche de fond** avec suivi de l'avancement, limite de débit Replicate respectée (attente et nouvel essai sur une erreur 429), erreurs claires (token, crédit épuisé, délai dépassé).

### Comparatif réalisé sur tes photos (coût total des essais ≈ 0,90 $)
| Modèle | Prix / photo | Résultat |
|---|---|---|
| Nano Banana 2 | ~0,067 $ | **Le plus fidèle** : tapis respecté, vêtement identique, texte d'étiquette lisible |
| Seedream 5 Lite | ~0,035 $ | Bon sur les vues entières, mais texte d'étiquette déformé |
| FLUX.2 [dev] | ~0,02 $ | Fond inventé (moquette, fenêtre) : écarté |
| Qwen Edit Plus | ~0,03 $ | Mur et parquet ajoutés, vue de biais : écarté |

**Mise à jour : modèle par type de photo.** GPT Image 2 en qualité basse, testé ensuite sur tes photos, est aussi fidèle que Nano Banana 2 sur les vues entières, l'étiquette et le logo. Il est utilisé par défaut pour tous les types. Le bouton **HQ** d'une photo la régénère avec Nano Banana 2 quand elle ne convient pas. Les deux réglages sont modifiables type par type dans Paramètres → Photos.

| Modèle (essai du 21/10) | Prix / photo | Résultat |
|---|---|---|
| **GPT Image 2, qualité basse** | ~0,012 $ | **Fidèle partout** : vêtement, logo, étiquette (« MADE IN PAKISTAN »), tapis |
| GPT Image 2, qualité moyenne | ~0,047 $ | À peine mieux que la qualité basse sur l'étiquette |
| Nano Banana 1 | ~0,039 $ | Correct, mais tache de lumière artificielle |
| FLUX.2 klein | ~0,002 $ | **A inventé une fermeture éclair** et une fenêtre : écarté |

Coût estimé : **~0,05 $ par article** (4 photos), soit ~5 $ pour 100 articles, régénérations HQ occasionnelles en plus. Replicate facture GPT Image 2 par image produite selon la qualité (métriques « model_variant: low ») : vérifie le montant réel sur ta facture Replicate après quelques jours.

### Points de vigilance
- Les tout petits textes d'étiquette (tableau des tailles) peuvent être approximatifs : **toujours comparer avec l'original avant de publier**.
- Lors d'un essai, l'IA a inventé un col sur un gros plan de hoodie ; la consigne interdit maintenant d'élargir le cadrage. La relecture reste indispensable.
- Les photos de défaut ne sont jamais envoyées à l'IA.

### Décisions prises
- **Résolution 1K** (896 × 1200) : prix de base, suffisant pour Vinted.
- **Fond de démarrage** : sans photo du tapis seul, une version « tapis vide » a été générée à partir de ton exemple réussi. Remplace-la par une vraie photo du tapis pour un rendu encore plus juste.
- **Article de test** « Hoodie Adidas Originals - gris (test photos) » créé en local : à supprimer.
- `httpx` passé en dépendance de production (il manquait dans l'image Docker : attrapé au premier démarrage).

## Plusieurs comptes Vinted (ajout du 21/10/2026) ✅

### Fait
- **Une boîte mail par compte Vinted** (Paramètres → Mails) : ajout, modification, test de connexion, pause et débranchement. La boîte déjà configurée devient « Compte 1 » à la migration.
- **Synchro** : toutes les boîtes actives, l'une après l'autre, avec un journal par boîte.
- **Mails** : chaque mail garde le compte qui l'a reçu (badge et filtre dans Mails, badge dans Ventes à confirmer).
- **Articles** : champ « Compte Vinted » (fiche, création, action groupée, filtre du stock).
- **Rapprochement** : une vente reçue sur un compte n'est rapprochée qu'avec les articles de ce compte ou ceux pas encore attribués. Une vente confirmée attribue le compte à l'article.

- **Relecture de l'historique** : la première synchro d'une boîte remonte jusqu'au premier achat du stock (moins 15 jours, 30 jours au minimum). Bouton « Relire tout l'historique » par boîte.
- **Ventes importées de l'Excel** (vendues, date estimée, sans vente enregistrée) : un mail de vente qui leur correspond remplace la date estimée par la vraie date et heure, et enregistre prix, acheteur et n° de commande. L'article reste vendu ; les mails d'expédition et de livraison qui suivent mettent l'envoi à jour. Annuler restaure la date estimée.
- Pas de notification push pour les mails de plus de 2 jours (relecture de l'historique).
- Un article acheté après la date du mail de vente est écarté du rapprochement.

### Décisions prises
- Un article vendu importé et un exemplaire identique encore en ligne : la vente part dans « à confirmer » plutôt que d'être attribuée au hasard.
- Le filtre et les badges n'apparaissent qu'à partir de 2 comptes, pour ne pas charger l'écran avec un seul compte.
- Débrancher une boîte conserve ses mails, ventes et articles (le lien vers le compte est retiré).
- Les expéditeurs Vinted lus restent communs à toutes les boîtes.
- La compta reste globale (pas de découpage par compte pour l'instant).

## Nouvelle annonce depuis les photos (ajout du 21/10/2026) ✅

### Fait
- **Stock → Nouvelle annonce** : on dépose toutes les photos de l'article (12 max, dans n'importe quel ordre).
- **Une seule requête à Claude (vision)** : type de chaque photo (devant, dos, étiquette, logo, défaut, détail), fiche lue sur l'étiquette (marque, taille, matière), catégorie, couleur, état, défauts visibles, titre, description, mots-clés et prix estimé. Environ 5 à 10 s.
- **Retouche des photos lancée aussitôt** en tâche de fond (sauf les photos de défaut, jamais retouchées).
- **Style du vendeur** : description de 2-3 lignes simples (exemples fournis), titres calés sur les vrais titres Vinted vendus (mails), prix calé sur les vraies ventes. Consignes communes dans `prompts/style_annonce.txt`.
- **Provenance** : article déjà au stock (suggestions par marque, taille et ressemblance ; l'annonce fusionne avec lui), nouvel article d'un batch (avec prix d'achat), ou **pièce perso** (achat 0 €, hors batchs).
- **Éditeur** : « Autre titre », « Autre version », « Plus court » ne régénèrent que la partie demandée ; copie du titre et de la description ; « Télécharger pour Vinted » (photos numérotées dans l'ordre) ; « Publié sur Vinted ».
- **Ventes à confirmer → Pièce perso** : crée l'article depuis le mail (0 € d'achat), confirme la vente et applique ses mails de suivi.

### Décisions prises
- Le prix de l'IA ne sert que s'il n'y a pas assez de ventes comparables : il est affiché comme « Proposé par l'IA ».
- La provenance est demandée avant « Publié sur Vinted » pour qu'aucune marge ne soit faussée.
- Pièce perso : coût 0 €, donc toute la vente est de la marge ; elle reste dans le CA et la compta (pas encore séparée dans l'export URSSAF : à décider).
- Vinted n'a pas d'API de publication : la mise en ligne reste un copier-coller, réduit au minimum.

## État général

Les 4 étapes du cahier des charges sont faites. Ce qui reste à valider avec tes vraies données :
1. **Mails Vinted réels** : dépose des `.eml` dans `backend/fixtures/emails/<type>/`. Les règles initiales sont des suppositions, testées seulement sur des mails synthétiques.
2. **Bordereaux réels** : le format 10x15 met la page entière à l'échelle ; il faudra peut-être recadrer sur l'étiquette.
3. **Notifications sur iPhone** : nécessitent l'URL HTTPS (Vercel) et l'app installée.
4. **Qualité des textes de l'IA** : à juger sur tes articles, puis ajuster les prompts dans `backend/app/prompts/`.

## Mise en ligne et notifications détaillées (ajout du 23/10/2026) ✅

### Fait
- **Production** : backend sur Railway (projet `vinted-manager` : service `backend`, Postgres, volume `/data`), front sur Vercel : https://vinted-manager-gamma.vercel.app (`vinted-manager.vercel.app` appartient à quelqu'un d'autre). Déploiement : `railway up ./backend --path-as-root --service backend` et `vercel deploy --prod` depuis `frontend/` (pas de déploiement automatique sur push).
- **Notifications push détaillées** :
  - offre : « 💰 Offre de 30 € sur <article> », avec prix affiché, écart en %, conseil (accepter, contre-proposer + montant, refuser) et pseudo ;
  - message : « 💬 Message de <pseudo> » ;
  - favori (nouveau type de mail) : « ❤️ Nouveau favori », article et prix ;
  - vente : prix et acheteur ;
  - filet de sécurité : un mail Vinted qu'aucune règle ne reconnaît envoie « Mail Vinted non reconnu » ;
  - chaque type peut être coupé dans Paramètres → Notifications.
- Règles par défaut en version 4 : la règle des favoris extrait le titre, l'offre « Commande mise à jour » extrait le pseudo.

### À vérifier avec les vrais mails
- Le format exact des mails de favori et de message n'a pas encore été vu : à contrôler après la première synchro en production.
- **Connexion** : plus de blocage après plusieurs échecs (retiré le 23/10/2026). Les messages d'erreur disent précisément ce qui ne va pas : aucun compte créé, email inconnu (l'adresse saisie est rappelée) ou mot de passe incorrect, avec la commande à lancer pour corriger. Les tentatives restent journalisées.

## Lecture des mails en temps réel (ajout du 23/10/2026) ✅

- **Écoute IMAP IDLE** (`services/imap_idle.py`) : une connexion en lecture seule par boîte active ; Gmail prévient dès qu'un mail arrive et la synchro part aussitôt (notification en ~10 s). Connexion renouvelée toutes les 9 min, reconnexion automatique après une erreur (30 s → 5 min), écoutes vérifiées chaque minute (boîte ajoutée, modifiée, mise en pause). `ECOUTE_TEMPS_REEL=false` la coupe.
- **Synchro planifiée toutes les minutes** en production (`INTERVALLE_SYNCHRO_MINUTES=1`), filet de sécurité si l'écoute tombe. Les mails déjà connus ne sont plus retéléchargés : seul leur en-tête Message-ID est relu.
- **Journal de synchro** : nettoyé chaque nuit (7 derniers jours conservés).

# Extension d'automatisation Vinted (branche `extension-vinted`, spécification `SPEC_EXTENSION.md`)

Développée en autonomie le 25/10/2026, phase par phase (un commit par phase). Aucun appel réel à Vinted : tout est
testé contre les captures anonymisées de `extension/tests/fixtures/vinted/` (copie de `fixtures/vinted/`).

**Point de départ** : la branche part de `main` **plus** le travail non commité présent dans l'arbre de `main` le
25/10 (écoute IMAP IDLE, notifications détaillées), recopié à l'identique dans un premier commit pour partir de l'état
déployé. `main` n'a pas été touchée ; la branche vit dans un worktree séparé (`../vinted-manager-extension`).

## Phase 1 : socle de l'extension et brouillons automatiques ✅

### Fait
- **Comptes Vinted** : `vinted_user_id` (attendu), jeton d'extension hashé (SHA-256, comparé en temps constant),
  dernière activité et version de l'extension, `telegram_chat_id`, `pause` (+ raison), réglages JSON. Boîte mail
  facultative : la synchro IMAP et l'écoute ignorent les comptes sans boîte ; « Débrancher » une boîte garde un compte
  piloté par l'extension.
- **Article** : `vinted_item_id`, `vinted_draft_id`, `brouillon_statut` / `brouillon_erreur` / `brouillon_cree_le`,
  `prix_initial`, `prix_plancher` (82 %), `couleur_a_verifier`, `ai_photo_declare`, `importe_vinted`. Migration
  `c4a1e7d2f950` (vérifiée : upgrade, `alembic check`, downgrade).
- **Routes de l'extension** (`/api/extension/…`, en-tête `X-Extension-Token`) : `compte`, `heartbeat`,
  `brouillons/suivant`, `photos/{id}` (JPEG publié, seulement pour un article du compte), `brouillons/{id}/resultat`,
  `arret`, `pause`, `reprendre`.
- **Brouillon** : article du compte, « reçu à publier », titre + description + prix, photos terminées ; 6 par jour et
  par compte (réglable), de 8 h à 23 h (Paris), un seul à la fois. Charge utile complète (`condition_id`,
  `package_size_id`, `ai_photo`, photos dans l'ordre du zip).
- **Complétude** : devant, dos, étiquette et 5 photos au total, sinon refus (« Photo manquante : dos. ») avec
  notification ; « Relancer le brouillon » sur la fiche article.
- **Fidélité des photos** : « Première photo réelle » (Paramètres → Photos, activé par défaut) ; contrôle de couleur
  ΔE (Lab, zone centrale) entre original et retouche, au-delà de 10 brouillon bloqué jusqu'à « Couleur fidèle » sur la
  photo. `ai_photo = true` dès qu'une photo publiée est générée.
- **Style** : les deux exemples de Lucas ajoutés à `prompts/style_annonce.txt`.
- **Extension** (`extension/`, Manifest V3, TypeScript strict, esbuild, Vitest, sans framework) :
  client Vinted unique (`src/vinted/client.ts`), création du brouillon pas à pas comme le site (photos une par une
  2 à 5 s d'écart, catégorie suggérée, attributs, taille, marque, couleur, matière, brouillon), contrôle du compte
  connecté avant chaque lot, arrêt sur 401/403/429/captcha/réponse non JSON, jamais de nouvel essai. Service worker :
  alarme de 30 s, signal de vie chaque minute, au plus un brouillon toutes les 5 min + 0 à 120 s. Popup (compte,
  état, brouillons x/6, dernière action, Pause/Reprendre) et page d'options (URL du backend, jeton).
- **App** : Paramètres → **Automatisation** (comptes, jeton affiché une seule fois, compte Vinted attendu avec
  « C'est bien ce compte », pause, journal de l'extension) ; bloc **Vinted** sur la fiche article.

### Tests
- Backend : 22 nouveaux tests (`tests/test_extension_brouillons.py`), dont les 5 tests de réception : brouillon
  complet, article de la sœur jamais servi au profil de Lucas, refus sans dos avec notification, 7ᵉ demande du jour
  refusée, 403 → pause. 204 tests au total, ruff et mypy OK.
- Extension : 36 tests Vitest. Le brouillon envoyé est **identique à la capture du site** (`drafts_create.json`) ;
  403, 401, 429, captcha (HTML et DataDome JSON), réponse non JSON, mauvais compte (aucune écriture), taille et marque
  introuvables, cadence du service worker. `tsc` strict OK.
- Frontend : lint, types, Vitest et build OK.

### Décisions prises (phase 1)
- **Compte Vinted attendu obligatoire** : sans `vinted_user_id` confirmé, aucune action. L'extension remonte le compte
  vu dans le profil ; Lucas le confirme d'un clic (ou saisit l'identifiant).
- **Quota** : chaque brouillon demandé compte, réussi ou non (chaque essai agit sur Vinted).
- **Article sans aucune photo dans l'app** : simplement ignoré (pas de notification), pour ne pas alerter sur les
  articles publiés à la main.
- **Brouillon resté « en cours » 30 min** sans résultat : passé en erreur (« vérifie les brouillons sur Vinted avant de
  relancer »), jamais relancé automatiquement.
- **Couleur** : toutes les photos publiées en version retouchée sont contrôlées ; une photo non mesurable bloque aussi ;
  une régénération remet le contrôle à zéro.
- **Recadrage de la première photo** : au format 3:4 seulement s'il retire au plus 25 % de l'image (on ne coupe jamais
  un vêtement photographié en paysage).
- **Taille du colis** : 1 pour t-shirt, top, débardeur, polo, maillot, chemise, bonnet, casquette, chaussettes,
  ceinture ; 2 sinon (dont vestes et catégorie inconnue).
- **Plancher** = 82 % du prix initial **arrondi aux 50 centimes supérieurs** (jamais sous 82 %).
- **Marque** : celle de la fiche prime (titre exact dans les suggestions puis la liste de la catégorie) ; la marque
  proposée par Vinted n'est reprise que si la fiche n'en a pas (ou porte le même nom). Sinon : erreur, jamais une autre
  marque.
- **Couleur et matière** : suggestion de Vinted d'abord (comme le site), correspondance avec la fiche sinon.
- **Éligibilité** (`offline_verification/eligibility`) non appelée : facultative, un appel de moins.
- **Attribut obligatoire inconnu** dans une catégorie : erreur, pas de brouillon partiel.
- `users/current` relu au plus toutes les 5 min pour le signal de vie, et systématiquement avant chaque brouillon. Son
  format (`{"user": {"id", "login"}}`) n'a pas de capture : à confirmer au premier lancement.
- **Pause / Reprendre de la popup** = pause du compte dans vinted-manager ; « Reprendre » vaut reprise manuelle.
- URL du backend autre que `localhost:8000` : l'accès est demandé à l'enregistrement des options
  (`optional_host_permissions`).
- TypeScript 5 (comme le frontend) pour l'extension.

### À tester toi-même (phase 1, sur le compte Vinted **secondaire**)
1. Déployer la branche (la migration s'applique au démarrage).
2. `cd extension && npm install && npm run build`, puis Chrome → `chrome://extensions` → mode développeur →
   « Charger l'extension non empaquetée » → dossier `extension/dist`, dans le profil Chrome du compte de test.
3. Paramètres → Automatisation : « Générer un jeton d'extension », le coller dans les options de l'extension avec
   l'URL du backend (celui qui a tes données : Railway en production, ou `http://localhost:8000`).
4. Ouvrir un onglet www.vinted.fr connecté au compte de test ; dans la minute, la popup affiche le compte : cliquer
   « C'est bien ce compte » dans Paramètres → Automatisation.
5. Préparer un article de test attribué à ce compte (reçu à publier, annonce, prix, photos devant, dos, étiquette et
   5 au total) et attendre au plus ~7 min : vérifier le brouillon sur Vinted (ordre des photos, première photo réelle,
   titre, description, prix, catégorie, marque, taille, état, couleur, déclaration IA).
6. Vérifier qu'un article sans photo de dos est refusé (notification) et qu'un article de l'autre compte n'est pas pris.

## Phase 2 : pilotage ✅

### Fait
- **File de tâches générique** (`tache_vinted`, `services/taches.py`, `services/file_vinted.py`) : types de la
  spécification (+ `photos_reference` pour la phase 5), priorités 1 à 5, `executer_apres`, statuts `a_valider`
  (attend Lucas), `a_faire`, `en_cours`, `faite`, `erreur`, `annulee`, clé d'unicité (jamais deux fois la même
  action). Routes `GET /api/extension/taches/suivante`, `POST /api/extension/taches/{id}/resultat`,
  `POST /api/extension/evenements`. Les brouillons passent par la file ; les routes de la phase 1 restent
  (compatibilité des tests).
- **Règles de distribution** : une tâche à la fois par compte ; la nuit, seules les réponses aux acheteurs (messages
  et offres reçues) ; 20 à 60 s entre deux actions non urgentes ; un module coupé laisse ses tâches en file ;
  tâche sans résultat après 20 min → erreur, jamais relancée.
- **Budget d'actions** (réglable) : 40 republications, 60 offres, 120 messages, 6 brouillons par jour, 15 actions
  par heure. Dépassement : action reportée à l'heure suivante ou au lendemain (étalée) ; les réponses aux acheteurs
  ignorent le plafond horaire.
- **Arrêts automatiques** : réponse inattendue (401, 403, 429, captcha, non JSON), 3 erreurs Vinted consécutives,
  session expirée (avec la marche à suivre), budget journalier dépassé par une réponse → compte en pause, alerte,
  reprise manuelle uniquement. **Arrêt d'urgence** : interrupteur global, modules par compte, pause par compte,
  `/stop` sur Telegram.
- **Telegram** (`services/telegram.py`) : `TELEGRAM_BOT_TOKEN`, relevé `getUpdates` toutes les 5 s (pas de
  webhook), appairage par code à 6 chiffres (`/start <code>`), commandes `/stop`, `/reprendre`, `/etat`, boutons
  Envoyer / Modifier / Ignorer sur les propositions de l'assistant. Alertes : arrêt, session expirée, mauvais compte,
  hors ligne, brouillons prêts, erreurs, vente et litige (mails). Silencieuses la nuit. Sans token : rien n'est
  envoyé, sans erreur. Les notifications push restent en place.
- **Surveillance** : signal de vie chaque minute (avec « onglet Vinted ouvert ») ; sans signal pendant 5 min, ou
  onglet fermé depuis 5 min → une alerte, puis « de nouveau en ligne » au retour.
- **Réglages par compte** (JSON, valeurs par défaut de la spécification, validation des bornes) : heures actives,
  modules, budget, brouillons, assistant, prix, favoris, republication, après-vente, types d'alertes.
- **App** : Paramètres → Automatisation : interrupteur général, réglages par compte (panneau latéral), Telegram
  (code d'appairage), budget du jour, actions en attente (valider, corriger, ignorer), journal.
- **Extension** : boucle générique sur la file du backend (le backend décide du rythme), signal « onglet ouvert »,
  exécuteurs par type, distinction erreur Vinted / contrôle de l'extension ; vérification Prettier ajoutée.

### Tests
- Backend : 22 nouveaux tests (`tests/test_pilotage.py`) avec un faux client Telegram : priorités, nuit,
  interrupteurs, unicité, tâche perdue, 3 erreurs consécutives, arrêt sur réponse inattendue, plafonds horaire et
  journalier, appairage, commandes, boutons, validation depuis l'app, absence de token, alertes silencieuses et
  filtrées, vente relayée au bon chat, hors ligne, onglet fermé, réglages. 226 tests au total.
- Extension : 37 tests (file générique, arrêt, pause, onglet fermé). Migration `d7b3f0a9c214` vérifiée.

### Décisions prises (phase 2)
- **Offres reçues la nuit** : traitées comme des réponses aux acheteurs (délai de 5 à 15 min), car l'assistant les
  inclut dans le même délai de nuit. Les relances de favoris, elles, attendent 8 h.
- **Plafond journalier atteint par une réponse à un acheteur** : arrêt du compte (120 messages ou 60 offres dans la
  journée est anormal) plutôt que de laisser un acheteur sans réponse sans prévenir.
- **Erreurs consécutives** : seules les erreurs renvoyées par Vinted comptent ; un refus d'un contrôle de l'extension
  (taille introuvable, mauvais compte…) ne compte pas et n'interrompt pas la série.
- **Chaque action commencée compte dans le budget**, réussie ou non.
- **Écart de 20 à 60 s** entre deux actions non urgentes d'un même compte (en plus des délais propres à chaque
  module) : jamais de rafale, même à 8 h quand la file de la nuit se vide.
- **Brouillons** : la cadence (5 min + 0 à 120 s) est désormais gérée par le backend.
- **Alertes Telegram la nuit** : envoyées sans son.
- **Débrancher la boîte mail** d'un compte piloté garde le compte.

### À tester toi-même (phase 2)
1. Créer le bot avec @BotFather, mettre `TELEGRAM_BOT_TOKEN` dans `.env` (ou dans les variables Railway), redémarrer.
2. Paramètres → Automatisation → « Relier Telegram » sur chaque compte, envoyer `/start <code>` au bot depuis le
   téléphone de la personne concernée (ta sœur pour son compte).
3. Envoyer `/etat`, puis `/stop` et vérifier que la popup de l'extension passe en pause ; `/reprendre`.
4. Fermer Chrome 6 minutes : une alerte « hors ligne » doit arriver, puis « de nouveau en ligne » à la réouverture.

## Phase 3 : assistant (messages et offres reçues) ✅

### Fait
- **Lecture du dressing** (`services/dressing.py`, événement `dressing`) toutes les 30 min et au démarrage, toutes
  les pages : rattachement par `vinted_item_id`, brouillon publié (même identifiant), titre exact, puis recherche
  floue des mails (marque et taille contrôlées) ; sinon article « importé de Vinted » (en ligne, signalé). Prix
  affiché, `prix_initial`, plancher, vues, favoris et URL des photos enregistrés ; un article « reçu à publier »
  passe en ligne. Brouillons ignorés.
- **Surveillance de la messagerie** : l'onglet relève les compteurs de non-lus toutes les 15 à 30 s (5 min la nuit)
  et prévient le service worker quand ils augmentent ; la messagerie est aussi relue toutes les 5 min par sécurité.
  Le backend garde le point de reprise par conversation (date et identifiants des messages traités) et répond quelles
  conversations lire (5 au plus par passage).
- **Offres reçues** (`offres.decider_vinted`, règles déterministes) : acceptation dès 90 % du prix affiché ou au
  niveau de la dernière proposition ; refus sous 50 % avec message poli de l'IA ; sinon contre-offre à mi-chemin,
  arrondie aux 50 centimes, jamais sous le plancher (82 % du prix initial) ni au-dessus de la précédente ; au plancher,
  renvoyé une fois puis escalade Telegram (Envoyer = accepter / Ignorer).
- **Messages** : réponse de l'IA d'après la fiche seule (prompt et schéma étendus : intention, réponse, escalade,
  raison, montant proposé). Escalade (tâche « à valider » + Telegram avec Envoyer / Modifier / Ignorer) si l'IA a un
  doute, si l'intention est lot ou suspect, et **toujours** (filet de sécurité sans l'IA) pour paiement ou contact
  hors Vinted, litige ou retour, lot, mesures absentes de la fiche, article non rattaché, IA indisponible.
  Prix proposé dans un message → mêmes règles, réponse par une offre vendeur ou par un texte de refus.
- **Délais** : 20 à 60 s en journée, 5 à 15 min la nuit. Un nouveau message remplace la réponse en attente ; une
  réponse faite à la main sur Vinted l'annule.
- **Extension** : exécuteurs `repondre_message` (nouvelle API de messagerie), `accepter_offre`, `refuser_offre`
  (refus puis message 3 à 8 s après), `contre_offre` (limites `seller_options` vérifiées avant l'envoi) ; lectures
  réduites au nécessaire avant d'être transmises (ni photos ni avatars).

### Tests
- Backend : 32 nouveaux tests (`tests/test_assistant.py`) sur les captures réelles (inbox, conversation, dressing) :
  table des règles d'offre, négociation complète jusqu'à l'escalade, acceptation, refus, offres déjà traitées,
  réponses, 5 cas d'escalade obligatoire, escalade demandée par l'IA, prix dans un message, IA indisponible, nuit,
  remplacement et annulation des réponses, article inconnu, mémorisation de la dernière contre-offre, dressing.
  258 tests au total. Migration `e1c5a8b3d702` vérifiée.
- Extension : 55 tests (lectures réduites, pagination du dressing, réponse, acceptation, refus + message, contre-offre
  dans et hors limites, mauvais compte, compteurs de non-lus, orchestration du service worker).

### Décisions prises (phase 3)
- **Première lecture de la messagerie** : rien d'antérieur n'est traité (aucune réponse à d'anciens messages).
- **Offre et texte dans le même passage** : l'offre est traitée, le texte n'appelle pas de réponse séparée (une seule
  action vers l'acheteur).
- **Offre acceptée par contre-offre** (prix proposé dans un message) : offre vendeur au montant demandé, sans texte.
- **Contre-offre** : envoyée seule (Vinted l'affiche dans la conversation), sans message en plus.
- **Message de refus** : rédigé par l'IA ; si l'IA est indisponible, texte fixe poli.
- **Aucune lecture de Vinted quand le compte est en pause** ou l'automatisation coupée ; la surveillance des non-lus
  s'arrête d'elle-même 2 min après la dernière consigne du service worker.
- **Dressing** : une annonce fermée (vendue) sans article correspondant n'est pas importée ; le prix et le statut ne
  sont mis à jour que pour un article reçu ou en ligne ; une disparition n'est déduite que d'une lecture complète.
- Montants envoyés à Vinted au format « 6.5 » (point décimal, sans zéro inutile).

### À tester toi-même (phase 3, compte secondaire)
1. Laisser tourner l'extension, puis depuis un autre compte : envoyer un message simple (« toujours dispo ? ») →
   réponse automatique en 20 à 60 s ; un message avec « PayPal » → alerte Telegram avec les boutons.
2. Faire une offre à 50 % puis à 70 % du prix → refus poli, puis contre-offre ; vérifier les montants.
3. Vérifier dans Paramètres → Automatisation → Journal que les annonces du dressing sont rattachées ou importées
   (et compléter le coût d'achat des articles importés).

## Phase 4 : favoris (message et offre en moins d'une minute) ✅

### Fait
- **Détection** : quand le compteur de notifications augmente (relevé toutes les 15 à 30 s), et toutes les 5 min par
  sécurité, l'extension lit la liste des notifications : `api.vinted.fr/inbox-notifications/v1/notifications`
  d'abord, puis `www.vinted.fr/web/gateway/inbox-notifications/v1/notifications` ; celle qui répond est mémorisée
  et journalisée. Un 404 n'arrête pas le compte (route absente, pas un blocage).
- **Backend** (`services/favoris.py`, table `favori_vinted`) : un favori par membre et par annonce (contrainte
  d'unicité), relance programmée 20 à 60 s après (réglable) ; la nuit, à partir de 8 h si le favori a moins de 12 h.
  Offre = prix affiché − 10 % (réglable), arrondie aux 50 centimes, jamais sous le plancher ; pas de relance si aucune
  réduction n'est possible. Message tiré au hasard parmi les variantes, avec `{prenom}` (pseudo, ou rien),
  `{article}`, `{prix}` (montant de l'offre) ; message par défaut de la spécification.
- **Extension** : contrôle du compte (sans cache), page `want_it` ouverte dans l'**onglet de travail** (en
  arrière-plan, réutilisé), conversation lue dans l'URL `/inbox/{id}` (15 s au plus), `transaction_id` lu dans la
  conversation (méthode simple de la spécification), message puis offre 2 à 5 s après (limites `seller_options`
  vérifiées), retour de l'onglet de travail sur le dressing. Redirection vers une page de connexion ou de vérification
  → arrêt du compte.
- **Après la relance**, la conversation est enregistrée avec l'offre envoyée comme dernière proposition : si le membre
  négocie, l'assistant repart de là.

### Tests
- Backend : 10 nouveaux tests (`tests/test_favoris.py`) : relance en moins d'une minute, unicité membre/article,
  première lecture, notification ordinaire, format inexploitable signalé une fois par jour, nuit et limite de 12 h,
  plancher, module coupé, article inconnu, variables du message, extraction, résultat (conversation enregistrée,
  budget : un message et une offre par relance). 268 tests au total. Migration `f3d9b2c6e815` vérifiée.
- Extension : 65 tests (bascule d'adresse des notifications, mémorisation, relance complète, mauvais compte sans
  navigation, absence de redirection, redirection vers la connexion, offre refusée après le message).

### Décisions prises (phase 4)
- **Format des notifications non capturé** : extraction tolérante (texte contenant « favori », identifiant de
  l'annonce dans le lien ou `subject_id`, membre dans le lien ou `sender_id`/`user_id`, jamais le compte lui-même).
  Notification inexploitable : aucune relance, journal, et une alerte par jour au plus pour demander une capture.
- **Première lecture des notifications** : rien d'antérieur n'est relancé.
- **`{prix}`** = le montant de l'offre proposée.
- Les relances de favoris ne partent jamais la nuit (pas une réponse à un acheteur).
- La lecture des notifications ne se fait que si le module favoris est actif.

### À tester toi-même (phase 4, compte secondaire)
1. Depuis un autre compte, mettre un article en favori : dans la minute, une conversation s'ouvre avec le message et
   une offre à −10 %. Vérifier que l'onglet de travail (en arrière-plan) revient ensuite sur le dressing.
2. Dans Paramètres → Automatisation → Journal, noter quelle adresse de notifications a répondu (« Liste des
   notifications lue via api » ou « via www »).
3. Si l'alerte « Favoris non exploitables » arrive : capturer la liste des notifications (DevTools → Réseau →
   `notifications?page`) et me l'envoyer pour ajuster l'extraction.

## Phase 5 : republication différenciée ✅

### Fait
- **Planification** (`services/republication.py`, toutes les 30 min, heures actives) : article en ligne depuis
  5 jours (réglable) depuis la dernière publication ; au plus une republication programmée à la fois par compte,
  0 à 20 min plus tard (jamais en rafale, budget de 40 par jour). Reportée si un message a été échangé sur l'article
  il y a moins d'une heure (contrôle refait au moment de partir : report de 30 min). Une offre en attente ne bloque
  pas.
- **Avant la suppression** : une offre (relance) part aux membres de l'historique des favoris qui n'en ont pas reçu ;
  la republication attend que ces relances soient faites.
- **Photos** (Pillow, côté backend) : toujours à partir des photos publiées la première fois ; rotation de 1,5 à 2,5°
  (sens alterné d'une republication à l'autre), zoom de 4,5 à 5,5 % (relevé si besoin pour qu'aucun coin vide ne
  reste), luminosité −2 à −5 %, JPEG qualité 85 à 92 sans métadonnées. La première photo garde une couleur
  imperceptiblement différente (ΔE ≤ 3, sinon baisse de luminosité réduite).
- **Annonce importée sans photo** : tâche `photos_reference` — l'extension télécharge une fois les photos de
  l'annonce (CDN `*.vinted.net`, sans cookie) et le backend les garde comme référence.
- **Texte** : nouveau prompt `prompts/reecriture_annonce.txt` ; marque, taille, état, défauts, matière et mots-clés
  vérifiés automatiquement ; deux essais, sinon l'annonce actuelle est reprise telle quelle.
- **Extension** : contrôle de l'ancienne annonce (`GET /api/v2/items/{id}` : vendue, réservée ou fermée → annulé),
  nouveau brouillon avec les photos transformées, publication (`completion`, `push_up: false`), puis suppression de
  l'ancienne, dans cet ordre. Échec après une étape faite : le résultat partiel remonte (brouillon créé, ou nouvelle
  annonce publiée mais ancienne non supprimée → alerte « supprime-la à la main »).
- **App** : vues, favoris et nombre de republications sur la fiche article ; plages de transformation réglables.

### Tests
- Backend : 13 nouveaux tests (`tests/test_republication.py`) : zoom nécessaire, plages tirées, coins sans vide,
  absence de métadonnées, fidélité de la première photo sur trois teintes, vérification du texte, repli sur l'annonce
  actuelle, cadence, nuit, report pour conversation récente (à la planification et au départ), offres aux favoris
  d'abord, annonce importée (téléchargement des photos), réussite, ancienne non supprimée, échec. 281 au total.
- Extension : 71 tests (ordre brouillon → publication → suppression, corps de publication conforme à la capture,
  annonce réservée, publication refusée, suppression refusée, photos de référence).

### Décisions prises (phase 5)
- **Republication d'une annonce importée** : `ai_photo = true` faute de savoir si ses photos étaient générées (on ne
  déclare jamais `false` sans le savoir) ; description inconnue → pas de republication (journal) tant que la fiche
  n'est pas complétée.
- **Réécriture refusée deux fois** : on republie avec le texte actuel plutôt que de bloquer.
- **Brouillon orphelin** (publication refusée) : laissé sur Vinted et signalé, jamais supprimé automatiquement.
- Le sens de rotation alterne d'une republication à l'autre ; les paramètres tirés sont gardés dans la tâche.

### À tester toi-même (phase 5, compte secondaire)
1. Réduire la cadence à 1 jour (Paramètres → Automatisation → Réglages → Republication) sur le compte de test,
   attendre la republication : nouvelle annonce publiée, ancienne supprimée, photos légèrement différentes.
2. **Point de vigilance de la spécification** : comparer vues et favoris (fiche article → bloc Vinted) avant et après
   quelques republications pour mesurer l'efficacité des transformations.

## Phase 6 : baisse de prix automatique ✅

### Fait
- **Backend** (`services/baisse_prix.py`, toutes les heures) : −5 % (réglable) une seule fois par article, entre 48 et
  72 h après la publication (délai propre à chaque article, tiré dans la plage), arrondi aux 50 centimes, jamais sous
  le plancher, jamais après une republication. Tâche `modifier_prix` (priorité 5) avec le prix attendu et le nouveau
  prix ; le prix de l'article est mis à jour au résultat (ancien prix gardé).
- **Extension** : relecture de l'annonce (`GET /api/v2/items/{id}`), contrôle du prix actuel (modifié à la main
  entre-temps → rien n'est fait), reconstruction de l'objet `item` **complet** (même forme que la capture du site),
  puis `PUT /api/v2/item_upload/items/{id}` avec un nouveau `temp_uuid` et `push_up: false`.
- **Champ manquant** à la relecture : aucun `PUT`, la tâche passe en erreur, le module « prix » est coupé pour ce
  compte et Lucas reçoit la marche à suivre (capture de la page d'édition, section 13.5).
- Fiche article : « Baisse auto : 30 € → 28,50 € ».

### Tests
- Backend : 7 nouveaux tests (`tests/test_baisse_prix.py`) : échéance 48–72 h, une seule fois, trop tôt, trop tard,
  après une republication, annonce importée, plancher, module coupé, résultat (prix mis à jour, module coupé sur
  champ manquant). 288 tests au total. Migration `b8f2d5a1c463` vérifiée.
- Extension : 76 tests, dont l'objet reconstruit **identique à la capture `items_update`** (au prix et au
  `temp_uuid` près), champs manquants, prix modifié entre-temps.

### Décisions prises (phase 6)
- **Fenêtre stricte** : un article publié il y a plus de 72 h (+ 24 h de rattrapage si le PC était éteint) n'est pas
  baissé : pas de baisse en masse des articles déjà en ligne au démarrage.
- **Annonces importées de Vinted** : date de publication inconnue → pas de baisse automatique.
- **« Pas de nouvelle baisse après une republication »** : un article déjà republié n'est jamais baissé.
- Une baisse impossible (déjà au plancher) compte comme faite : l'article n'est plus examiné.
- **Reconstruction** : `isbn`, mesures, `manufacturer`, `manufacturer_labelling` (toujours nuls dans les captures
  de vêtements) sont repris s'ils sont présents, nuls sinon ; `ai_photo` vient de vinted-manager (déclaration faite
  au brouillon) ou de l'annonce lue, sinon champ manquant. Les autres champs sont obligatoires.

### À tester toi-même (phase 6, compte secondaire)
1. Sur une annonce de test publiée par l'app, attendre 48 à 72 h (ou, pour aller plus vite, réduire
   « Après (heures) » dans les réglages Prix) : soit le prix baisse sur Vinted, soit l'alerte « Baisse de prix
   automatique coupée » arrive avec le nom du champ manquant.
2. Dans ce second cas, capturer le chargement de la page d'édition d'une annonce (DevTools → Réseau, « Conserver le
   journal », « Save all as HAR ») et me l'envoyer.
