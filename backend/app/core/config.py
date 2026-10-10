"""Central application settings. Environment is read only here (architecture §12)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # --- Required for the API and the health check ----------------------
    database_url: str = Field(min_length=1)
    redis_url: str = Field(min_length=1)
    s3_endpoint_url: str = Field(min_length=1)
    frontend_origin: str = Field(min_length=1)

    # Bounded timeout (seconds) for each dependency probe.
    health_timeout_seconds: float = 3.0

    # --- Required by the initializer (app.db.init_db), which validates them explicitly ---
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "assignflow-submissions"
    s3_region: str = "us-east-1"
    seed_demo_password: str | None = None

    # Initializer wait loop (architecture §10.3: retry every 2 s for up to 60 s).
    init_wait_interval_seconds: float = 2.0
    init_wait_timeout_seconds: float = 60.0

    # --- Reserved for later phases (declared, unused so far) ---
    jwt_secret: str | None = None
    jwt_expire_minutes: int = 120
    max_upload_mb: int = 10
    app_timezone_display: str = "Asia/Kolkata"
    # Background job for the 24-hour deadline reminders (switched off by the test configuration).
    reminder_scheduler_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
