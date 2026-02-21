"""
PURPOSE: Configuration settings for JSR Hydra trading system.

This module uses Pydantic Settings to manage configuration from environment
variables and .env files. All settings are validated and typed.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    PURPOSE: Central configuration class for JSR Hydra.

    Manages all environment-based settings including database connections,
    MT5 broker integration, Telegram notifications, and trading parameters.
    Settings are loaded from environment variables and .env file.
    """

    # Database & Cache Configuration
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@jsr-postgres:5432/jsr_hydra"
    REDIS_URL: str = "redis://jsr-redis:6379/0"

    # MT5 Broker Configuration
    MT5_HOST: str = "jsr-mt5"
    MT5_RPYC_PORT: int = 18812
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""
    MT5_REST_URL: str = "http://jsr-mt5:18812"
    MAX_TEST_LOTS: float = 0.01

    # Telegram Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Risk Management Settings
    MAX_DRAWDOWN_PCT: float = 15.0
    DAILY_LOSS_LIMIT_PCT: float = 5.0
    RISK_PER_TRADE_PCT: float = 1.0
    MIN_SIGNAL_CONFIDENCE: float = 0.3

    # System Settings
    APP_ENV: str = "development"
    DEBUG: bool = False
    DRY_RUN: bool = True
    LOG_LEVEL: str = "INFO"
    JWT_SECRET: str = "change-me-in-production"
    API_KEY: str = "change-me-in-production"

    # OpenAI LLM Configuration
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1/chat/completions"

    # Z.AI LLM Configuration
    ZAI_API_KEY: str = ""
    ZAI_MODEL: str = "glm-4.6"
    ZAI_BASE_URL: str = "https://api.z.ai/api/paas/v4/chat/completions"

    # Finnhub API Key (free tier — register at finnhub.io)
    # Used for economic calendar data in sentiment module
    FINNHUB_API_KEY: str = ""

    # Brain runtime selection (openai | zai)
    BRAIN_LLM_PROVIDER: str = "openai"
    # Writable directory for brain persistence files (memory, XP, allocator, RL state)
    BRAIN_DATA_DIR: str = "/app/data/brain"

    # TradingView Webhook Configuration
    # Shared secret used to authenticate inbound TradingView Pine Script webhooks.
    # Set this to a long random string in production and configure the same value
    # in your TradingView alert webhook URL body or X-Webhook-Secret header.
    TRADINGVIEW_WEBHOOK_SECRET: str = "jsr-hydra-tv-webhook-2024"

    # Admin Credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    # Default insecure values that must be changed for non-dev environments
    _INSECURE_DEFAULTS: dict[str, str] = {
        "JWT_SECRET": "change-me-in-production",
        "API_KEY": "change-me-in-production",
        "ADMIN_PASSWORD": "admin",
    }

    def is_production(self) -> bool:
        """
        PURPOSE: Determine whether the app is running in production mode.

        Returns:
            bool: True when APP_ENV indicates production.
        """
        return self.APP_ENV.strip().lower() in {"prod", "production"}

    def is_development(self) -> bool:
        """
        PURPOSE: Determine whether the app is running in development mode.

        Returns:
            bool: True when APP_ENV indicates development or debug is on.
        """
        return self.APP_ENV.strip().lower() in {"dev", "development"} or self.DEBUG

    def get_insecure_defaults(self) -> list[str]:
        """
        PURPOSE: Return list of settings that still use insecure default values.

        Returns:
            list[str]: Setting names that are still at their insecure defaults.
        """
        return [
            name for name, default_val in self._INSECURE_DEFAULTS.items()
            if getattr(self, name) == default_val
        ]

    def validate_credentials(self) -> None:
        """
        PURPOSE: Enforce that sensitive defaults are not used outside development.

        CALLED BY: Application startup (create_app / on_startup).

        In production/staging: raises ValueError with clear instructions.
        In development: returns the list of warnings for the caller to log.

        Raises:
            ValueError: If credentials are insecure defaults in non-dev mode.
        """
        insecure = self.get_insecure_defaults()
        if not insecure:
            return

        hint = (
            "Set these in your .env file or as environment variables:\n"
            + "\n".join(f"  {name}=<your-secure-value>" for name in insecure)
        )

        if not self.is_development():
            raise ValueError(
                f"SECURITY: Insecure default credentials detected for: "
                f"{', '.join(insecure)}.\n{hint}"
            )

    class Config:
        """Pydantic model configuration."""

        env_file: str = ".env"
        env_file_encoding: str = "utf-8"
        case_sensitive: bool = True


settings: Settings = Settings()
