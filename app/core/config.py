from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cors_origins: str  # 쉼표로 구분
    farmmap_api_key: str
    vworld_api_key: str
    anthropic_api_key: str = ""  # 선택: 포장지 OCR(/ocr/pesticide-labels)만 쓴다


settings = Settings()
