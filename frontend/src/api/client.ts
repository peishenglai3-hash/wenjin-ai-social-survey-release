import axios from "axios";
import config from "../config";

const api = axios.create({
  baseURL: `${config.apiBaseUrl}/api/v1`,
  timeout: 120000,
  withCredentials: true,
});

// Access tokens live only in memory. Refresh tokens are kept in an HttpOnly
// cookie by the backend and are never read by JavaScript.
let inMemoryAccessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  inMemoryAccessToken = token;
}

export function getAccessToken(): string | null {
  return inMemoryAccessToken;
}

// ── 401 Refresh Queue ─────────────────────────────────────
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: any) => void;
}> = [];

function getToken(): string | null {
  return inMemoryAccessToken;
}

function processQueue(error: any, token: string | null = null) {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  failedQueue = [];
}

// Request interceptor — inject Bearer token (skip for guest)
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token && token !== "guest") {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — handle 401 with auto-refresh
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const originalRequest = err.config;

    // Only attempt refresh for 401s that aren't auth endpoints themselves
    if (
      err.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes("/auth/login") &&
      !originalRequest.url?.includes("/auth/register") &&
      !originalRequest.url?.includes("/auth/refresh")
    ) {
      if (isRefreshing) {
        // Queue this request until refresh completes
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch(() => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const resp = await axios.post(
          `${config.apiBaseUrl}/api/v1/auth/refresh`,
          {},
          { withCredentials: true },
        );
        const { access_token: newAccess } = resp.data;
        setAccessToken(newAccess);
        processQueue(null, newAccess);
        originalRequest.headers.Authorization = `Bearer ${newAccess}`;
        return api(originalRequest);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        // Clear auth — force re-login
        setAccessToken(null);
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    console.error("API error:", err.message);
    return Promise.reject(err);
  },
);

export default api;
