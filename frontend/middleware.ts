import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("sb-access-token")?.value;
  const { pathname } = request.nextUrl;

  // Public routes — always accessible
  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/signup") ||
    pathname.startsWith("/auth/callback") ||
    pathname.startsWith("/docs") ||
    pathname === "/"
  ) {
    // Redirect authenticated users away from login/signup
    if (token && (pathname === "/login" || pathname === "/signup")) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
    return NextResponse.next();
  }

  // Legacy /demo route — redirect to dashboard (detection is automatic now)
  if (pathname.startsWith("/demo")) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // Protected routes — require auth token OR demo mode
  if (!token && pathname.startsWith("/dashboard")) {
    // Allow access if force-demo is enabled (Vercel showcase deployment)
    if (process.env.NEXT_PUBLIC_FORCE_DEMO === "true") {
      return NextResponse.next();
    }
    // Allow access if demo cookie is set (backend unreachable detection)
    const isDemo = request.cookies.get("forge_demo")?.value === "1";
    if (isDemo) {
      return NextResponse.next();
    }
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
