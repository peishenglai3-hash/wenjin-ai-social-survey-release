/**
 * Authenticated fetch helper — wraps native fetch with JWT Bearer token.
 *
 * Use this for raw fetch calls that need authentication. For Axios-based
 * API calls, use api/client.ts which already has interceptors.
 */

import { getAccessToken } from "../api/client";

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const accessToken = getAccessToken();
  if (accessToken && accessToken !== "guest") {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  return headers;
}

/**
 * Fetch wrapper that automatically includes JWT auth headers.
 * Falls back gracefully if no token is stored (for public endpoints).
 */
export async function authFetch(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const authHeaders = getAuthHeaders();
  return fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      ...authHeaders,
      ...(options.headers as Record<string, string> || {}),
    },
  });
}

export { getAuthHeaders };
