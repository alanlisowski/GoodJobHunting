from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Required on purpose: an empty CAPTURE_TOKEN would let anyone in.
    anthropic_api_key: SecretStr
    capture_token: SecretStr
    db_path: str = "./job_radar.db"


settings = Settings()
