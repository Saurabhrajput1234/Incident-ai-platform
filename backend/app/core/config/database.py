from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/incident_ai"

    class Config:
        env_file = ".env"
        case_sensitive = True
