import { useState, useEffect, useCallback, type ReactNode } from "react";
import api, { setAccessToken as setClientAccessToken } from "../api/client";
import { clearOfflineQueue } from "../services/offlineQueue";
import { AppCtx, type UserProfile, type SurveyProject, type AuthUser } from "./contextValue";

function getInitialTheme(): string {
  try {
    const saved = localStorage.getItem("user_profile");
    if (saved) {
      const p = JSON.parse(saved);
      if (p.theme_preference) return p.theme_preference;
    }
    const themeOnly = localStorage.getItem("app_theme");
    if (themeOnly) return themeOnly;
  } catch { /* ignore */ }
  return "academic";
}
export function AppProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<UserProfile | null>(() => {
    try {
      const saved = localStorage.getItem("user_profile");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [project, setProject] = useState<SurveyProject | null>(() => {
    try {
      const saved = localStorage.getItem("current_project");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [theme, setThemeState] = useState<string>(getInitialTheme);

  // ── Auth state ──────────────────────────────────────────
  const [access_token, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);

  const isAuthenticated = !!user && !!access_token;

  // Validate stored token on mount
  useEffect(() => {
    const bootstrapSession = async () => {
      // One-time migration path for clients that still have a legacy token pair.
      let legacyRefreshToken: string | undefined;
      try {
        const saved = localStorage.getItem("wenjin_auth");
        if (saved) legacyRefreshToken = JSON.parse(saved).refresh_token || undefined;
      } catch { /* ignore malformed legacy state */ }

      try {
        const resp = await api.post(
          "/auth/refresh",
          legacyRefreshToken ? { refresh_token: legacyRefreshToken } : {},
        );
        const at = resp.data.access_token as string;
        setAccessToken(at);
        setClientAccessToken(at);
        const me = await api.get("/auth/me", {
          headers: { Authorization: `Bearer ${at}` },
        });
        setUser(me.data);
      } catch {
        setAccessToken(null);
        setClientAccessToken(null);
      } finally {
        localStorage.removeItem("wenjin_auth");
        setIsAuthLoading(false);
      }
    };
    void bootstrapSession();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const resp = await api.post("/auth/login", { email, password });
    const { access_token: at } = resp.data;
    setAccessToken(at);
    setClientAccessToken(at);
    const me = await api.get("/auth/me", {
      headers: { Authorization: `Bearer ${at}` },
    });
    setUser(me.data);
  }, []);

  const register = useCallback(async (
    email: string,
    password: string,
    display_name: string,
    captcha_token: string,
    captcha_answer: string,
  ) => {
    // Register then auto-login
    await api.post("/auth/register", {
      email,
      password,
      display_name,
      captcha_token,
      captcha_answer,
    });
    await login(email, password);
  }, [login]);

  // ── Guest mode ──────────────────────────────────────────
  const loginGuest = useCallback(() => {
    const guestId = `guest_${crypto.randomUUID().slice(0, 8)}`;
    const guestUser: AuthUser = {
      id: 0,
      email: `${guestId}@guest.wenjin`,
      display_name: `游客${guestId.slice(-4)}`,
      role: "guest",
      is_active: true,
    };
    void api.post("/auth/logout").catch(() => {});
    clearOfflineQueue();
    setUser(guestUser);
    setAccessToken("guest");
    setClientAccessToken(null);
    // Guest session — stored separately from auth tokens
    localStorage.setItem("wenjin_guest", JSON.stringify({
      guestId, displayName: guestUser.display_name, createdAt: new Date().toISOString(),
    }));
  }, []);
  const sendSmsCode = useCallback(async (
    phone: string,
    captcha_token: string,
    captcha_answer: string,
  ) => {
    await api.post("/auth/send-sms", {
      phone,
      captcha_token,
      captcha_answer,
    });
  }, []);

  const loginPhone = useCallback(async (phone: string, sms_code: string) => {
    const resp = await api.post("/auth/login/phone", { phone, sms_code });
    const { access_token: at } = resp.data;
    setAccessToken(at);
    setClientAccessToken(at);
    const me = await api.get("/auth/me", {
      headers: { Authorization: `Bearer ${at}` },
    });
    setUser(me.data);
  }, []);

  const registerPhone = useCallback(async (
    phone: string,
    sms_code: string,
    display_name: string,
    captcha_token: string,
    captcha_answer: string,
  ) => {
    await api.post("/auth/register/phone", {
      phone,
      sms_code,
      display_name,
      captcha_token,
      captcha_answer,
    });
    // Auto-login after phone registration
    await loginPhone(phone, sms_code);
  }, [loginPhone]);

  const logout = useCallback(() => {
    // Fire-and-forget to revoke server-side refresh token
    void api.post("/auth/logout").catch(() => {});
    setAccessToken(null);
    setClientAccessToken(null);
    setUser(null);
    localStorage.removeItem("wenjin_auth");
    clearOfflineQueue();
  }, []);

  const refreshToken = useCallback(async (): Promise<boolean> => {
    try {
      const resp = await api.post("/auth/refresh", {});
      const { access_token: at } = resp.data;
      setAccessToken(at);
      setClientAccessToken(at);
      return true;
    } catch {
      logout();
      return false;
    }
  }, [logout]);

  // ── ORCID OAuth ──────────────────────────────────────────
  const orcidLogin = useCallback(async () => {
    // Fetch ORCID authorize URL and redirect
    const resp = await api.get("/auth/orcid", { params: { redirect_to: "/" } });
    const { authorize_url, state } = resp.data;
    // Store state in sessionStorage for CSRF verification
    sessionStorage.setItem("orcid_state", state);
    // Redirect to ORCID
    window.location.href = authorize_url;
  }, []);

  const orcidExchange = useCallback(async (authCode: string) => {
    const resp = await api.post("/auth/orcid/exchange", { auth_code: authCode });
    const { access_token: at } = resp.data;
    setAccessToken(at);
    setClientAccessToken(at);
    const me = await api.get("/auth/me", {
      headers: { Authorization: `Bearer ${at}` },
    });
    setUser(me.data);
  }, []);

  const setTheme = (t: string) => {
    setThemeState(t);
    if (profile) {
      const updated = { ...profile, theme_preference: t };
      setProfile(updated);
      api.post("/profile", { id: profile.id, theme_preference: t }).catch(() => {});
    }
  };

  // Apply theme to <html> element
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("app_theme", theme);
  }, [theme]);

  // ── Apply ui_font_size setting to DOM ──
  useEffect(() => {
    const size = profile?.ui_font_size || "medium";
    document.documentElement.setAttribute("data-font-size", size);
  }, [profile?.ui_font_size]);

  // ── Apply ui_high_contrast setting to DOM ──
  useEffect(() => {
    if (profile?.ui_high_contrast) {
      document.documentElement.setAttribute("data-high-contrast", "true");
    } else {
      document.documentElement.removeAttribute("data-high-contrast");
    }
  }, [profile?.ui_high_contrast]);

  // Sync theme from profile on first load
  useEffect(() => {
    if (profile?.theme_preference && profile.theme_preference !== theme) {
      void Promise.resolve().then(() => setThemeState(profile.theme_preference!));
    }
  }, [profile?.theme_preference, theme]);

  useEffect(() => {
    if (profile) {
      localStorage.setItem("user_profile", JSON.stringify(profile));
    } else {
      localStorage.removeItem("user_profile");
    }
  }, [profile]);

  useEffect(() => {
    if (project) {
      localStorage.setItem("current_project", JSON.stringify(project));
    } else {
      localStorage.removeItem("current_project");
    }
  }, [project]);

  return (
    <AppCtx.Provider value={{
      profile, setProfile, project, setProject, theme, setTheme,
      access_token, user, isAuthenticated, isAuthLoading,
      login, loginPhone, loginGuest, register, registerPhone, sendSmsCode, logout, refreshToken,
      orcidLogin, orcidExchange,
    }}>
      {children}
    </AppCtx.Provider>
  );
}
