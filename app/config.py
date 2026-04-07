from pydantic import BaseSettings


class Settings(BaseSettings):
    # Async SQLAlchemy URL. Example: postgresql+asyncpg://user:pass@db:5432/dbname
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # If true, disables SSL verification for outgoing requests (testing only)
    ETRADE_INSECURE: bool = False

    # App runtime settings
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8011

    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
