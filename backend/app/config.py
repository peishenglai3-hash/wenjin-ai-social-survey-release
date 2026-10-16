from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # Security
    jwt_secret: str = ""  # MUST be set via JWT_SECRET env var — no hardcoded default
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = "wenjin_refresh"
    # Local HTTP development may need False; production deployments must set True.
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: str = "lax"

    # Rate Limiting (per-IP limits)
    rate_limit_enabled: bool = True
    rate_limit_api_per_minute: int = 60
    rate_limit_ai_per_minute: int = 10
    rate_limit_auth_per_minute: int = 20
    # Only these direct peers may supply X-Forwarded-For/X-Real-IP.
    trusted_proxy_ips: list[str] = []

    # ── AI Provider: DeepSeek (text-heavy tasks: topic, questionnaire, analysis, export) ──
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-pro"

    # ── AI Cost Circuit Breaker (per-user limits) ──
    cost_limit_enabled: bool = True
    cost_limit_tokens_per_user_day: int = 2_000_000  # 2M tokens/user/day
    cost_limit_tokens_per_user_month: int = 30_000_000  # 30M tokens/user/month

    # ── AI Provider: Qwen / DashScope (vision + ASR for fieldwork) ──
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_vision_model: str = "qwen-vl-max"
    qwen_asr_model: str = "paraformer-realtime-v2"
    qwen_filetrans_model: str = "qwen3-asr-flash"

    # ── AI Provider: Volcano Engine / ARK (Doubao LLM — emotion + semantic analysis) ──
    volcano_api_key: str = ""
    volcano_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcano_emotion_model: str = "doubao-seed-2-0-pro-260215"  # Doubao Seed 2.0 Pro for emotion
    volcano_emotion_enabled: bool = True

    # ── AI Provider: Tencent Hunyuan (real-time tasks: hints, summarization, memory) ──
    hunyuan_api_key: str = ""
    hunyuan_base_url: str = "https://api.hunyuan.cloud.tencent.com/v1"
    hunyuan_model: str = "hunyuan-turbo"
    hunyuan_enabled: bool = True

    # Provider routing
    vision_provider: str = "qwen"  # qwen | deepseek | auto
    asr_provider: str = "qwen"     # qwen | volcano | xfyun | browser
    emotion_provider: str = "volcano"  # volcano | deepseek | qwen — multi-modal emotion LLM
    realtime_provider: str = "hunyuan"  # hunyuan | deepseek — hints, summarization, memory extraction

    # Versioned Open API gateway.  Credentials remain server-side; the fake
    # provider is opt-in for offline development and contract tests only.
    open_api_enabled: bool = True
    open_api_fake_enabled: bool = False
    open_api_max_messages: int = 64
    open_api_max_tokens: int = 8192
    qwen_model: str = "qwen-plus"

    # ── Xunfei ASR (legacy fallback) ──
    xf_app_id: str = ""
    xf_api_key: str = ""
    xf_api_secret: str = ""

    # ── Literature Search ──
    semantic_scholar_api_key: str = ""  # Free key from semanticscholar.org

    # ── FunASR (local speech engine — primary) ──
    funasr_asr_model: str = "iic/SenseVoiceSmall"
    funasr_vad_model: str = "fsmn-vad"
    funasr_spk_model: str = "cam++"
    funasr_emotion_model: str = "iic/emotion2vec_plus_large"
    funasr_device: str = "cpu"  # cpu | cuda:0
    funasr_batch_size_s: int = 300

    # ── Emotion Tracking ──
    emotion_sample_interval_s: float = 5.0
    emotion_enabled: bool = True

    # ── Realtime Pipeline ──
    realtime_summary_interval_s: int = 120
    realtime_hint_interval_s: int = 15

    # Database (SQLite for dev, PostgreSQL for prod)
    database_url: str = "sqlite+aiosqlite:///./app.db"

    # PostgreSQL connection (used when DATABASE_URL points to postgresql+asyncpg://)
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600  # Recycle connections after 1 hour

    # Redis (optional, for session buffering and ORCID state tokens)
    redis_url: str = "redis://localhost:6379/0"

    # ── ORCID OAuth (academic identity) ──
    orcid_client_id: str = ""
    orcid_client_secret: str = ""
    orcid_redirect_uri: str = ""
    orcid_sandbox: bool = True  # True = use sandbox.orcid.org, False = use orcid.org
    orcid_authorize_url: str = "https://sandbox.orcid.org/oauth/authorize"
    orcid_token_url: str = "https://sandbox.orcid.org/oauth/token"
    orcid_userinfo_url: str = "https://orcid.org/oauth/userinfo"

    # File upload
    upload_dir: str = "/tmp/wenjin-uploads"
    max_upload_mb: int = 500

    # Public-facing base URL for file download by third-party APIs (DashScope FileTrans).
    # Set PUBLIC_BASE_URL only in a deployment that intentionally exposes a callback URL.
    public_base_url: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        """Refuse empty, placeholder, or trivially short signing keys."""
        secret = value.strip()
        placeholders = {
            "replace-with-a-long-random-secret",
            "change-me",
            "changeme",
            "secret",
        }
        if len(secret) < 32 or secret.lower() in placeholders:
            raise ValueError(
                "JWT_SECRET must be a deployment-specific random value of at least 32 characters"
            )
        return secret


settings = Settings()
