import * as React from "react";
import { CheckCircle2, Circle, CircleAlert, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type ProgressTone = "blue" | "cyan" | "emerald" | "amber" | "red" | "slate";

const toneClasses: Record<ProgressTone, string> = {
  blue: "bg-blue-600",
  cyan: "bg-cyan-600",
  emerald: "bg-emerald-600",
  amber: "bg-amber-500",
  red: "bg-red-600",
  slate: "bg-slate-500",
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
      <div className="h-2 overflow-hidden rounded-full bg-slate-100 ring-1 ring-inset ring-slate-200">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700 ease-out motion-reduce:transition-none",
            toneClasses[tone],
          )}
          style={{ width: `${safeValue}%` }}
        />
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