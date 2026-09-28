from pathlib import Path
from typing import List, Literal, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url, URL

# Locate .env in backend/ or root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"
if not ENV_FILE.exists():
    ENV_FILE = BASE_DIR.parent / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database
    DATABASE_URL: str

    # Security & JWT. No default secret: a missing one must stop startup rather
    # than fall back to a value published in the repository.
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720  # 12 hours

    # Failed sign-ins tolerated per window, per (client, account) and per client
    LOGIN_MAX_FAILURES_PER_ACCOUNT: int = 5
    LOGIN_MAX_FAILURES_PER_CLIENT: int = 30
    LOGIN_FAILURE_WINDOW_SECS: int = 900

    # Background jobs
    ESCALATION_SWEEP_INTERVAL_SECS: int = 60
    NOTIFICATION_DISPATCH_INTERVAL_SECS: int = 30
    # Yesterday's silence does not change through the day, so this sweep is hourly
    # rather than per minute; it only needs to beat the first ward round.
    MISSED_CHECKIN_SWEEP_INTERVAL_SECS: int = 3600
    # "disabled" leaves escalation notifications queued and logs a warning;
    # "log" writes each one to the application log and marks it sent.
    NOTIFICATION_PROVIDER: Literal["disabled", "log"] = "disabled"

    # Patient WhatsApp messages. "disabled" leaves them queued and logs a warning;
    # "log" writes a line per message (no patient details) and marks it sent;
    # "meta" sends approved templates through the Graph API.
    WHATSAPP_PROVIDER: Literal["disabled", "log", "meta"] = "disabled"
    # The platform's own number, used for a hospital that has not connected one
    META_PHONE_NUMBER_ID: Optional[str] = None
    META_ACCESS_TOKEN: Optional[str] = None
    # Accepted in the webhook handshake besides each hospital's own verify token
    META_WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    # Signs webhook calls. Without it every webhook POST is refused.
    META_APP_SECRET: Optional[str] = None
    META_API_VERSION: str = "v21.0"
    # Where patients open their check-in link, and where Meta reaches the webhook
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    PUBLIC_API_BASE_URL: str = "http://localhost:8000"
    DAILY_DISPATCH_INTERVAL_SECS: int = 60

    # The check-in simulator: the /checkin episode picker and ?episode_id= access.
    # It has no sign-in and lists every active patient, so it is for demos on seeded
    # data only. Off, a check-in needs the link from the patient's WhatsApp reminder.
    CHECKIN_SIMULATOR_ENABLED: bool = False

    LOG_LEVEL: str = "INFO"

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def secret_is_strong(cls, value: str) -> str:
        if len(value) < 32 or value.startswith("change-this"):
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters and must not be the example "
                "placeholder. Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return value

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list of strings."""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def async_database_url(self) -> URL:
        """
        Dynamically adapts DATABASE_URL for asyncpg with Neon's PgBouncer pooler.
        Strips query parameters not recognized by asyncpg DSN and sets drivername.
        """
        u = make_url(self.DATABASE_URL)
        query = dict(u.query)
        # asyncpg receives ssl configuration via connect_args or ssl parameter
        query.pop("sslmode", None)
        query.pop("channel_binding", None)
        return u.set(drivername="postgresql+asyncpg", query=query)

settings = Settings()
