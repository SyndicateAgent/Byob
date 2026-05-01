import * as React from "react";
import { Activity, Database, Network, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export function InlineSpinner({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin", className)} />
  );
}

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("shimmer-surface rounded-md bg-slate-100", className)} {...props} />;
}

export function PipelineLoader({
  label = "Running retrieval pipeline",
  detail,
  className,
}: {
  label?: string;
  detail?: string;
  className?: string;
}) {
  const nodes = [Sparkles, Database, Network, Activity];

  return (
    <div className={cn("rounded-lg border border-cyan-100 bg-cyan-50/70 p-4", className)}>
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-cyan-950">{label}</p>
          {detail && <p className="text-xs text-cyan-700">{detail}</p>}
        </div>
        <div className="relative h-9 w-9 rounded-full bg-white text-cyan-700 shadow-sm">
          <span className="absolute inset-1 rounded-full border border-cyan-200" style={{ animation: "pulse-ring 1.6s ease-in-out infinite" }} />
          <Activity className="absolute left-1/2 top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2" />
        </div>
      </div>
      <div className="grid grid-cols-[auto_1fr_auto_1fr_auto_1fr_auto] items-center gap-2">
        {nodes.map((Icon, index) => (
          <React.Fragment key={index}>
            <div
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-200 bg-white text-cyan-700 shadow-sm"
              style={{ animation: `float-y 2.4s ease-in-out ${index * 120}ms infinite` }}
            >
              <Icon className="h-4 w-4" />
            </div>
            {index < nodes.length - 1 && (
              <div className="relative h-1 overflow-hidden rounded-full bg-cyan-100">
                <span className="absolute inset-y-0 w-1/2 rounded-full bg-cyan-500" style={{ animation: `sweep 1.25s ease-in-out ${index * 160}ms infinite` }} />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}