# Spécification : extension d'automatisation Vinted pour vinted-manager

Version du 25/10/2026, toutes routes capturées. Document unique à donner à Claude Code. Il remplace `BRIEF_EXTENSION_V1.md` et `VINTED_API.md`.

## 0. Mode d'emploi pour Claude Code : développement en autonomie

Ce document est conçu pour que tu développes **toutes les phases sans poser de question à Lucas**. Toutes les décisions produit sont prises (section 2), toutes les routes Vinted sont capturées (section 13) et des réponses réelles anonymisées sont fournies dans `fixtures/vinted/`.

### 0.1 Lecture préalable
Ce document en entier, puis `PROGRESS.md` (décisions existantes et conventions), `backend/app/models/stock.py`, `backend/app/models/systeme.py` (dont `Parametres` et `CompteVinted`), `backend/app/services/photos.py`, `backend/app/services/offres.py`, `backend/app/services/ia.py`, `backend/app/prompts/`, `backend/app/scheduler.py`, `backend/app/services/notifications.py`.

### 0.2 Façon de travailler
- Enchaîner les phases dans l'ordre de la section 5, sans attendre Lucas entre deux phases.
- **Tout se valide sans Vinted réel** : les appels Vinted passent par un client unique (`extension/src/vinted/client.ts`) testé contre les fixtures de `fixtures/vinted/` (copier ce dossier dans `extension/tests/fixtures/vinted/`). Les tests de réception de chaque phase sont automatisés avec ces fixtures. Les vérifications sur le vrai compte sont listées pour Lucas dans `PROGRESS.md` (« À tester toi-même »), comme pour les étapes précédentes.
- Après chaque phase : tests backend (`uv run pytest`, `ruff`, `mypy`), tests de l'extension (`npm test`, `tsc`), tests frontend si touchés, puis mise à jour de `PROGRESS.md` (fait, décisions prises, à tester par Lucas) et un commit par phase.
- **Quand un détail n'est pas tranché ici**, ne pas demander : choisir l'option la plus prudente pour le compte Vinted (moins d'actions, plus lent, arrêt plutôt qu'insistance), l'écrire dans « Décisions prises » de `PROGRESS.md`, et continuer.
- Ne s'arrêter pour demander que dans deux cas : une information impossible à déduire et indispensable (aucune n'est attendue), ou une action qui toucherait un vrai compte Vinted pendant le développement (interdit : aucun appel réel à Vinted depuis les tests).
- Langue : code, commentaires, messages et interface en français, comme le reste du dépôt.

### 0.3 Règles absolues
- Aucun identifiant Vinted (cookie, token, mot de passe) n'est lu, stocké ni transmis par l'extension ou le backend.
- Jamais de nouvel essai automatique d'une écriture Vinted qui a échoué.
- Toute réponse Vinted inattendue (401, 403, 429, captcha, réponse non JSON) arrête le compte concerné et prévient Lucas.
- Aucune action sur un compte Vinted dont l'identifiant ne correspond pas au compte attendu.
- Ne jamais deviner une route Vinted absente de la section 13. Les seules routes à vérifier au premier lancement réel sont signalées comme telles ; elles doivent échouer proprement (journal + alerte), pas casser le reste.

## 1. Contexte et objectif

Lucas vend des vêtements sur Vinted. Son app **vinted-manager** (FastAPI + Postgres + Next.js en PWA, ce dépôt) gère déjà : stock, batches, compta et export URSSAF, lecture des mails Vinted (ventes, offres, messages, bordereaux, litiges), envois et bordereaux fusionnés, analyse des photos et rédaction des annonces avec Claude, retouche des photos via Replicate, prix conseillé calé sur les vraies ventes, décision sur les offres, notifications push, plusieurs comptes Vinted.

Il lui manque d'**agir sur Vinted** : aujourd'hui tout passe par des copier-coller.

**Objectif** : une extension Chrome qui exécute les actions sur Vinted à la place de Lucas, pilotée par vinted-manager. À terme, Lucas ne fait plus que deux choses : publier les brouillons préparés et expédier les colis.

**Comptes** : celui de Lucas et celui de sa sœur. Elle vit au même domicile et vend ses propres affaires. Les articles des deux comptes ne se mélangent jamais.

## 2. Décisions prises

| Sujet | Décision |
|---|---|
| Base technique | Construire sur vinted-manager, pas de nouveau projet ni de Supabase |
| Exécution | PC de Lucas allumé en permanence (basse consommation) ; cloud seulement si l'essai est concluant |
| Brouillons | Jusqu'à 6 par jour et par compte, selon les photos fournies ; Lucas publie lui-même |
| Photos exigées | Devant, dos, étiquette obligatoires ; logo si présent ; au moins 5 photos au total |
| Modèles photo | Nano Banana 2 pour devant et dos, GPT Image 2 qualité basse pour étiquette, logo, détails |
| Première photo | Réelle (originale redressée et recadrée), pas générée |
| Déclaration IA | `ai_photo = true` dès qu'une photo publiée est générée |
| Republication | Tous les 5 jours ; reportée si un message a été échangé il y a moins d'1 h |
| Offre aux favoris | 10 % par défaut, en moins d'une minute après le favori |
| Offres reçues | Acceptées dès 90 % du prix affiché ; contre-offres sans limite de tours ; jamais sous 82 % du prix initial |
| Messages | Réponse automatique par l'IA dès le départ, escalade si doute |
| Baisse de prix | -5 % une seule fois, 48 à 72 h après publication sans vente |
| Après-vente | Remerciement automatique, bordereaux en A4, récapitulatif à 17 h 30 ; évaluations manuelles |
| Notifications | Bot Telegram, un destinataire par compte |
| Heures actives | 8 h à 23 h ; la nuit, réponses en 5 à 15 min et aucune action non urgente |
| Test | Sur un compte Vinted secondaire avant les comptes réels |

## 3. Architecture

