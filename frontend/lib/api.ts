const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "byob_access_token";
const API_KEY_KEY = "byob_api_key";

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

export function getApiKey() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(API_KEY_KEY);
}

export function setApiKey(apiKey: string) {
  window.localStorage.setItem(API_KEY_KEY, apiKey);
}

interface RequestOptions extends RequestInit {
  auth?: "jwt" | "api-key" | "none";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (options.auth !== "none") {
    if (options.auth === "api-key") {
      const apiKey = getApiKey();
      if (apiKey) headers.set("X-API-Key", apiKey);
    } else {
      const token = getToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
  if (response.status === 401) {
    clearToken();
    redirectToLogin();
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
