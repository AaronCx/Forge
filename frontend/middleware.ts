import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

function isDemoDeployment(request: NextRequest): boolean {
  // Build-time opt-in (used by the e2e smoke test and local demo runs)
  if (process.env.NEXT_PUBLIC_FORCE_DEMO === "true") return true;
  const host = request.headers.get("host") || "";
  // Vercel deployments (no local backend available) → demo mode
  return host.includes("vercel.app");
}

export function middleware(request: NextRequest) {
  const token = request.cookies.get("sb-access-token")?.value;
  const { pathname } = request.nextUrl;
  const forceDemo = isDemoDeployment(request);

  // Public routes — always accessible
  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/signup") ||
    pathname.startsWith("/auth/callback") ||
    pathname.startsWith("/docs") ||
    pathname === "/"
  ) {
    // In demo mode, redirect login/signup straight to dashboard
    if (forceDemo && (pathname === "/login" || pathname === "/signup")) {
      const response = NextResponse.redirect(new URL("/dashboard", request.url));
      response.cookies.set("forge_demo", "1", { path: "/" });
      return response;
    }
    if (token && (pathname === "/login" || pathname === "/signup")) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
    return NextResponse.next();
  }

  // Legacy /demo route — redirect to dashboard
  if (pathname.startsWith("/demo")) {
    const response = NextResponse.redirect(new URL("/dashboard", request.url));
    response.cookies.set("forge_demo", "1", { path: "/" });
    return response;
  }

  // Protected routes — require auth OR demo mode
  if (!token && pathname.startsWith("/dashboard")) {
    if (forceDemo) {
      const response = NextResponse.next();
      response.cookies.set("forge_demo", "1", { path: "/" });
      return response;
    }
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
