export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export function construireUrl(chemin: string, params?: Params): string {
  const qs = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(params ?? {})) {
    if (valeur === undefined || valeur === null || valeur === "") continue;
    if (Array.isArray(valeur)) valeur.forEach((v) => qs.append(cle, String(v)));
    else qs.append(cle, String(valeur));
  }
  const q = qs.toString();
  return `/api${chemin}${q ? `?${q}` : ""}`;
}

function redirigerVersLogin() {
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    const suite = window.location.pathname + window.location.search;
    window.location.href = `/login?suite=${encodeURIComponent(suite)}`;
  }
}

async function lireErreur(res: Response): Promise<string> {
  try {
    const corps = await res.json();
    if (typeof corps?.detail === "string") return corps.detail;
  } catch {
    /* corps non JSON */
  }
  if (res.status >= 500) return "Le serveur ne répond pas correctement. Réessaie dans un instant.";
  return `Erreur ${res.status}`;
}

export async function api<T>(
  chemin: string,
  options: { method?: string; body?: unknown; params?: Params; form?: FormData } = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(construireUrl(chemin, options.params), {
      method: options.method ?? (options.body || options.form ? "POST" : "GET"),
      credentials: "same-origin",
      headers: options.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
    });
  } catch {
    throw new ApiError("Impossible de joindre le serveur. Vérifie ta connexion.", 0);
  }
  if (res.status === 401 && !chemin.startsWith("/auth/login")) {
    redirigerVersLogin();
    throw new ApiError("Session expirée, reconnecte-toi.", 401);
  }
  if (!res.ok) throw new ApiError(await lireErreur(res), res.status);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Télécharge un fichier renvoyé par l'API (export, CSV, zip). */
export async function telecharger(chemin: string, params?: Params): Promise<void> {
  const res = await fetch(construireUrl(chemin, params), { credentials: "same-origin" });
  if (res.status === 401) {
    redirigerVersLogin();
    return;
  }
  if (!res.ok) throw new ApiError(await lireErreur(res), res.status);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const nom = /filename="?([^"]+)"?/.exec(disposition)?.[1] ?? "export";
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = nom;
  a.click();
  URL.revokeObjectURL(url);
}
