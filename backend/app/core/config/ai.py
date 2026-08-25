from pydantic_settings import BaseSettings

class AISettings(BaseSettings):
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_MAX_TOKENS: int = 1024
    GROQ_TEMPERATURE: float = 0.0

    class Config:
        env_file = ".env"
        case_sensitive = True
