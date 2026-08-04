from pydantic_settings import BaseSettings


class SecuritySettings(BaseSettings):
    SECRET_KEY: str = "changeme"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        case_sensitive = True
