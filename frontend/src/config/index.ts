const config = {
  // Empty string = same-origin (production). Override via .env for local dev.
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
  appName: "AI 社会调查工作台",
  collaborationV1Enabled: import.meta.env.VITE_COLLABORATION_V1_ENABLED === "true",
};

export default config;
