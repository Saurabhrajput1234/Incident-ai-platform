from pydantic_settings import BaseSettings

class AISettings(BaseSettings):
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    ANTHROPIC_MAX_TOKENS: int = 1024
    ANTHROPIC_TEMPERATURE: float = 0.0

    class Config:
        env_file = ".env"
        case_sensitive = True
