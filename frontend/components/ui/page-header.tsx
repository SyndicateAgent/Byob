import * as React from "react";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("animate-fade-up flex items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold text-slate-950">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-500">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

export function MetricTile({
  label,
  value,
  hint,
  icon,
  accent = "blue",
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  accent?: "blue" | "cyan" | "emerald" | "amber";
}) {
  const accents = {
    blue: "bg-blue-50 text-blue-700 border-blue-100",
    cyan: "bg-cyan-50 text-cyan-700 border-cyan-100",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-100",
    amber: "bg-amber-50 text-amber-700 border-amber-100",
  };

  return (
    <div className="animate-fade-up rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase text-slate-500">{label}</p>
        <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg border", accents[accent])}>{icon}</div>
      </div>
      <p className="mt-4 text-2xl font-semibold text-slate-950">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}