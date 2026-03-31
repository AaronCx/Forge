"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getUser, logout as authLogout } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useBackendMode } from "@/lib/backend-context";
import { Menu } from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/dashboard/monitor", label: "Monitor" },
  { href: "/dashboard/analytics", label: "Analytics" },
  { href: "/dashboard/orchestrate", label: "Orchestrate" },
  { href: "/dashboard/agents", label: "Agents" },
  { href: "/dashboard/blueprints", label: "Blueprints" },
  { href: "/dashboard/compare", label: "Compare" },
  { href: "/dashboard/runs", label: "Runs" },
  { href: "/dashboard/evals", label: "Evals" },
  { href: "/dashboard/approvals", label: "Approvals" },
  { href: "/dashboard/triggers", label: "Triggers" },
  { href: "/dashboard/traces", label: "Traces" },
  { href: "/dashboard/prompts", label: "Prompts" },
  { href: "/dashboard/knowledge", label: "Knowledge" },
  { href: "/dashboard/marketplace", label: "Marketplace" },
  { href: "/dashboard/team", label: "Team" },
  { href: "/dashboard/workspace", label: "Workspace" },
  { href: "/dashboard/settings", label: "Settings" },
];

function SidebarContent({
  pathname,
  userEmail,
  onLogout,
  onNavigate,
}: {
  pathname: string;
  userEmail: string;
  onLogout: () => void;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <nav className="flex-1 flex flex-col gap-1 p-4 overflow-y-auto">
        {navItems.map((item) => {
          const href = item.href;
          return (
            <Link
              key={item.href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                (item.href === "/dashboard"
                  ? pathname === "/dashboard"
                  : pathname.startsWith(item.href))
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto border-t border-border p-4">
        <p className="truncate text-xs text-muted-foreground" title={userEmail}>
          {userEmail}
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 w-full justify-start text-muted-foreground"
          onClick={onLogout}
        >
          Sign out
        </Button>
      </div>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [userEmail, setUserEmail] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);

  const { mode } = useBackendMode();
  const demo = mode === "demo";

  useEffect(() => {
    if (mode === "loading") return;
    if (demo) {
      setUserEmail("demo@forge.dev");
      // Set cookie so middleware allows access without auth
      document.cookie = "forge_demo=1; path=/";
      return;
    }
    // Live mode — require real auth
    getUser()
      .then((user) => {
        if (!user) {
          router.push("/login");
          return;
        }
        setUserEmail(user.email || "");
      })
      .catch(() => {
        router.push("/login");
      });
  }, [router, mode, demo]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  async function handleLogout() {
    await authLogout();
    window.location.href = "/login";
  }

  const logo = (
    <div className="flex h-16 items-center gap-2 border-b border-border px-6">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
        AF
      </div>
      <span className="text-lg font-bold">Forge</span>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col border-r border-border bg-card">
        {logo}
        <SidebarContent
          pathname={pathname}
          userEmail={userEmail}
          onLogout={handleLogout}
        />
      </aside>

      {/* Mobile Header + Sheet */}
      <div className="flex flex-1 flex-col">
        <header className="flex md:hidden h-14 items-center gap-3 border-b border-border bg-card px-4">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="shrink-0">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              {logo}
              <SidebarContent
                pathname={pathname}
                userEmail={userEmail}
                onLogout={handleLogout}
                onNavigate={() => setMobileOpen(false)}
              />
            </SheetContent>
          </Sheet>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-xs">
              AF
            </div>
            <span className="font-semibold">Forge</span>
          </div>
        </header>

        {/* Demo mode banner */}
        {demo && (
          <div className="bg-yellow-900/50 border-b border-yellow-700 px-4 py-2 text-sm text-yellow-200 text-center">
            Backend not detected. Showing demo mode. Run &apos;forge up&apos; to start the backend.
          </div>
        )}

        {/* Loading state */}
        {mode === "loading" && (
          <div className="flex items-center justify-center p-8 text-muted-foreground text-sm">
            Detecting backend...
          </div>
        )}

        {/* Main content */}
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-6xl p-4 md:p-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
