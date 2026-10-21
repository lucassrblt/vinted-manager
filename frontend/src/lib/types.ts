// Types miroirs des schémas de l'API. Les montants arrivent en chaînes décimales (« 12.50 »).
export type Decimal = string;

export type Statut = "commande" | "recu_a_publier" | "en_ligne" | "vendu" | "envoye" | "livre" | "litige" | "retourne";

export type Etat = "neuf_avec_etiquette" | "neuf_sans_etiquette" | "tres_bon_etat" | "bon_etat" | "satisfaisant";

export interface Article {
  id: number;
  nom: string;
  marque: string | null;
  categorie: string | null;
  taille: string | null;
  couleur: string | null;
  etat: Etat | null;
  prix_achat_brut: Decimal | null;
  remise: Decimal;
  prix_achat_net: Decimal | null;
  prix_vente_cible: Decimal | null;
  prix_vente_reel: Decimal | null;
  statut: Statut;
  batch_id: number | null;
  batch_nom: string | null;
  source: string | null;
  date_achat: string | null;
  date_reception: string | null;
  date_publication: string | null;
  date_vente: string | null;
  date_envoi: string | null;
  date_livraison: string | null;
  litige: boolean;
  notes: string | null;
  titre_annonce: string | null;
  description_annonce: string | null;
  mesures: Record<string, string | number> | null;
  created_at: string;
  updated_at: string;
  prix_vente: Decimal | null;
  marge: Decimal | null;
  marge_pct: Decimal | null;
  coefficient: Decimal | null;
  indicateur: "Sous l'objectif" | "OK" | "Au-dessus" | null;
  jours_en_ligne: number | null;
  delai_vente_heures: number | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  taille_page: number;
}

export interface Historique {
  id: number;
  ancien_statut: Statut | null;
  nouveau_statut: Statut;
  date: string;
  commentaire: string | null;
}

export interface Preuve {
  id: number;
  article_id: number | null;
  batch_id: number | null;
  type: string;
  nom_original: string;
  mime: string;
  taille_octets: number;
  date_upload: string;
  note: string | null;
}

export interface LiensArticle {
  ventes: {
    id: number;
    prix: Decimal;
    date_heure: string;
    acheteur: string | null;
    numero_commande: string | null;
    auto_rapproche: boolean;
  }[];
  envois: {
    id: number;
    statut: string;
    transporteur: string | null;
    date_limite_envoi: string | null;
    date_depot: string | null;
  }[];
  mails: { id: number; date: string | null; sujet: string | null; type_detecte: string | null }[];
  preuves: Preuve[];
}

export interface BatchStats {
  id: number;
  nom: string;
  fournisseur: string | null;
  date_commande: string | null;
  total_paye: Decimal | null;
  remise_globale: Decimal;
  notes: string | null;
  nb_articles: number;
  nb_publies: number;
  nb_vendus: number;
  sell_through: Decimal | null;
  ca: Decimal;
  marge_realisee: Decimal;
  coefficient_ventes: Decimal | null;
  delai_moyen_heures: number | null;
  valeur_stock_restant: Decimal;
  investi: Decimal;
}

export interface Kpis {
  ca_encaisse: Decimal;
  nb_ventes: number;
  ventes_sans_date: number;
  marge_realisee: Decimal;
  cotisations_estimees: Decimal;
  marge_apres_cotisations: Decimal;
  delai_moyen_heures: number | null;
  total_investi: Decimal;
  valeur_stock: Decimal;
  marge_globale: Decimal;
  marge_globale_apres_cotisations: Decimal;
  coefficient_global: Decimal | null;
  sell_through: Decimal | null;
  nb_total: number;
  nb_vendus: number;
  nb_en_stock: number;
  nb_recus: number;
  nb_publies: number;
  nb_a_publier: number;
  taux_cotisations: Decimal;
}

export interface PointSerie {
  periode: string;
  debut: string;
  ca: Decimal;
  marge: Decimal;
  nb_ventes: number;
}

export interface LigneRepartition {
  cle: string;
  nb_ventes: number;
  ca: Decimal;
  marge: Decimal;
  delai_moyen_heures: number | null;
}

export interface Piste {
  id: number;
  origine: "tests" | "recherche" | "manuel";
  marque: string | null;
  produit: string;
  mots_cles: string | null;
  categorie: string | null;
  achat_max: Decimal | null;
  revente_basse: Decimal | null;
  revente_haute: Decimal | null;
  priorite: string | null;
  quantite_test: string | null;
  commentaire: string | null;
  perf_nb_ventes: number;
  perf_prix_moyen: Decimal | null;
  perf_delai_moyen_jours: number | null;
  perf_coefficient_moyen: Decimal | null;
  perf_base: string | null;
}

export interface Anomalie {
  champ: string;
  niveau: "erreur" | "avertissement";
  message: string;
}

export interface LigneImport {
  ligne: number;
  nom: string;
  taille: string | null;
  marque: string | null;
  categorie: string | null;
  couleur: string | null;
  prix_achat_brut: Decimal | null;
  remise: Decimal;
  prix_achat_net: Decimal | null;
  prix_vente: Decimal | null;
  vendu: boolean;
  litige: boolean;
  batch: string | null;
  source: string | null;
  date_achat: string | null;
  statut_excel: string | null;
  statut: Statut | null;
  anomalies: Anomalie[];
}

export interface PisteImport {
  origine: "tests" | "recherche";
  marque: string | null;
  produit: string;
  categorie: string | null;
  achat_max: Decimal | null;
  revente_basse: Decimal | null;
  revente_haute: Decimal | null;
  priorite: string | null;
}

export interface ApercuImport {
  lignes: LigneImport[];
  pistes: PisteImport[];
  onglets_lus: string[];
  onglets_absents: string[];
}

export interface Parametres {
  taux_cotisations: Decimal;
  coefficient_min: Decimal;
  coefficient_max: Decimal;
  seuil_article_lent_jours: number;
  objectif_ventes_jour: number;
  arrondi_seuil: Decimal;
  arrondi_pas: Decimal;
}

export interface EcranDuJour {
  a_publier: number;
  commandes_en_attente: number;
  litiges: number;
  articles_lents: {
    id: number;
    nom: string;
    taille: string | null;
    prix_vente: Decimal | null;
    jours_en_ligne: number | null;
  }[];
  semaine: {
    ca: Decimal;
    marge: Decimal;
    nb_ventes: number;
    ca_precedente: Decimal;
    marge_precedente: Decimal;
    nb_ventes_precedente: number;
  };
  objectif_jour: { objectif: number; ventes: number };
}
