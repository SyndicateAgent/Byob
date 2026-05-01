export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "byob_access_token";

export function apiUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function getToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export function redirectToLogin() {
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/login") {
    window.location.replace("/login");
  }
}

export interface DecodedToken {
  sub: string;
  email: string;
  role: string;
  exp: number;
}

export function decodeToken(token: string | null): DecodedToken | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const padded = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json =
      typeof atob === "function" ? atob(padded) : Buffer.from(padded, "base64").toString("utf-8");
    return JSON.parse(json) as DecodedToken;
  } catch {
    return null;
  }
}

export function getCurrentUserFromToken(): DecodedToken | null {
  return decodeToken(getToken());
}

interface RequestOptions extends RequestInit {
  auth?: "jwt" | "none";
}

export class ApiError extends Error {
  status: number;
  code: string | null;
  detail: unknown;

  constructor(status: number, message: string, code: string | null = null, detail: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("content-type") ?? "";
  let message = `Request failed: ${response.status}`;
  let code: string | null = null;
  let detail: unknown = null;
  if (contentType.includes("application/json")) {
    try {
      const body = (await response.json()) as Record<string, unknown>;
      const err = (body as { error?: { message?: string; code?: string; detail?: unknown } }).error;
      if (err && typeof err === "object") {
        message = err.message ?? message;
        code = err.code ?? null;
        detail = err.detail ?? null;
      } else if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((entry) => {
            if (entry && typeof entry === "object" && "msg" in entry) {
              return String((entry as { msg: unknown }).msg);
            }
            return JSON.stringify(entry);
          })
          .join(", ");
      }
    } catch {
      // fall through to text path
    }
  } else {
    try {
      message = (await response.text()) || message;
    } catch {
      // ignore
    }
  }
  return new ApiError(response.status, message, code, detail);
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (options.auth !== "none") {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(apiUrl(path), {
    ...options,
    headers,
  });
  if (response.status === 401 && options.auth !== "none") {
    clearToken();
    redirectToLogin();
  }
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
