from pydantic_settings import BaseSettings


class LoggingSettings(BaseSettings):
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True