```
                    vinted-manager (FastAPI + Postgres, localhost:8000)
                    décide : quoi faire, sur quel article, avec quelles données
                         ▲                                   │
       résultats, données│                                   │ tâches, réglages
                         │                                   ▼
        service worker de l'extension (un profil Chrome par compte Vinted)
                         │  alarmes, file de tâches, budget, arrêt d'urgence
                         ▼
        content script sur un onglet www.vinted.fr
                         │  fetch same-origin, cookies du navigateur
                         ▼
                   API privée Vinted
```

- **vinted-manager** reste le cerveau : règles de prix et d'offres, IA (Claude, `ANTHROPIC_MODEL`), photos, réglages, historique, notifications.
- **L'extension** est le bras : elle exécute les appels Vinted depuis la session du navigateur et renvoie les résultats. Elle garde le minimum d'état (file en cours, pause).
- **Authentification extension → backend** : un jeton par compte Vinted (en-tête `X-Extension-Token`), généré dans vinted-manager, stocké hashé (SHA-256), comparé en temps constant.
- **Deux profils Chrome**, un par compte, chacun avec l'extension et son propre jeton.
- **Telegram** : un bot, un `chat_id` par compte, envoi par le backend.

### 3.1 Socle technique commun (décidé, ne pas redemander)

**Extension**
- Manifest V3, TypeScript strict, build **esbuild**, tests **Vitest**, dossier `extension/` à la racine. Pas de framework UI (popup et options en HTML + TypeScript).
- **Le service worker est le seul à parler au backend** (avec `host_permissions` sur l'URL du backend, donc sans souci de CORS). **Le content script est le seul à parler à Vinted** (`fetch` depuis la page www.vinted.fr, `credentials: "include"` ; les appels à `api.vinted.fr` fonctionnent de la même façon, Vinted autorise l'origine www.vinted.fr).
- Échanges service worker ↔ content script : `chrome.tabs.sendMessage` / `chrome.runtime.onMessage`, messages JSON typés `{type, id, payload}`. Les photos passent en base64 (une photo par message).
- Cadence : `chrome.alarms` à 30 s (minimum autorisé en MV3) pour le service worker ; dans l'onglet Vinted, le content script interroge les compteurs de non-lus toutes les 15 à 30 s (aléatoire) pendant les heures actives et prévient le service worker quand un compteur change.
- Un onglet `www.vinted.fr` doit être ouvert dans le profil. Pour les actions qui nécessitent une navigation (page `want_it`), l'extension utilise un **onglet de travail** dédié qu'elle ouvre elle-même, en arrière-plan, et réutilise.
- Configuration (`chrome.storage.local`) : URL du backend (défaut `http://localhost:8000`), jeton du compte.

**Backend : file de tâches générique**
Toutes les actions Vinted passent par une table `tache_vinted`, pas seulement les brouillons :

| Champ | Contenu |
|---|---|
| `id`, `compte_id` | |
| `type` | `brouillon`, `repondre_message`, `accepter_offre`, `refuser_offre`, `contre_offre`, `relance_favori`, `republication`, `modifier_prix`, `message_apres_vente` |
| `article_id` | nullable |
| `payload` | JSON : tout ce dont l'extension a besoin pour exécuter sans réfléchir (ids Vinted, texte exact, montant) |
| `priorite` | 1 réponse acheteur, 2 offre ou relance, 3 après-vente, 4 brouillon, 5 republication ou prix |
| `executer_apres` | horodatage (délais aléatoires, heures actives, report) |
| `statut` | `a_faire`, `en_cours`, `faite`, `erreur`, `annulee` |
| `resultat`, `erreur`, `tentatives`, dates | |

Routes d'extension (en plus de celles de la phase 1, même authentification) :
- `GET /api/extension/taches/suivante` : la tâche la plus prioritaire dont `executer_apres` est passé, dans le budget d'actions, si le compte n'est pas en pause ; 204 sinon.
- `POST /api/extension/taches/{id}/resultat` : `{ok, resultat | erreur}`.
- `POST /api/extension/evenements` : l'extension remonte ce qu'elle observe (nouvelles conversations et messages, nouvelles offres reçues, nouveaux favoris, annonces du dressing, erreurs Vinted). **C'est le backend qui décide** (règles, IA) et crée les tâches. L'extension ne prend aucune décision métier.

Le endpoint des brouillons de la phase 1 peut être réécrit sur cette file dès la phase 2 ; garder la compatibilité des tests.

**Synchronisation du dressing (nécessaire dès la phase 3)**
- Toutes les 30 min (et au démarrage), l'extension lit `GET /api/v2/wardrobe/{user_id}/items` (toutes les pages) et l'envoie en événement `dressing`.
- Le backend rattache chaque annonce Vinted à un article : d'abord par `vinted_item_id` connu, sinon par titre exact puis par la recherche floue déjà utilisée pour les mails (`services/rapprochement.py`). Il renseigne `vinted_item_id`, le prix affiché et, s'il est vide, `prix_initial`. Une annonce sans article correspondant crée un article « importé de Vinted » rattaché au compte (statut `en_ligne`), signalé dans l'app.
- Les brouillons (`is_draft: true`) ne sont pas des annonces en ligne.

**Photos**
- Toutes les transformations d'image (première photo réelle, contrôle de couleur, transformations de republication) se font **dans le backend avec Pillow**, déjà installé. Pas de nouvelle dépendance lourde (pas de numpy obligatoire) : conversion sRGB → Lab écrite à la main pour le contrôle de couleur.
- L'extension ne fait que transférer les JPEG fournis par le backend.

