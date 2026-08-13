from pydantic_settings import BaseSettings

class AISettings(BaseSettings):
    GROQ_API_KEY: str
    GROQ_MODEL: str
    GROQ_MAX_TOKENS: int
    GROQ_TEMPERATURE: float

    class Config:
        env_file = ".env"
        case_sensitive = True
