const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("es_access_token");
}

let refreshInFlight: Promise<boolean> | null = null;

// Concurrent 401s share one refresh, since a page often fires several requests at once.
function refreshAccessToken(): Promise<boolean> {
  const refreshToken = typeof window === "undefined" ? null : window.localStorage.getItem("es_refresh_token");
  if (!refreshToken) return Promise.resolve(false);
  refreshInFlight ??= fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
    .then(async (res) => {
      if (!res.ok) return false;
      const tokens = await res.json();
      setAuthTokens(tokens.access_token, tokens.refresh_token);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

function errorMessage(body: unknown, status: number): string {
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors arrive as a list of { loc, msg }.
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = d.loc?.[d.loc.length - 1];
        const message = (d.msg ?? "is invalid").replace(/^Value error, /, "");
        return typeof field === "string" ? `${field.replace(/_/g, " ")}: ${message}` : message;
      })
      .join("; ");
  }
  return `Request failed with status ${status}`;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { auth?: boolean; idempotencyKey?: string; isRetry?: boolean } = {}
): Promise<T> {
  const { auth = true, idempotencyKey, isRetry = false, ...init } = options;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401 && auth && !isRetry && (await refreshAccessToken())) {
    return apiFetch<T>(path, { ...options, isRetry: true });
  }

  if (res.status === 204) return undefined as T;

  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    throw new ApiError(errorMessage(body, res.status), res.status);
  }

  return body as T;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path, { method: "GET" }),
  post: <T>(path: string, data?: unknown, opts?: { idempotencyKey?: string; auth?: boolean }) =>
    apiFetch<T>(path, { method: "POST", body: data ? JSON.stringify(data) : undefined, ...opts }),
  patch: <T>(path: string, data?: unknown) => apiFetch<T>(path, { method: "PATCH", body: data ? JSON.stringify(data) : undefined }),
};

export function setAuthTokens(access: string, refresh: string) {
  window.localStorage.setItem("es_access_token", access);
  window.localStorage.setItem("es_refresh_token", refresh);
}

export function clearAuthTokens() {
  window.localStorage.removeItem("es_access_token");
  window.localStorage.removeItem("es_refresh_token");
}
