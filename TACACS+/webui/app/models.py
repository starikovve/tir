from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    """Учётная запись веб-интерфейса. Это не пользователь внутри tac_plus-ng.cfg."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Хеш argon2id. Открытый пароль не хранится.
    password_hash: Mapped[str] = mapped_column(String(255))
    # admin — полный доступ; user — только свои сессии, свой журнал и смена своего пароля.
    role: Mapped[str] = mapped_column(String(16), default="user", index=True)
    group_name: Mapped[str] = mapped_column(String(64), default="")


class Device(Base):
    """Карточка NAS в инвентаре веб-интерфейса. В tac_plus-ng.cfg сама не попадает."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(64), index=True)
    shared_key: Mapped[str] = mapped_column(String(256))
    group_name: Mapped[str] = mapped_column(String(64), default="")
    vendor: Mapped[str] = mapped_column(String(16), default="other")
