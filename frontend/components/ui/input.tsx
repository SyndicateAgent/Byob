import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, type, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  const isFileInput = type === "file";

  return (
    <input
      type={type}
      className={cn(
        "h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm outline-none transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100",
        isFileInput &&
          "h-auto min-h-12 cursor-pointer bg-[linear-gradient(180deg,rgba(255,255,255,0.98)_0%,rgba(248,250,252,0.98)_100%)] px-2 py-1.5 pr-2 text-slate-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)] hover:border-slate-400 hover:bg-white file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-slate-950 file:px-3.5 file:py-2 file:text-sm file:font-medium file:text-white file:shadow-sm file:transition-colors file:duration-200 hover:file:bg-slate-800",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100",
        className,
      )}
      {...props}
    />
  );
}
