"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  Bot,
  Database,
  ExternalLink,
  FileText,
  HardDrive,
  LayoutDashboard,
  LogOut,
  Plug,
  Search,
  Server,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  clearToken,
  getCurrentUserFromToken,
  getToken,
  MINIO_CONSOLE_URL,
  QDRANT_DASHBOARD_URL,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: ["admin", "editor", "viewer"] },
  { href: "/knowledge-bases", label: "Knowledge Bases", icon: BookOpen, roles: ["admin", "editor", "viewer"] },
  { href: "/documents", label: "Documents", icon: FileText, roles: ["admin", "editor", "viewer"] },
  { href: "/retrieval", label: "Retrieval Console", icon: Search, roles: ["admin", "editor", "viewer"] },
  { href: "/agent", label: "QA Agent", icon: Bot, roles: ["admin", "editor", "viewer"] },
  { href: "/mcp", label: "MCP Guide", icon: Plug, roles: ["admin", "editor", "viewer"] },
  { href: "/users", label: "Users", icon: Users, roles: ["admin"] },
];

const externalWebUis = [
  { href: MINIO_CONSOLE_URL, label: "MinIO", icon: HardDrive },
  { href: QDRANT_DASHBOARD_URL, label: "Qdrant", icon: Database },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === "/login";
  const [authChecked, setAuthChecked] = useState(false);
  const [role, setRole] = useState<string>("viewer");
  const [email, setEmail] = useState<string>("");

  useEffect(() => {
    if (!isLogin && !getToken()) {
      router.replace("/login");
      return;
    }
    const decoded = getCurrentUserFromToken();
    if (decoded) {
      setRole(decoded.role);
      setEmail(decoded.email);
    }
    setAuthChecked(true);
  }, [isLogin, router]);

  const visibleNav = useMemo(() => navItems.filter((item) => item.roles.includes(role)), [role]);

  if (isLogin) {
    return <main className="min-h-screen bg-slate-50">{children}</main>;
  }

  if (!authChecked) {
    return <main className="min-h-screen bg-slate-50" />;
  }

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 flex w-64 flex-col border-r border-slate-200 bg-white/95 backdrop-blur">
        <div className="flex items-center gap-3 border-b border-slate-200 px-6 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-950 text-white shadow-sm">
            <Server className="h-4 w-4" />
          </div>
          <div>
            <p className="font-semibold leading-tight">BYOB Console</p>
            <p className="text-xs text-slate-500">Self-hosted vector DB</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                  active
                    ? "bg-blue-50 text-blue-700 shadow-sm"
                    : "text-slate-600 hover:translate-x-0.5 hover:bg-slate-100 hover:text-slate-900",
                )}
              >
                <Icon className="h-4 w-4 transition-transform duration-200 group-hover:scale-110" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-slate-200 px-4 py-4">
          <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              <span>External Web UIs</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </div>
            <div className="space-y-2">
              {externalWebUis.map((item) => {
                const Icon = item.icon;
                return (
                  <Button
                    key={item.label}
                    asChild
                    variant="outline"
                    className="h-9 w-full justify-start gap-2 px-3 text-xs"
                  >
                    <a href={item.href} target="_blank" rel="noreferrer" title={item.href}>
                      <Icon className="h-3.5 w-3.5" />
                      <span className="min-w-0 flex-1 text-left">{item.label}</span>
                      <ExternalLink className="h-3.5 w-3.5 text-slate-400" />
                    </a>
                  </Button>
                );
              })}
            </div>
          </div>
          <div className="mb-3 truncate text-xs">
            <p className="truncate font-medium text-slate-800" title={email}>
              {email || "Signed in"}
            </p>
            <p className="capitalize text-slate-500">{role}</p>
          </div>
          <Button
            variant="outline"
            className="w-full justify-center gap-2"
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </aside>
      <main className="ml-64 min-h-screen p-8">
        <div className="mx-auto w-full max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