**IA**
- Réutiliser `services/ia.py` (`_appeler`, sortie JSON imposée par schéma, gestion d'erreurs existante) et le modèle `ANTHROPIC_MODEL`.
- **Réponse à un message** : étendre `prompts/reponse_message.txt` et `SCHEMA_REPONSE` pour obtenir `{"intention": "question" | "offre_texte" | "lot" | "remerciement" | "suspect" | "autre", "reponse": "<texte>", "escalade": true | false, "raison_escalade": "<texte ou vide>"}`. Escalade obligatoire si la réponse demande une information absente de la fiche (mesures notamment), si le message parle de paiement ou de contact hors Vinted, de litige, ou si l'intention est `suspect`.
- **Offre formulée dans un message** (« vous la laissez à 50 € ? ») : le backend extrait le montant (IA, champ `montant_propose`), puis applique les mêmes règles qu'une offre Vinted et répond par une offre vendeur (`contre_offre`) ou par le texte adéquat.
- **Réécriture pour la republication** : nouveau prompt `prompts/reecriture_annonce.txt`, sortie `{"titre", "description"}`, contraintes de la section 10.1 ; vérification automatique (marque, taille, état, défauts, matière présents) avant de créer la tâche.
- Les décisions de prix ne sont jamais prises par l'IA (règles déterministes de `services/offres.py`, adaptées section 8).

**Telegram**
- Variable d'environnement `TELEGRAM_BOT_TOKEN`. Sans elle, les alertes restent en notifications push et en journal, sans erreur.
- Le backend interroge l'API Telegram en `getUpdates` (long polling, tâche APScheduler toutes les 5 s) : pas de webhook à exposer, ça marche sur le PC de Lucas.
- Appairage : Paramètres → Comptes affiche un code à 6 chiffres ; Lucas envoie `/start <code>` au bot ; le backend enregistre `telegram_chat_id` sur le compte.
- Tests avec un faux client Telegram (pas d'appel réel).

**Ce que Lucas fera lui-même (rien à coder)** : créer le bot avec @BotFather et mettre le token dans `.env`, générer les jetons d'extension, charger l'extension dans deux profils Chrome, régler les modèles photo par type, faire les tests réels listés dans `PROGRESS.md`.

## 4. Conformité et garde-fous

### 4.1 Règles Vinted à respecter
- **Photos** : Vinted exige des photos réelles et fidèles de l'article. La retouche ne doit jamais modifier le vêtement : ni couleur, ni coupe, ni matière, ni défaut effacé. Les photos de défaut ne sont jamais retouchées.
- **Déclaration IA** : à la création, Vinted transmet `ai_photo`, et par photo `ai_detected`, `digital_source_type`, `c2pa_read_error`. L'extension envoie `ai_photo = true` dès qu'au moins une photo publiée est générée. Elle ne déclare jamais `false` pour masquer des photos générées.
- **Textes** : exacts, rien d'inventé. Une marque ou une taille illisible reste « à compléter », jamais devinée. Défauts toujours mentionnés.
- **Statut vendeur** : Vinted réserve l'achat-revente régulier aux comptes Pro. Point ouvert côté Lucas, hors périmètre technique, mais qui pourrait ouvrir l'accès à l'API officielle Vinted Pro (`pro-docs.svc.vinted.com`).

### 4.2 Contrôle du compte
Avant chaque lot d'actions : `GET /api/v2/users/current`. Si `user.id` ≠ `vinted_user_id` du compte dans vinted-manager, ne rien faire et prévenir Lucas (« mauvais compte connecté dans ce profil »). C'est ce qui empêche un article de Lucas d'atterrir sur le compte de sa sœur.

### 4.3 Rythme humain
- Délais aléatoires entre chaque action (2 à 5 s entre deux uploads, 20 à 60 s avant une réponse, etc.).
- Budget d'actions par compte (section 11.4), partagé par tous les modules.
- Heures actives 8 h à 23 h (Europe/Paris). La nuit, seules les réponses aux acheteurs partent, en 5 à 15 min.
- Jamais deux extensions d'automatisation Vinted actives dans le même profil.

### 4.4 Arrêts automatiques
Captcha, réponse 403, 3 erreurs consécutives, session expirée, budget dépassé → arrêt du compte, notification Telegram, reprise manuelle uniquement.

## 5. Phases

| Phase | Contenu | Dépend de captures ? |
|---|---|---|
| 1 | Socle de l'extension + brouillons automatiques | Non, routes confirmées |
| 2 | Pilotage : Telegram, arrêt d'urgence, budget d'actions, surveillance, réglages | Non |
| 3 | Assistant : réponses aux messages et aux offres reçues | Non, routes confirmées le 25/10 |
| 4 | Favoris : message et offre en moins d'une minute | Non, routes confirmées le 25/10 |
| 5 | Republication différenciée | Non, routes confirmées le 25/10 |
| 6 | Baisse de prix automatique | Non, route confirmée le 25/10 |
| 7 | Après-vente automatique | Non, route de message confirmée le 25/10 |

Toutes les phases ont leurs routes confirmées. Ordre de développement : 1, 2, 3 (cœur de l'autonomie), 4, 5, 6, 7. Chaque phase doit passer ses tests automatisés avant la suivante ; aucune n'attend de validation de Lucas.

## 6. Phase 1 : socle et brouillons automatiques

Les tests de réception ci-dessous sont à automatiser avec les fixtures ; les mêmes vérifications sur le vrai compte vont dans « À tester toi-même ».

### 6.1 Backend
**B1. Comptes Vinted** (`CompteVinted`)
- Ajouter `vinted_user_id` (bigint, nullable, unique), `jeton_extension_hash`, `extension_vue_le`, `telegram_chat_id` (texte, nullable), `pause` (bool).
- Rendre les champs IMAP optionnels : le compte de la sœur peut exister sans boîte mail. La synchro IMAP ignore les comptes sans IMAP.
- Paramètres → Comptes : « Générer un jeton d'extension » (affiché une seule fois), `vinted_user_id`, dernière activité de l'extension.

**B2. Suivi sur l'article** (`Article`) : `vinted_item_id` (bigint), `vinted_draft_id` (bigint), `brouillon_statut` (`a_creer` | `en_cours` | `cree` | `erreur`), `brouillon_erreur`, `brouillon_cree_le`, `prix_initial` (prix au moment de la première publication ou de l'import), `prix_plancher` (calculé : 82 % du prix initial). Migration Alembic.

**B3. Router `backend/app/api/extension.py`**, hors du routeur protégé par cookie, authentifié par `X-Extension-Token`.

| Route | Rôle |
|---|---|
| `GET /api/extension/compte` | `{compte_id, nom, vinted_user_id, pause}` |
| `GET /api/extension/brouillons/suivant` | Prochain article prêt, ou 204. Le passe en `en_cours`. |
| `GET /api/extension/photos/{photo_id}` | JPEG de la version publiée, seulement si l'article appartient au compte |
| `POST /api/extension/brouillons/{article_id}/resultat` | `{ok: true, vinted_draft_id}` ou `{ok: false, erreur}` |
| `POST /api/extension/heartbeat` | `{vinted_user_id, version}` → `extension_vue_le` |

**Article prêt** : `compte_id` = ce compte ; statut `recu_a_publier` ; titre, description et prix remplis ; photos terminées ; contrôle de complétude et de couleur passés ; `brouillon_statut` vide (ou `erreur` relancée à la main).

**Quota** : 6 brouillons par compte et par jour (Europe/Paris), entre 8 h et 23 h. Réglable.

**Charge utile** de `brouillons/suivant` : `article_id`, `titre`, `description`, `prix`, `marque`, `taille`, `condition_id`, `couleur`, `matiere`, `categorie`, `package_size_id`, `ai_photo`, `photos` (liste ordonnée `{photo_id, type}`, ordre Vinted déjà utilisé pour le zip).

**État → `condition_id`** : Neuf avec étiquette 6, Neuf sans étiquette 1, Très bon état 2, Bon état 3, Satisfaisant 4.

**`package_size_id`** : 1 pour t-shirts et hauts légers (observé, catégorie 1806), 2 pour sweats et pulls (observé, catégorie 268), 2 par défaut pour les vestes (hypothèse).

**B4. Complétude des photos** : refus (statut `erreur`, notification « photo manquante : dos ») sans devant, dos, étiquette et 5 photos au total. Les photos de défaut comptent et restent originales.

**B5. Fidélité des photos**
- Réglage « Première photo réelle » dans Paramètres → Photos, activé par défaut : la photo « devant » publiée est l'originale (redressée, recadrée, métadonnées supprimées).
- Contrôle de couleur : couleur moyenne de la zone centrale du vêtement en Lab, original contre version générée. Écart ΔE > 10 → « couleur à vérifier », brouillon bloqué jusqu'à validation dans l'app.
- Modèles par type : Nano Banana 2 pour devant et dos, GPT Image 2 `low` pour le reste (réglage existant).

**B6. Déclaration IA** : `ai_photo = true` si au moins une photo publiée est une version générée. Par photo : `ai_detected: false`, `digital_source_type: []`, `c2pa_read_error: "other"` (ce que le site envoie pour un fichier sans métadonnées C2PA).

**B7. Style des annonces** : garder `prompts/style_annonce.txt`. Exemples de Lucas à y ajouter :
> T-shirt Nike ACG violet, taille M, super sympa. Porté mais en très bon état.

> Sweat col rond Uniqlo gris chiné, taille L. Porté mais en bon état, petite tache légère sur le devant en bas.

### 6.2 Extension (`extension/` à la racine du dépôt)
**E1. Manifest V3**, TypeScript strict, build esbuild, tests Vitest, sans framework UI (section 3.1).
- `permissions` : `storage`, `alarms`, `tabs`, `scripting`.
- `host_permissions` : `https://www.vinted.fr/*`, URL du backend (`http://localhost:8000/*` par défaut).
- Page d'options : URL du backend, jeton du compte (`chrome.storage.local`).

**E2. Service worker** : alarme de 30 s (section 3.1) ; demande d'un brouillon au plus toutes les 5 min, avec un délai aléatoire de 0 à 120 s ; heartbeat ; un onglet `www.vinted.fr` ouvert par Lucas est requis (sinon état « onglet Vinted fermé » dans la popup ; seul l'onglet de travail de la section 3.1 est ouvert automatiquement) ; récupération de la tâche, téléchargement des photos depuis le backend, transmission au content script.

**E3. Création du brouillon** (content script, routes en section 13.2)
1. Contrôle du compte (4.2).
2. CSRF lu dans la page, `anon_id` dans le cookie, UUID de session d'upload généré.
3. Upload des photos une par une, 2 à 5 s entre chaque.
4. `suggestions/categories` → `catalog_id` ; `attributes` → options.
5. Taille : libellé de `taille` cherché dans les options de `size` ; absent → erreur « taille introuvable ».
6. `suggestions/attributes` avec titre et description : la marque de vinted-manager prime (titre exact dans `brands[]`), sinon `prefill_brand`, sinon erreur ; couleur et matière suggérées, ou correspondance avec `couleur` et `matiere`.
7. `POST /api/v2/item_upload/drafts`, résultat renvoyé au backend.

**E4. Garde-fous** : section 4. Un seul brouillon à la fois par compte.

**E5. Popup** : compte Vinted connecté et compte vinted-manager, état (actif, en pause, erreur, onglet fermé), brouillons du jour (x/6), dernière action, bouton Pause / Reprendre.

### 6.3 Tests de réception
1. Un article de test complet du compte de Lucas devient un brouillon Vinted : photos dans l'ordre, première photo réelle, titre, description, prix, catégorie, marque, taille, état, couleur corrects, `ai_photo` conforme.
2. Un article du compte de la sœur n'est jamais traité par le profil de Lucas.
3. Un article sans photo de dos est refusé avec notification.
4. La 7ᵉ demande du jour n'est pas traitée.
5. Une réponse 403 simulée met le compte en pause.

## 7. Phase 2 : pilotage

### 7.1 Réglages (Paramètres de vinted-manager, page installable sur téléphone)
Par compte : heures actives, pause ; republication (cadence, délai de conversation active, plages de transformation) ; prix (baisse, plancher, arrondi) ; favoris (messages, variantes, réduction, délai) ; assistant (seuil d'acceptation, plancher, ton, réponses types) ; brouillons (maximum par jour) ; après-vente (messages, heure du récapitulatif) ; budget d'actions ; notifications (`chat_id` Telegram, types d'alertes). L'extension relit les réglages au démarrage et à chaque tâche.

### 7.2 Telegram
- Variable `TELEGRAM_BOT_TOKEN` ; `chat_id` par compte (procédure d'appairage : `/start` puis code affiché dans les paramètres).
- Alertes : vente, intervention requise par l'IA, offre hors règles, session Vinted expirée, onglet ou PC hors ligne, arrêt automatique, litige, brouillons prêts, récapitulatif quotidien.
- Boutons sur les alertes de l'assistant : envoyer la réponse proposée, la modifier, ignorer.
- Commandes : `/stop`, `/reprendre`, `/etat`.
- Les notifications push existantes restent en place.

### 7.3 Arrêt d'urgence
Interrupteur global, par module et par compte dans les paramètres ; `/stop` Telegram ; arrêts automatiques (4.4). Mise en œuvre : champ `pause` lu avant chaque action ; les tâches en attente restent en file, rien n'est perdu.

### 7.4 Budget d'actions par compte (valeurs de départ, réglables)
| Action | Plafond |
|---|---|
| Republications | 40 par jour |
| Offres envoyées | 60 par jour |
| Messages (favoris, réponses, après-vente) | 120 par jour |
| Brouillons | 6 par jour |
| Toutes actions confondues | 15 par heure |

Dépassement : l'action non urgente est reportée (heure suivante ou lendemain). Les réponses aux acheteurs restent prioritaires.

### 7.5 Surveillance
Heartbeat chaque minute ; sans signal pendant 5 minutes → alerte Telegram. Session Vinted expirée (401 persistant ou `users/current` en échec) → alerte avec la marche à suivre.

## 8. Phase 3 : assistant (messages et offres reçues)

- **Détection** : l'extension interroge Vinted (inbox et notifications) toutes les 15 à 30 s pendant les heures actives, toutes les 5 min la nuit. La lecture des mails reste pour la compta et le rapprochement.
- **Offres reçues** (adapter `services/offres.py`, règles déterministes, montants arrondis à 0,50 €) :
  - `prix_affiche` = prix actuel de l'annonce ; `plancher` = 82 % de `prix_initial` ; `dernier_propose` = dernière contre-offre envoyée dans cette conversation, sinon `prix_affiche`.
  - **Accepter** si l'offre ≥ 90 % de `prix_affiche`, ou si l'offre ≥ `dernier_propose`.
  - **Refuser** (refus Vinted + message poli rédigé par l'IA) si l'offre < 50 % de `prix_affiche` : offre jugée non sérieuse.
  - **Sinon contre-proposer** : `contre = max(plancher, arrondi((offre + dernier_propose) / 2))`. Si `contre` ≤ offre, accepter. Si `contre` = `dernier_propose` (on est déjà au plancher), renvoyer cette même valeur une seule fois, puis escalade Telegram au tour suivant.
  - Sans limite de tours, mais chaque contre-offre est inférieure ou égale à la précédente.
- **Messages** : l'IA répond (taille, état, envoi, disponibilité, lots) à partir de la fiche article uniquement. Escalade Telegram si la réponse n'est pas dans la fiche (mesures notamment), litige, demande de paiement hors Vinted, message suspect.
- **Délai** : 20 à 60 s en journée, 5 à 15 min la nuit.
- **Mode** : automatique dès le départ.
- **Demandes de lot** (plusieurs articles) : escalade Telegram, pas de réponse automatique.
- **Plus tard** : champ « mesures » à l'upload des photos, pour que l'IA puisse y répondre.

## 9. Phase 4 : favoris (message et offre)

- Détection des nouveaux favoris par les notifications Vinted, toutes les 15 à 30 s.
- Message défini par Lucas, variables `{prenom}` (Vinted ne donne que le pseudo : on utilise `login_name`, ou rien si le message reste naturel sans), `{article}`, `{prix}`, plusieurs variantes tirées au hasard. Message par défaut si Lucas n'en a pas saisi : « Hello, merci pour ton favori ! Je te propose une petite réduction si ça te tente. »
- Uniquement pendant les heures actives ; un favori reçu la nuit est traité à partir de 8 h, s'il a moins de 12 h.
- Offre jointe : 10 % par défaut, réglable, jamais sous le plancher.
- Envoi 20 à 60 s après le favori. Un seul message et une seule offre par membre et par article.

## 10. Phases 5 à 7

### 10.1 Republication différenciée
- **Cadence** : tous les 5 jours depuis la dernière publication.
- **Report** : si un message a été échangé sur l'article il y a moins d'une heure ; nouvel essai toutes les 30 min. Une offre en attente ne bloque pas.
- **Avant suppression** : offre envoyée aux membres qui ont mis l'article en favori et n'en ont pas encore reçu. La seule source est l'historique des favoris enregistré par le backend à partir des notifications (phase 4) ; aucun autre appel.
- **Nouvelle annonce** au prix courant, réparties sur les heures actives, jamais en rafale.
- **Photos** : toujours à partir des photos publiées la première fois (jamais d'une version déjà transformée). Pour un article importé de Vinted sans photos dans vinted-manager, les télécharger une fois depuis les URL `full_size_url` de l'annonce et les garder comme référence. Paramètres tirés au hasard à chaque fois :

| Transformation | Plage |
|---|---|
| Rotation | 1,5 à 2,5°, sens alterné |
| Zoom | 4,5 à 5,5 % (masque les coins vides de la rotation) |
| Luminosité | -2 à -5 % |
| Réencodage | JPEG qualité 85 à 92, métadonnées supprimées |

- La première photo reste fidèle : la baisse de luminosité ne doit pas changer la couleur perçue.
- **Texte** : titre et description reformulés par le LLM ; marque, taille, état, défauts, matière et mots-clés conservés et vérifiés automatiquement avant publication.
- **Point de vigilance** : si Vinted compare les images par empreinte perceptuelle, ces transformations peuvent ne pas suffire. Mesurer vues et favoris après republication sur le compte de test.

### 10.2 Baisse de prix automatique
-5 % une seule fois par article, 48 à 72 h après publication sans vente ; arrondi à 0,50 € ; jamais sous le plancher ; pas de nouvelle baisse après une republication.

### 10.3 Après-vente
1. Vente détectée par les mails (existant), confirmée par la disparition de l'annonce du dressing.
2. Message de remerciement quelques minutes après, avec un délai aléatoire, dans la conversation de l'inbox dont `data.inventory_items[].id` contient l'annonce vendue (et dont l'interlocuteur correspond à l'acheteur du mail quand il est connu). Conversation introuvable : tâche en erreur, sans alerte.
3. Bordereau récupéré (existant par mail), fusionné en PDF A4.
4. Récapitulatif à 17 h 30 sur Telegram : colis à préparer et PDF des bordereaux (remplace le rappel push de 9 h dans `scheduler.py`).
5. Rappel avant la date limite d'envoi.
6. Évaluations : rien d'automatique.
7. Litige ou retour : aucune action, alerte immédiate.

## 11. Exécution

### 11.1 Étape 1 : PC de Lucas
- `docker compose up -d` au démarrage de la session.
- Chrome lancé au démarrage avec les deux profils, un onglet vinted.fr ouvert dans chacun, extension chargée en mode développeur.
- Windows : pas de mise en veille, écran éteint après 5 min, mode d'alimentation économique, heures d'activité pour éviter les redémarrages de mise à jour ; option BIOS de redémarrage après coupure de courant si disponible.

### 11.2 Étape 2 : cloud (plus tard)
Serveur 4 Go de RAM, Chrome réel dans Docker avec écran virtuel (Xvfb) et profil persistant, accès distant sécurisé (noVNC) pour se connecter à Vinted, **proxy ISP statique français dédié par compte** (sinon le compte apparaît depuis un datacenter étranger).

## 12. Coûts de fonctionnement estimés
| Poste | Coût mensuel |
|---|---|
| Retouche photos (Nano Banana 2 devant et dos, GPT Image 2 le reste) | ~10 € |
| IA rédaction et réponses (Claude Haiku 5.5 par défaut) | 5 à 15 € |
| Électricité du PC | 2 à 11 € selon la machine |
| Telegram | 0 € |

## 13. Référence de l'API Vinted

### 13.1 Contexte d'exécution
- Appels depuis le content script sur `https://www.vinted.fr`, `fetch` same-origin, `credentials: "include"`.
- En-têtes : `x-csrf-token` (meta `csrf-token` ou motif `CSRF_TOKEN":"…"` dans le HTML), `x-anon-id` (cookie `anon_id`), `locale: fr-FR`, `accept: application/json, text/plain, */*`. Le site envoie aussi `siid` (UUID d'origine non identifiée : le relire depuis la page ou tester sans).

### 13.2 Création d'un brouillon (confirmé par capture le 25/10/2026)
0. `upload_session_id` = UUID v4 généré côté client, réutilisé comme `temp_uuid`.
1. **Photo** : `POST /api/v2/photos`, multipart : `photo[type]=item`, `photo[file]=<jpeg>`, `photo[temp_uuid]=<uuid>`. Réponse : `id` (pour `assigned_photos`), `image_uuid` (pour les suggestions), `is_suspicious`.
2. **Catégorie** : `POST /api/v2/item_upload/suggestions/categories`
   `{"image_metadata":[{"image_id":"<image_uuid>","orientation":"0"}],"upload_session_id":"<uuid>"}` → `prefill_categories[0]`.
3. **Attributs** : `POST /api/v2/item_upload/attributes` `{"attributes":[{"code":"category","value":[<catalog_id>]}]}` → options et `required`. Observé (catégorie 1806) : `size` requis (Tailles hommes : 206 XS, 207 S, 208 M, 209 L, 210 XL, 211 XXL, 212 XXXL), `condition` requis (6, 1, 2, 3, 4), `material` multiple (44 Coton, 149 Acrylique, 123 Cachemire…). Les tailles dépendent de la catégorie : toujours relire les options.
4. **Suggestions** : `POST /api/v2/item_upload/suggestions/attributes`
   `{"title","description","category_id","suggested_category_id","image_metadata","upload_session_id","attributes":[{"code":"category","ids":["<id>"]},{"code":"brand","ids":[]},{"code":"size","ids":[]},{"code":"condition","ids":[]},{"code":"color","ids":[]},{"code":"material","ids":[]}]}`
   → `prefill_brand`, `brands[]`, `colors[]`, `dynamic_attributes` (`color` et `material` avec `suggested_option_ids`).
   Listes : `GET /api/v2/item_upload/brands?category_id=`, `GET /api/v2/item_upload/colors`, `GET /api/v2/item_upload/catalogs` (~550 Ko, à mettre en cache).
5. **Éligibilité** (faite par le site, optionnelle) : `POST /api/v2/offline_verification/eligibility`.
6. **Brouillon** : `POST /api/v2/item_upload/drafts`
```json
{
  "draft": {
    "id": null, "currency": "EUR", "temp_uuid": "<uuid>",
    "title": "<titre>", "description": "<description>",
    "brand_id": 687713, "brand": "Nike ACG", "catalog_id": 1806, "isbn": null,
    "ai_photo": true, "price": "24", "package_size_id": 1,
    "shipment_prices": {"domestic": null, "international": null},
    "color_ids": [25],
    "assigned_photos": [{"id": 36532004066, "orientation": 0, "ai_detected": false, "digital_source_type": [], "c2pa_read_error": "other"}],
    "measurement_length": null, "measurement_width": null,
    "item_attributes": [{"code": "size", "ids": [208]}, {"code": "condition", "ids": [6]}, {"code": "material", "ids": [44]}],
    "manufacturer": null, "manufacturer_labelling": null
  },
  "parcel": null,
  "upload_session_id": "<uuid>"
}
```
   Réponse : `{"draft":{"id":10522041322},"after_upload_actions":[],"code":0}`. Le brouillon apparaît dans `GET /api/v2/wardrobe/{user_id}/items` avec `is_draft: true`.

### 13.3 Publication, modification, suppression, offre (confirmé par capture le 25/10/2026)

**Publier un brouillon** : `POST /api/v2/item_upload/drafts/{draft_id}/completion`. Corps : le même objet `draft` qu'à la création, avec `"id": <draft_id>`, plus `"push_up": false` au niveau racine. Les `assigned_photos` peuvent se limiter à `{id, orientation}`. Réponse : `{"item":{"id":<item_id>},"after_upload_actions":[...]}` (l'id de l'annonce publiée est celui du brouillon).

**Republication** = créer un nouveau brouillon (13.2) avec les photos transformées et le texte reformulé, le publier (`completion`), puis supprimer l'ancienne annonce. Dans cet ordre : en cas d'échec, l'ancienne annonce reste en ligne.

**Supprimer une annonce ou un brouillon** : `POST /api/v2/items/{id}/delete`, corps vide. Réponse : `{"code":0,"message":"Ok","message_code":"ok"}`.

**Modifier une annonce (prix, titre, description)** : `PUT /api/v2/item_upload/items/{item_id}`. Le corps contient l'objet `item` **complet** (même structure que `draft`, avec `id`, `temp_uuid` nouveau, `assigned_photos` existants, `item_attributes`, etc.) et `"push_up": false`. Il faut donc relire l'annonce avant (`GET /api/v2/items/{id}?localization=fr-FR` ; vérifier que tous les champs nécessaires y figurent, sinon capturer le chargement de la page d'édition). Ne jamais envoyer un objet partiel : les champs absents risquent d'être effacés.

**Envoyer une offre dans une conversation existante (vendeur → acheteur)** :
1. `GET /api/v2/transactions/{transaction_id}/offers/seller_options` → `min_price`, `max_price`.
2. Optionnel (fait par le site) : `POST /api/v2/offer/estimate_with_fees` `{"item_ids":["<item_id>"],"offer_price":{"amount":"22.00","currency_code":"EUR"},"fees":["buyer_protection"]}` → prix total payé par l'acheteur.
3. `POST /api/v2/transactions/{transaction_id}/offers` `{"offer":{"price":"20","currency":"EUR"}}` → `{"offer":{"id","price","user_msg_thread_id","transaction_id"}}`.

**Offre à un membre qui a liké** : le site passe par la page `https://www.vinted.fr/inbox/want_it?receiver_id={user_id}&item_id={item_id}`, qui ouvre (ou crée) la conversation et redirige vers `/inbox/{conversation_id}`. Aucune requête Fetch/XHR n'a été vue pour cette création : elle se fait au chargement de la page (confirmé par deux captures). Le `user_id` du membre vient de la notification de favori.

Mise en œuvre retenue, sans route devinée :
1. Le service worker ouvre (ou réutilise) un onglet de travail et le fait naviguer vers l'URL `want_it`.
2. Après la redirection vers `/inbox/{conversation_id}`, la page appelle elle-même `GET /api/v2/transactions/{transaction_id}/offers/seller_options`. Le content script lit cette URL dans `performance.getEntriesByType("resource")` et en extrait le `transaction_id` (délai maximal 15 s, sinon erreur).
   Alternative plus simple : lire le `conversation_id` dans l'URL `/inbox/{conversation_id}` puis `GET https://api.vinted.fr/messaging/main/conversations/{conversation_id}` → `data.transaction_id`.
3. Envoi du message de relance (`POST …/messaging/main/conversations/{conversation_id}/replies`), puis de l'offre avec `POST /api/v2/transactions/{transaction_id}/offers`.
4. L'onglet de travail revient ensuite sur la page du dressing.

**Messagerie (nouvelle API, sur `api.vinted.fr`)** : appels cross-origin depuis la page www.vinted.fr, avec les cookies (`credentials: "include"`) et les en-têtes `x-csrf-token`, `x-anon-id`, `locale: fr-FR`, `platform: web`, `x-next-app: marketplace-web`, `siid`.

- **Lire une conversation** : `GET https://api.vinted.fr/messaging/main/conversations/{conversation_id}` (UUID, celui de l'URL `/inbox/{conversation_id}`). Réponse utile :
  - `data.transaction_id`, `data.current_user_side` (`seller`), `data.items[].inventory_item_id` (id de l'annonce), `data.items[].title`, `data.total_price` ;
  - `opposite_users[]` ;
  - `messages[]` : `message_type` (`legacy_reply` pour un message texte, `legacy_offer_request` pour une offre), `sender_id`, `created_at`, `data.entity` (pour un message : `body` ; pour une offre : `offer_request_id`, `price`, `original_price`, `status`, `status_title`, `transaction_id`, `user_id`). Statut observé : 20 = offre acceptée.
- **Envoyer un message** : `POST https://api.vinted.fr/messaging/main/conversations/{conversation_id}/replies`
  `{"content":"<texte>","is_personal_data_sharing_check_skipped":false,"photo_temp_uuids":null}` → 201, `{"id","conversation_id","created_at","message_type":"reply_plain","sender_id","data":{"content","id"}}`.

L'ancienne route `POST /api/v2/conversations/{id}/replies` des sources publiques n'est plus celle utilisée par le site : ne pas l'utiliser.

**Répondre à une offre reçue** (le `offer_request_id` et le `transaction_id` viennent de `messages[].data.entity` de la conversation) :
- **Accepter** : `PUT /api/v2/transactions/{transaction_id}/offer_requests/{offer_request_id}/accept`, corps vide → `offer_request.status = 20` et un objet `offer` créé.
- **Refuser** : `PUT /api/v2/transactions/{transaction_id}/offer_requests/{offer_request_id}/reject`, corps vide → `offer_request.status = 30`.
- **Contre-proposer** (confirmé par capture) : envoyer directement une offre vendeur sur la même transaction, sans refuser la demande avant : `POST /api/v2/transactions/{transaction_id}/offers` `{"offer":{"price":"7","currency":"EUR"}}` → `{"offer":{"id","price","user_msg_thread_id","transaction_id"}}`. Le site appelle juste avant `POST /api/v2/offer/estimate_with_fees` pour afficher le prix payé par l'acheteur (optionnel).
- Statuts observés : 20 acceptée, 30 refusée.

**Détection des nouveaux messages, offres et favoris** (confirmé par capture) :
- `GET https://api.vinted.fr/messaging/main/users/unread_count` → `{"unread_count": 2}`. Appel léger : à interroger toutes les 15 à 30 s pendant les heures actives.
- `GET https://api.vinted.fr/inbox-notifications/v1/notifications/unread_count` → `{"count": 0}`. Même usage pour les notifications (favoris notamment).
- `GET https://api.vinted.fr/messaging/main/inbox` → `conversations[]` (20 par page) et `pagination` (`has_next`, `next_cursor`). Par conversation : `id` (UUID), `conversation_type` (`inquiry`…), `is_unread_by_current_user`, `last_message` (`created_at`, `sender_id`, `message_type`, `data.content`), `opposite_users[].data` (`id`, `login_name`), `data.inventory_items[]` (`id`, `title`), `statuses`.
  - `sender_id: "0"` correspond à un événement système (offre, changement de statut).
  - Le nom du paramètre de pagination n'a pas été vu : la première page suffit pour la surveillance.
- Algorithme : quand un compteur augmente (ou toutes les 5 min par sécurité), lire `inbox` ; pour chaque conversation dont `last_message.created_at` est plus récent que le dernier traitement et dont l'expéditeur n'est pas le compte lui-même, lire la conversation (`GET …/messaging/main/conversations/{id}`) et traiter les messages et offres arrivés depuis. Garder ce point de reprise côté backend pour ne jamais traiter deux fois le même message.
- Liste des notifications : la source publique utilise `GET https://www.vinted.fr/web/gateway/inbox-notifications/v1/notifications?page&per_page` ; le site appelle désormais le même service sur `api.vinted.fr/inbox-notifications/v1/…`. Vérifier laquelle répond au premier test.

### 13.4 Autres routes (sources publiques, octobre 2026)
| Usage | Méthode et route | Statut |
|---|---|---|
| Utilisateur courant | `GET /api/v2/users/current` | Confirmé 2026 |
| Rafraîchir le token | `POST /web/api/auth/refresh` | Confirmé 2026 (le navigateur s'en charge normalement) |
| Mon dressing | `GET /api/v2/wardrobe/{userId}/items?page&per_page` | Confirmé par capture |
| Filtres du dressing (compteurs actifs, brouillons, vendus) | `GET /api/v2/closet/seller_filters` | Confirmé par capture |
| Détail d'un article | `GET /api/v2/items/{id}?localization=fr-FR` | Confirmé 2026 |
| Notifications (dont favoris) | `GET /web/gateway/inbox-notifications/v1/notifications?page&per_page` | Confirmé 2026 |
| Recherche de comparables | `GET https://api.vinted.fr/svc-catalogue/items` (filtres `attribute_ids[...]`) | Confirmé 2026 |
### 13.5 À capturer (DevTools → Réseau, « Conserver le journal » coché, puis « Save all as HAR »)
| Capture | Filtre | Phase |
|---|---|---|
| Ouvrir la page d'édition d'une annonce (pour savoir d'où viennent les données du formulaire) | Tout | 6 (optionnel : sinon relire l'annonce avec `GET /api/v2/items/{id}`) |

## 14. À vérifier au premier lancement réel (comportement par défaut déjà défini, ne bloque pas le développement)
| Point | Comportement par défaut à coder |
|---|---|
| `package_size_id` des vestes et manteaux | 2 ; si Vinted refuse, erreur claire sur la tâche |
| En-tête `siid` | Le relire depuis la page s'il est trouvé, sinon ne pas l'envoyer |
| Liste des notifications : `api.vinted.fr/inbox-notifications/v1/notifications` ou `www.vinted.fr/web/gateway/inbox-notifications/v1/notifications` | Essayer la première, puis la seconde ; mémoriser celle qui répond ; journaliser |
| Champs exacts de `GET /api/v2/items/{id}` pour reconstruire l'objet complet avant un `PUT` | Si un champ requis manque, ne pas faire le `PUT` : tâche en erreur et alerte |
| Effet de `ai_photo = true` sur la visibilité | Aucun ; Lucas observe sur le compte de test |
| Efficacité des transformations de republication | Aucun ; Lucas compare vues et favoris |

Hors technique : le statut Pro de Lucas (accès possible à l'API officielle Vinted Pro).

## 15. Fixtures fournies (`fixtures/vinted/`)
Réponses réelles capturées le 25/10/2026 et anonymisées (identifiants et pseudos des autres membres remplacés, aucun jeton). Chaque fichier contient `request` (méthode, URL, corps) et `response` (statut, corps).

| Fichier | Route |
|---|---|
| `photos_upload.json` | `POST /api/v2/photos` |
| `suggestions_categories.json` | `POST /api/v2/item_upload/suggestions/categories` |
| `attributes_1806.json`, `attributes_268.json` | `POST /api/v2/item_upload/attributes` (t-shirt, sweat) |
| `suggestions_attributes.json` | `POST /api/v2/item_upload/suggestions/attributes` |
| `eligibility.json` | `POST /api/v2/offline_verification/eligibility` |
| `drafts_create.json` | `POST /api/v2/item_upload/drafts` |
| `drafts_completion.json` | `POST /api/v2/item_upload/drafts/{id}/completion` |
| `items_update.json` | `PUT /api/v2/item_upload/items/{id}` |
| `items_delete.json` | `POST /api/v2/items/{id}/delete` |
| `colors.json`, `brands_1806.json`, `catalogs.json` | listes de référence |
| `wardrobe_items.json`, `closet_seller_filters.json` | dressing |
| `offers_seller_options.json`, `offer_estimate_with_fees.json` | préparation d'une offre |
| `offers_send_to_liker.json`, `offers_counter.json` | `POST /api/v2/transactions/{id}/offers` |
| `offer_request_accept.json`, `offer_request_reject.json` | réponse à une offre reçue |
| `messaging_inbox.json`, `messaging_conversation.json`, `messaging_reply.json` | messagerie `api.vinted.fr` |
| `messaging_unread_count.json`, `notifications_unread_count.json` | compteurs de non-lus |
