from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все параметры приходят из окружения или .env, не из кода."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_secret_key: str
    database_url: str = "sqlite:///./tacacs-ui.sqlite"
    accounting_log: str = "/var/log/tac_plus-ng/acct"
    session_cookie_secure: bool = False
    bootstrap_admin_user: str = ""
    bootstrap_admin_password: str = ""


def get_settings() -> Settings:
    return Settings()
