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

    # Telegram Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Risk Management Settings
    MAX_DRAWDOWN_PCT: float = 15.0
    DAILY_LOSS_LIMIT_PCT: float = 5.0
    RISK_PER_TRADE_PCT: float = 1.0

    # System Settings
    DEBUG: bool = False
    DRY_RUN: bool = True
    LOG_LEVEL: str = "INFO"
    JWT_SECRET: str = "change-me-in-production"
    API_KEY: str = "change-me-in-production"

    # Admin Credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    class Config:
        """Pydantic model configuration."""

        env_file: str = ".env"
        env_file_encoding: str = "utf-8"
        case_sensitive: bool = True


settings: Settings = Settings()
