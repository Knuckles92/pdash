import { NextResponse, type NextRequest } from "next/server";

/**
 * Redirect unauthenticated traffic to /login.
 * The server-side cookie is HttpOnly so we can only check its presence here.
 * The backend remains the source of truth and will 401 if the session is
 * actually invalid.
 */
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Allow public assets, the login page itself, and the proxied API.
  if (
    pathname === "/login" ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico" ||
    pathname.match(/\.(svg|png|jpg|jpeg|gif|webp|ico)$/)
  ) {
    return NextResponse.next();
  }

  const session = req.cookies.get("session");
  if (!session) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/|api/|favicon\\.ico).*)"],
};
