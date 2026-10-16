import { createContext } from "react";

export interface UserProfile {
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
  theory_driven?: number;
  methodological_rigidity?: number;
  analysis_depth?: number;
  structure_preference?: number;
  participation_level?: number;
  tech_dependency?: number;
  writing_style?: number;
  learning_preference?: number;
  ai_temperature?: number;
  ai_model_pref?: string;
  ai_hint_frequency?: string;
  ui_font_size?: string;
  ui_high_contrast?: boolean;
  default_export_format?: string;
  auto_save_interval?: string;
}

export interface SurveyProject {
  id: number;
  title: string;
  research_direction: string | null;
  paradigm: string;
  phase: string;
  status: string;
}

export interface AuthUser {
  id: number;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
}

export interface AppState {
  profile: UserProfile | null;
  setProfile: (p: UserProfile | null) => void;
  project: SurveyProject | null;
  setProject: (p: SurveyProject | null) => void;
  theme: string;
  setTheme: (t: string) => void;
  access_token: string | null;
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

export const AppCtx = createContext<AppState>({
  profile: null,
  setProfile: () => {},
  project: null,
  setProject: () => {},
  theme: "academic",
  setTheme: () => {},
  access_token: null,
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
