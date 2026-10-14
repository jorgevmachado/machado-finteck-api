from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            PROJECT_ROOT / ".env",
            PROJECT_ROOT / ".env.local",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ALGORITHM: str
    REDIS_URL: str | None = None
    REDIS_HOST: str
    REDIS_PORT: int
    SECRET_KEY: str
    DATABASE_URL: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REDIS_CACHE_TTL_SECONDS: int = 3600
    POKEAPI_BASE_URL: str = "https://pokeapi.co/api/v2"
    POKEAPI_VERIFY_SSL: bool = False
    POKEAPI_CA_BUNDLE: str | None = None
