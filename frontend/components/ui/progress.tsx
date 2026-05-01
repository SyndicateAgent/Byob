import * as React from "react";
import { CheckCircle2, Circle, CircleAlert, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type ProgressTone = "blue" | "cyan" | "emerald" | "amber" | "red" | "slate";

const toneClasses: Record<ProgressTone, string> = {
  blue: "from-blue-600 via-sky-500 to-cyan-500",
  cyan: "from-cyan-600 via-sky-500 to-blue-500",
  emerald: "from-emerald-600 via-teal-500 to-cyan-500",
  amber: "from-amber-500 via-orange-500 to-rose-500",
  red: "from-red-600 via-rose-500 to-orange-500",
  slate: "from-slate-500 via-slate-400 to-slate-500",
};

export interface ProgressBarProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number;
  label?: string;
  detail?: string;
  tone?: ProgressTone;
  indeterminate?: boolean;
  showValue?: boolean;
}

export function ProgressBar({
  value,
  label,
  detail,
  tone = "blue",
  indeterminate = false,
  showValue = true,
  className,
  ...props
}: ProgressBarProps) {
  const safeValue = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <div className={cn("space-y-2", className)} aria-busy={indeterminate || undefined} {...props}>
      {(label || detail || showValue) && (
        <div className="flex items-center justify-between gap-3 text-xs">
          <div className="min-w-0">
            {label && <p className="truncate font-medium text-slate-700">{label}</p>}
            {detail && <p className="truncate text-slate-500">{detail}</p>}
          </div>
          {showValue && <span className="font-medium tabular-nums text-slate-500">{safeValue}%</span>}
        </div>
      )}
      <div className="h-2.5 overflow-hidden rounded-full border border-slate-200 bg-slate-100 shadow-inner">
        <div
          className={cn(
            "relative h-full rounded-full bg-gradient-to-r",
            toneClasses[tone],
          )}
          style={{ width: `${safeValue}%` }}
        >
          <span
            className="absolute inset-0 opacity-30"
            style={{
              backgroundImage:
                "linear-gradient(45deg, rgba(255,255,255,.55) 25%, transparent 25%, transparent 50%, rgba(255,255,255,.55) 50%, rgba(255,255,255,.55) 75%, transparent 75%, transparent)",
              backgroundSize: "16px 16px",
            }}
          />
        </div>
      </div>
    </div>
  );
}

export interface StepItem {
  label: string;
  state: "idle" | "active" | "done" | "error";
}

export function StepRail({ steps, className }: { steps: StepItem[]; className?: string }) {
  return (
    <div className={cn("grid gap-2 sm:grid-cols-2 lg:grid-cols-4", className)}>
      {steps.map((step) => {
        const Icon =
          step.state === "done"
            ? CheckCircle2
            : step.state === "error"
              ? CircleAlert
              : step.state === "active"
                ? Loader2
                : Circle;
        return (
          <div
            key={step.label}
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition-all duration-300",
              step.state === "active" && "border-cyan-200 bg-cyan-50 text-cyan-800 shadow-sm",
              step.state === "done" && "border-emerald-200 bg-emerald-50 text-emerald-800",
              step.state === "error" && "border-red-200 bg-red-50 text-red-700",
              step.state === "idle" && "border-slate-200 bg-white text-slate-500",
            )}
          >
            <Icon className={cn("h-3.5 w-3.5", step.state === "active" && "animate-spin")} />
            <span className="truncate font-medium">{step.label}</span>
          </div>
        );
      })}
    </div>
  );
}