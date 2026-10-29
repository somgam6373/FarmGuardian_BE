from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cors_origins: str  # 쉼표로 구분
    farmmap_api_key: str
    vworld_api_key: str


settings = Settings()
