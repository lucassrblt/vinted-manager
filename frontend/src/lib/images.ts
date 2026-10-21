/** Côté le plus long d'une photo envoyée au serveur (le serveur réduit de toute façon à 2048 px). */
const TAILLE_MAX = 2048;
const QUALITE = 0.88;

/**
 * Réduit une photo dans le navigateur avant l'envoi : 2048 px max, JPEG, orientation de l'iPhone
 * appliquée. Une photo d'iPhone passe de 3-5 Mo à environ 0,5 Mo : envoi plus rapide et sous la
 * limite de taille du relais. Si le navigateur ne sait pas lire le fichier, il est envoyé tel quel.
 */
export async function reduirePhoto(fichier: File): Promise<File> {
  try {
    const image = await createImageBitmap(fichier, { imageOrientation: "from-image" });
    const echelle = Math.min(1, TAILLE_MAX / Math.max(image.width, image.height));
    if (echelle === 1 && fichier.type === "image/jpeg" && fichier.size < 1_500_000) {
      image.close();
      return fichier;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(image.width * echelle);
    canvas.height = Math.round(image.height * echelle);
    canvas.getContext("2d")?.drawImage(image, 0, 0, canvas.width, canvas.height);
    image.close();
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", QUALITE));
    if (!blob) return fichier;
    return new File([blob], fichier.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return fichier;
  }
}
