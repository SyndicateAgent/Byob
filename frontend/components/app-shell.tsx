"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BookOpen, FileText, Gauge, KeyRound, Search, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { clearToken, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/knowledge-bases", label: "Knowledge Bases", icon: BookOpen },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/api-keys", label: "API Keys", icon: KeyRound },
  { href: "/usage", label: "Usage", icon: Gauge },
  { href: "/retrieval", label: "Retrieval Console", icon: Search },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === "/login";
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    if (!isLogin && !getToken()) {
      router.replace("/login");
      return;
    }
    setAuthChecked(true);
  }, [isLogin, router]);

  if (isLogin) {
    return <main className="min-h-screen bg-slate-50">{children}</main>;
  }

  if (!authChecked) {
    return <main className="min-h-screen bg-slate-50" />;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <aside className="fixed inset-y-0 left-0 w-72 border-r border-slate-200 bg-white p-6">
        <div className="mb-8 flex items-center gap-3">
          <div className="rounded-lg bg-blue-600 p-2 text-white">
            <Settings className="h-5 w-5" />
          </div>
          <div>
            <h1 className="font-semibold">BYOB Console</h1>
            <p className="text-xs text-slate-500">Knowledge base BaaS</p>
          </div>
        </div>
        <nav className="space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  active ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-100",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <Button
          variant="outline"
          className="mt-8 w-full"
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
        >
          Sign out
        </Button>
      </aside>
      <main className="ml-72 min-h-screen p-8">{children}</main>
    </div>
  );
}
