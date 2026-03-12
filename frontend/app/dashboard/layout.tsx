"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { isDemoMode } from "@/lib/demo-data";

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
  { href: "/dashboard/settings", label: "Settings" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [userEmail, setUserEmail] = useState("");

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

  const demo = isDemoMode();

  async function handleLogout() {
    document.cookie = "agentforge_demo=; max-age=0; path=/";
    await supabase.auth.signOut();
    document.cookie = "sb-access-token=; max-age=0; path=/";
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border bg-card">
        <div className="flex h-16 items-center gap-2 border-b border-border px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
            AF
          </div>
          <span className="text-lg font-bold">AgentForge</span>
        </div>
        <nav className="flex flex-col gap-1 p-4">
          {navItems.map((item) => {
            const href = demo ? `${item.href}?demo=true` : item.href;
            return (
              <Link
                key={item.href}
                href={href}
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
          <p className="truncate text-xs text-muted-foreground" title={userEmail}>{userEmail}</p>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full justify-start text-muted-foreground"
            onClick={handleLogout}
          >
            Sign out
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-6xl p-8">{children}</div>
      </main>
    </div>
  );
}
