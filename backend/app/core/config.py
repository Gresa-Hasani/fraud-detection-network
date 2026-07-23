"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings, sourced from the environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="change_me_locally")
    neo4j_database: str = Field(default="neo4j")

    # Backend
    backend_port: int = Field(default=8000)
    backend_cors_origins: str = Field(default="http://localhost:5173")
    log_level: str = Field(default="INFO")
    api_key: str = Field(default="change_me_locally")

    # Fraud detection defaults (overridable per-rule at call time)
    default_shared_device_min_customers: int = Field(default=5)
    default_shared_ip_min_customers: int = Field(default=5)
    default_cycle_min_length: int = Field(default=3)
    default_cycle_max_length: int = Field(default=6)
    default_cycle_time_window_hours: int = Field(default=72)
    default_cycle_amount_tolerance_pct: float = Field(default=0.1)
    default_rapid_pass_through_minutes: int = Field(default=30)
    default_rapid_pass_through_min_pct: float = Field(default=0.85)
    default_fan_in_min_sources: int = Field(default=10)
    default_fan_out_min_targets: int = Field(default=10)
    default_fan_window_hours: int = Field(default=24)
    default_structuring_threshold: float = Field(default=10000.0)
    default_structuring_margin_pct: float = Field(default=0.1)
    default_structuring_window_hours: int = Field(default=72)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
