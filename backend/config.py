from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    max_followups: int = 2
    helper_cooldown_seconds: int = 5
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    groq_smart_model: str = "openai/gpt-oss-120b"


settings = Settings()
