import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("sb-access-token")?.value;
  const { pathname } = request.nextUrl;

  // Public routes
  if (pathname.startsWith("/login") || pathname.startsWith("/signup") || pathname.startsWith("/demo") || pathname.startsWith("/docs") || pathname === "/") {
    if (token && (pathname === "/login" || pathname === "/signup")) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
    return NextResponse.next();
  }

  // Demo mode bypass
  if (pathname.startsWith("/dashboard") && request.nextUrl.searchParams.has("demo")) {
    const response = NextResponse.next();
    response.cookies.set("agentforge_demo", "1", { path: "/" });
    return response;
  }

  // Protected routes
  if (!token && pathname.startsWith("/dashboard")) {
    const isDemo = request.cookies.get("agentforge_demo")?.value === "1";
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
