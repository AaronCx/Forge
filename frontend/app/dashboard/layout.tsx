"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
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
import {
  Activity,
  BookOpen,
  Bot,
  CheckCircle,
  Code2,
  Cpu,
  GitBranch,
  GitCompare,
  Key,
  LayoutDashboard,
  ListChecks,
  Menu,
  MessageSquare,
  Monitor,
  Network,
  Play,
  Plug,
  Settings as SettingsIcon,
  Store,
  Target,
  Users,
  Video,
  Zap,
  type LucideIcon,
} from "lucide-react";

type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
};

type NavGroup = {
  label: string | null;
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ label: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Build",
    items: [
      { label: "Agents", href: "/dashboard/agents", icon: Bot },
      { label: "Blueprints", href: "/dashboard/blueprints", icon: GitBranch },
      { label: "Prompts", href: "/dashboard/prompts", icon: MessageSquare },
      { label: "Knowledge", href: "/dashboard/knowledge", icon: BookOpen },
    ],
  },
  {
    label: null,
    items: [{ label: "Workspace", href: "/dashboard/workspace", icon: Code2 }],
  },
  {
    label: "Run",
    items: [
      { label: "Orchestrate", href: "/dashboard/orchestrate", icon: Network },
      { label: "Approvals", href: "/dashboard/approvals", icon: CheckCircle },
      { label: "Triggers", href: "/dashboard/triggers", icon: Zap },
      { label: "Targets", href: "/dashboard/targets", icon: Target },
    ],
  },
  {
    label: "Observe",
    items: [
      { label: "Runs", href: "/dashboard/runs", icon: Play },
      { label: "Traces", href: "/dashboard/traces", icon: Activity },
      { label: "Recordings", href: "/dashboard/recordings", icon: Video },
      { label: "Evals", href: "/dashboard/evals", icon: ListChecks },
      { label: "Compare", href: "/dashboard/compare", icon: GitCompare },
    ],
  },
  {
    label: "Compute",
    items: [
      { label: "Computer Use", href: "/dashboard/computer-use", icon: Monitor },
      { label: "Providers", href: "/dashboard/providers", icon: Cpu },
      { label: "MCP", href: "/dashboard/mcp", icon: Plug },
    ],
  },
  {
    label: null,
    items: [{ label: "Marketplace", href: "/dashboard/marketplace", icon: Store }],
  },
  {
    label: "Settings",
    items: [
      { label: "Team", href: "/dashboard/team", icon: Users },
      { label: "API Keys", href: "/dashboard/settings/api-keys", icon: Key },
      { label: "Preferences", href: "/dashboard/settings", icon: SettingsIcon },
    ],
  },
];

const ALL_HREFS = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.href));

function isActive(itemHref: string, pathname: string): boolean {
  if (itemHref === "/dashboard") return pathname === "/dashboard";
  // If a longer registered href matches the pathname, defer to that one.
  const longer = ALL_HREFS.find(
    (h) => h !== itemHref && h.startsWith(itemHref + "/") && (pathname === h || pathname.startsWith(h + "/"))
  );
  if (longer) return false;
  return pathname === itemHref || pathname.startsWith(itemHref + "/");
}

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
  const groups = useMemo(() => NAV_GROUPS, []);
  return (
    <>
      <nav className="flex flex-col gap-4 p-4">
        {groups.map((group, gi) => (
          <div key={`group-${gi}`} className="flex flex-col gap-1">
            {group.label && (
              <div className="px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                {group.label}
              </div>
            )}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href, pathname);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="truncate">{item.label}</span>
                  {item.badge && (
                    <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
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

  const { mode } = useBackendMode();
  const demo = mode === "demo";

  useEffect(() => {
    if (mode === "loading") return;
    if (demo) {
      setUserEmail("demo@forge.dev");
      document.cookie = "forge_demo=1; path=/";
      return;
    }
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
    document.cookie = "forge_demo=; max-age=0; path=/";
    await authLogout();
    window.location.href = "/";
  }

  const logo = (
    <div className="flex h-16 items-center gap-2 border-b border-border px-6">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
        F
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
            <SheetContent side="left" className="w-64 p-0 flex flex-col overflow-y-auto">
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
              F
            </div>
            <span className="font-semibold">Forge</span>
          </div>
        </header>

        {/* Demo mode banner */}
        {demo && (
          <div className="bg-yellow-900/50 border-b border-yellow-700 px-4 py-2 text-sm text-yellow-200 text-center">
            Exploring demo mode with simulated data
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
