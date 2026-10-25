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
