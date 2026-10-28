from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.settings import get_settings

_settings = get_settings()
_connect = {}
if _settings.database_url.startswith("sqlite"):
    _connect["check_same_thread"] = False

engine = create_engine(_settings.database_url, connect_args=_connect)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_schema() -> None:
    from app.models import Base

    Base.metadata.create_all(engine)
