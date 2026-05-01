import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(value >= 100 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

export function formatNumber(value: number): string {
  return value.toLocaleString();
}

export function formatDate(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const date = typeof input === "string" ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function formatRelative(input: string | null | undefined): string {
  if (!input) return "Never";
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return "Never";
  const diffSeconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (diffSeconds < 60) return "just now";
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return `${Math.floor(diffSeconds / 86400)}d ago`;
}

export function statusVariant(
  status: string,
): "default" | "success" | "warning" | "danger" | "muted" | "info" {
  const value = status.toLowerCase();
  if (["active", "completed", "ready", "success", "live"].includes(value)) return "success";
  if (["pending", "processing", "queued"].includes(value)) return "info";
  if (["archived", "disabled", "revoked"].includes(value)) return "muted";
  if (["failed", "error", "suspended"].includes(value)) return "danger";
  return "default";
}
