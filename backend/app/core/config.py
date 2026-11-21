from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MetaAnalyzer"
    environment: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"
    database_url: str = "sqlite+aiosqlite:///./metaanalyzer.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:5173"
    storage_root: str = "./storage/evidence"
    max_upload_size_mb: int = 2048

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
