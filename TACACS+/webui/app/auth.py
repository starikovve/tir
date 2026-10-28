import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.settings import get_settings

# argon2-cffi по умолчанию: argon2id, своя соль на каждый пароль.
_hasher = PasswordHasher()
_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
ROLES = ("admin", "user")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def valid_username(value: str) -> bool:
    return bool(_USERNAME.fullmatch(value))


def csrf_token(session: dict) -> str:
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


def csrf_ok(session: dict, provided: str) -> bool:
    expected = session.get("csrf") or ""
    if not expected or not provided:
        return False
    return secrets.compare_digest(expected, provided)


def bootstrap_admin(db: Session) -> None:
    """Создать первого admin, только когда таблица ещё пустая."""
    settings = get_settings()
    count = db.scalar(select(func.count()).select_from(User))
    if count:
        return
    username = settings.bootstrap_admin_user.strip()
    password = settings.bootstrap_admin_password
    if not username or not password or not valid_username(username):
        return
    db.add(
        User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            group_name="",
        )
    )
    db.commit()


def admin_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0)
