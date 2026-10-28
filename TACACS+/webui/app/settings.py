import re
from functools import lru_cache

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Одна пара «число / окно». slowapi разбирает second, minute, hour, day.
_RATE = re.compile(r"^\d+/(second|minute|hour|day)$")


class Settings(BaseSettings):
    """Все параметры приходят из окружения или .env, не из кода.

    Секреты (APP_SECRET_KEY, BOOTSTRAP_ADMIN_PASSWORD) без значения по умолчанию
    в репозиторий не попадают: пустой ключ процесс не запускает.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_secret_key: str
    database_url: str = "sqlite:///./tacacs-ui.sqlite"
    accounting_log: str = "/var/log/tac_plus-ng/acct"
    # true — флаг Secure у cookie. За HTTP его ставят false, иначе браузер cookie не сохранит.
    session_cookie_secure: bool = False
    bootstrap_admin_user: str = ""
    bootstrap_admin_password: str = ""
    # Лимит POST /login с одного адреса. Юнит systemd запускает один процесс uvicorn.
    login_rate_limit: str = "5/minute"

    @field_validator("app_secret_key")
    @classmethod
    def secret_long_enough(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 16:
            raise ValueError("APP_SECRET_KEY должен быть не короче 16 символов")
        return cleaned

    @field_validator("login_rate_limit")
    @classmethod
    def rate_limit_shape(cls, value: str) -> str:
        cleaned = value.strip()
        if not _RATE.fullmatch(cleaned):
            raise ValueError("LOGIN_RATE_LIMIT задаётся как число/second|minute|hour|day, например 5/minute")
        return cleaned


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(
            "Настройки веб-интерфейса не прочитаны. Секреты задаются только в окружении или в файле .env. "
            "Нужен APP_SECRET_KEY не короче 16 символов. " + str(exc)
        ) from exc
