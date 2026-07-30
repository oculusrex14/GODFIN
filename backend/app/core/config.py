from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_NAME: str = "GODFIN"
    VERSION: str = "0.1.0"
    DB_PATH: str = "godfin.db"
    HOST: str = "127.0.0.1"
    PORT: int = 5100
    API_V1_PREFIX: str = "/api/v1"
    LICENSE_API_URL: str = "https://godfin.vercel.app/api/license/verify"
    LICENSE_API_FALLBACK_URL: str = ""
    LICENSE_OFFLINE_GRACE_DAYS: int = 30
    WEBSITE_URL: str = "https://godfin.vercel.app"

    @property
    def database_path(self) -> Path:
        configured = Path(self.DB_PATH).expanduser()
        if configured.is_absolute():
            return configured
        return Path(__file__).resolve().parents[2] / configured

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

settings = Settings()
