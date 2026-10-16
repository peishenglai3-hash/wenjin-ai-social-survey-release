import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import api, { setAccessToken as setClientAccessToken } from "../api/client";
import { clearOfflineQueue } from "../services/offlineQueue";

interface UserProfile {
  id: number;
  mode: string;
  gender: string | null;
  role: string;
  experience_level: string;
  age_range: string | null;
  mbti: string | null;
  paradigm_preference: string;
  scenario_preference: string;
  theme_preference?: string;
  // Spectrum
  theory_driven?: number;
  methodological_rigidity?: number;
  analysis_depth?: number;
  structure_preference?: number;
  participation_level?: number;
  tech_dependency?: number;
  writing_style?: number;
  learning_preference?: number;
  // Settings
  ai_temperature?: number;
  ai_model_pref?: string;
  ai_hint_frequency?: string;
  ui_font_size?: string;
  ui_high_contrast?: boolean;
  default_export_format?: string;
  auto_save_interval?: string;
}

interface SurveyProject {
  id: number;
  title: string;
  research_direction: string | null;
  paradigm: string;
  phase: string;
  status: string;
}

// ── Auth types ─────────────────────────────────────────────
interface AuthUser {
  id: number;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
}

interface AuthState {
  access_token: string | null;
  refresh_token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  isAuthLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginPhone: (phone: string, sms_code: string) => Promise<void>;
  register: (email: string, password: string, display_name: string, captcha_token: string, captcha_answer: string) => Promise<void>;
  registerPhone: (phone: string, sms_code: string, display_name: string, captcha_token: string, captcha_answer: string) => Promise<void>;
  sendSmsCode: (phone: string, captcha_token: string, captcha_answer: string) => Promise<void>;
  loginGuest: () => void;
  logout: () => void;
  refreshToken: () => Promise<boolean>;
  orcidLogin: () => Promise<void>;
  orcidExchange: (authCode: string) => Promise<void>;
}

interface AppState extends AuthState {
  profile: UserProfile | null;
  setProfile: (p: UserProfile | null) => void;
  project: SurveyProject | null;
  setProject: (p: SurveyProject | null) => void;
  theme: string;
  setTheme: (t: string) => void;
}

const AppCtx = createContext<AppState>({
  profile: null,
  setProfile: () => {},
  project: null,
  setProject: () => {},
  theme: "academic",
  setTheme: () => {},
  // Auth defaults
  access_token: null,
  refresh_token: null,
  user: null,
  isAuthenticated: false,
  isAuthLoading: true,
  login: async () => {},
  loginPhone: async () => {},
  register: async () => {},
  registerPhone: async () => {},
  sendSmsCode: async () => {},
  loginGuest: () => {},
  logout: () => {},
  refreshToken: async () => false,
  orcidLogin: async () => {},
  orcidExchange: async () => {},
});

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
  // Refresh tokens are HttpOnly cookies; keep this field only for API shape compatibility.
  const refresh_token: string | null = null;
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
      setThemeState(profile.theme_preference);
    }
  }, [profile?.theme_preference]);

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
      access_token, refresh_token, user, isAuthenticated, isAuthLoading,
      login, loginPhone, loginGuest, register, registerPhone, sendSmsCode, logout, refreshToken,
      orcidLogin, orcidExchange,
    }}>
      {children}
    </AppCtx.Provider>
  );
}

export function useApp() {
  return useContext(AppCtx);
}
