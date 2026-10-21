import { NextResponse, type NextRequest } from "next/server";

const PUBLIQUES = ["/login"];

// Redirection rapide vers /login sans cookie de session. La validité réelle de la session
// est vérifiée par l'API (401 -> redirection côté client).
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const aSession = req.cookies.has("vm_session");
  if (!aSession && !PUBLIQUES.includes(pathname)) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?suite=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon.ico|icons|manifest.webmanifest|sw.js|.*\\.(?:png|svg|ico|webp)).*)"],
};
