import { NextRequest, NextResponse } from "next/server"

/**
 * Middleware — site-password gate (optional).
 *
 * If SITE_PASSWORD is set, users must pass the login page before accessing
 * the app. Firebase anonymous sign-in then happens client-side, and every
 * backend request includes a Firebase ID token for per-user rate limiting.
 *
 * If SITE_PASSWORD is not set, the login page is skipped entirely.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Always allow static assets, login page, and API routes
  if (
    pathname === "/login" ||
    pathname.startsWith("/api/") ||
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico" ||
    /\.(svg|png|jpg|jpeg|gif|webp)$/.test(pathname)
  ) {
    return NextResponse.next()
  }

  // If no site password is configured, skip the gate
  const hasSitePassword = Boolean(process.env.SITE_PASSWORD)
  if (!hasSitePassword) {
    return NextResponse.next()
  }

  // Check for auth cookie set by /api/auth
  const auth = request.cookies.get("insightnet-auth")
  if (!auth?.value) {
    return NextResponse.redirect(new URL("/login", request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
}

