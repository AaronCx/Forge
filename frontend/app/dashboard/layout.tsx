"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { isDemoMode } from "@/lib/demo-data";
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
  { href: "/dashboard/settings", label: "Settings" },
];

function SidebarContent({
  pathname,
  userEmail,
  demo,
  onLogout,
  onNavigate,
}: {
  pathname: string;
  userEmail: string;
  demo: boolean;
  onLogout: () => void;
  onNavigate?: () => void;
}) {
  return (
    <>
      <nav className="flex flex-col gap-1 p-4">
        {navItems.map((item) => {
          const href = demo ? `${item.href}?demo=true` : item.href;
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
    </>
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

  useEffect(() => {
    if (isDemoMode()) {
      setUserEmail("demo@agentforge.dev");
      return;
    }
    supabase.auth
      .getUser()
      .then(({ data }) => {
        if (!data.user) {
          router.push("/login");
          return;
        }
        setUserEmail(data.user.email || "");
      })
      .catch(() => {
        router.push("/login");
      });
  }, [router]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const demo = isDemoMode();

  async function handleLogout() {
    document.cookie = "agentforge_demo=; max-age=0; path=/";
    document.cookie = "sb-access-token=; max-age=0; path=/";
    try {
      await supabase.auth.signOut();
    } catch {
      // Continue with redirect even if signOut fails
    }
    // Clear any Supabase session data from localStorage
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("sb-")) localStorage.removeItem(key);
    }
    window.location.href = "/login";
  }

  const logo = (
    <div className="flex h-16 items-center gap-2 border-b border-border px-6">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
        AF
      </div>
      <span className="text-lg font-bold">AgentForge</span>
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
          demo={demo}
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
                demo={demo}
                onLogout={handleLogout}
                onNavigate={() => setMobileOpen(false)}
              />
            </SheetContent>
          </Sheet>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-xs">
              AF
            </div>
            <span className="font-semibold">AgentForge</span>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-6xl p-4 md:p-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
