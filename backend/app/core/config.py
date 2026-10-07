from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    secret_key: str
    database_url: str
    celery_broker_url: str = "redis://localhost:6379/0"
    cache_redis_url: str = "redis://localhost:6379/2"

    cookie_secure: bool = True
    session_idle_minutes: int = 120
    session_absolute_hours: int = 12
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    password_min_length: int = 10
    # requests allowed per client address (app.core.ratelimit); uploads per user or device
    rate_sign_in_per_15min: int = 60
    rate_otp_send_per_hour: int = 30
    rate_otp_check_per_15min: int = 60
    rate_uploads_per_hour: int = 600
    rate_limit_exempt: str = ""  # addresses or networks never limited, comma separated (the office, on sign-up day)

    files_dir: str = "/data/files"
    max_upload_mb: int = 10
    public_url: str = "http://localhost:8080"  # the address drivers open (activation links)
    messaging_provider: str = "log"  # "whatsapp" in production (Evolution API)
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = ""
    live_broker: str = "memory"  # "redis" in production: the API runs several worker processes
    hr_integration_mode: str = "off"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
