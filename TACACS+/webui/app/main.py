import ipaddress
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.acct import active_sessions, filter_records, load_records
from app.auth import (
    ROLES,
    admin_count,
    bootstrap_admin,
    csrf_ok,
    csrf_token,
    hash_password,
    valid_username,
    verify_password,
)
from app.db import SessionLocal, init_schema
from app.models import Device, User
from app.settings import get_settings

settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
VENDORS = ("cisco", "junos", "huawei", "other")
PAGE_SIZE = 50


class LoginRequired(Exception):
    pass


class Forbidden(Exception):
    pass


class BadCsrf(Exception):
    pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_schema()
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title="TACACS+ lab UI", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    session_cookie="tacacs_ui",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def optional_user(request: Request, db: Session) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    return db.get(User, uid)


def require_user(request: Request, db: Session) -> User:
    user = optional_user(request, db)
    if user is None:
        raise LoginRequired()
    return user


def require_admin(request: Request, db: Session) -> User:
    """Роль user сюда не проходит: ответ 403, даже если подставить чужой id."""
    user = require_user(request, db)
    if user.role != "admin":
        raise Forbidden()
    return user


def render(request: Request, db: Session, name: str, status: int = 200, **extra):
    context = {
        "user": optional_user(request, db),
        "csrf": csrf_token(request.session),
        "flash": request.session.pop("flash", None),
    }
    context.update(extra)
    return templates.TemplateResponse(request, name, context, status_code=status)


async def posted(request: Request) -> dict[str, str]:
    form = await request.form()
    values = {key: str(form.get(key) or "") for key in form.keys()}
    if not csrf_ok(request.session, values.get("csrf_token", "")):
        raise BadCsrf()
    return values


def safe_next(value: str) -> str:
    if value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def like_pattern(raw: str) -> str:
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def sort_pair(sort: str, direction: str, allowed: dict[str, object], default: str):
    column = allowed.get(sort, allowed[default])
    descending = direction == "desc"
    return column, descending, sort if sort in allowed else default, "desc" if descending else "asc"


@app.exception_handler(LoginRequired)
async def login_required(request: Request, _exc: LoginRequired):
    return RedirectResponse("/login?next=" + quote(request.url.path), status_code=303)


@app.exception_handler(Forbidden)
async def forbidden(request: Request, _exc: Forbidden):
    db = SessionLocal()
    try:
        return render(request, db, "forbidden.html", status=403)
    finally:
        db.close()


@app.exception_handler(BadCsrf)
async def bad_csrf(request: Request, _exc: BadCsrf):
    db = SessionLocal()
    try:
        return render(
            request,
            db,
            "error.html",
            status=400,
            message="Форма устарела или пришла с другого сайта. Обновите страницу и отправьте ещё раз.",
        )
    finally:
        db.close()


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    if optional_user(request, db):
        return RedirectResponse("/", status_code=303)
    return render(request, db, "login.html", error="", next=safe_next(request.query_params.get("next", "/")))


@app.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await posted(request)
    username = form.get("username", "").strip()
    password = form.get("password", "")
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        return render(
            request,
            db,
            "login.html",
            status=401,
            error="Неверное имя или пароль.",
            next=safe_next(form.get("next", "/")),
        )
    request.session.clear()
    request.session["uid"] = user.id
    request.session["csrf"] = csrf_token({})
    csrf_token(request.session)
    return RedirectResponse(safe_next(form.get("next", "/")), status_code=303)


@app.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    await posted(request)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    records = load_records(settings.accounting_log)
    if user.role == "admin":
        sessions = active_sessions(records)
        recent = list(reversed(records[-8:]))
    else:
        # Имя берётся из сессии, не из query string.
        own = [item for item in records if item["user"] == user.username]
        sessions = active_sessions(own)
        recent = list(reversed(own[-8:]))
    return render(
        request,
        db,
        "dashboard.html",
        device_count=db.scalar(select(func.count()).select_from(Device)) or 0,
        user_count=db.scalar(select(func.count()).select_from(User)) or 0,
        sessions=sessions,
        recent=recent,
        log_path=settings.accounting_log,
    )


@app.get("/devices", response_class=HTMLResponse)
def devices_list(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    sort: str = "name",
    direction: str = "asc",
):
    require_admin(request, db)
    allowed = {
        "name": Device.name,
        "address": Device.address,
        "group": Device.group_name,
        "vendor": Device.vendor,
    }
    column, descending, sort, direction = sort_pair(sort, direction, allowed, "name")
    stmt = select(Device)
    if q.strip():
        pattern = like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Device.name.like(pattern, escape="\\"),
                Device.address.like(pattern, escape="\\"),
                Device.group_name.like(pattern, escape="\\"),
                Device.vendor.like(pattern, escape="\\"),
            )
        )
    stmt = stmt.order_by(column.desc() if descending else column.asc())
    return render(
        request,
        db,
        "devices.html",
        devices=list(db.scalars(stmt)),
        q=q,
        sort=sort,
        direction=direction,
    )


def _address_ok(value: str) -> bool:
    try:
        if "/" in value:
            ipaddress.ip_network(value, strict=False)
        else:
            ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _device_errors(form: dict[str, str], db: Session, current: Device | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    name = form.get("name", "").strip()
    address = form.get("address", "").strip()
    key = form.get("shared_key", "").strip()
    vendor = form.get("vendor", "").strip()
    group_name = form.get("group_name", "").strip()
    if not valid_username(name):
        errors["name"] = "Имя: буква, затем буквы, цифры, точка, _ или -, до 64 символов."
    elif db.scalar(select(Device).where(Device.name == name, Device.id != (current.id if current else -1))):
        errors["name"] = "Устройство с таким именем уже есть."
    if not address or not _address_ok(address):
        errors["address"] = "Нужен IPv4, IPv6 или префикс CIDR."
    if not key or len(key) > 256:
        errors["shared_key"] = "Ключ обязателен и не длиннее 256 символов."
    if vendor not in VENDORS:
        errors["vendor"] = "Выберите тип устройства из списка."
    if len(group_name) > 64:
        errors["group_name"] = "Группа не длиннее 64 символов."
    return errors


@app.get("/devices/new", response_class=HTMLResponse)
def device_new(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return render(request, db, "device_form.html", device=None, errors={}, form={})


@app.post("/devices/new")
async def device_create(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    form = await posted(request)
    errors = _device_errors(form, db, None)
    if errors:
        return render(request, db, "device_form.html", status=400, device=None, errors=errors, form=form)
    db.add(
        Device(
            name=form["name"].strip(),
            address=form["address"].strip(),
            shared_key=form["shared_key"].strip(),
            group_name=form.get("group_name", "").strip(),
            vendor=form["vendor"].strip(),
        )
    )
    db.commit()
    request.session["flash"] = "Устройство добавлено. Конфиг tac_plus-ng этой записью не меняется."
    return RedirectResponse("/devices", status_code=303)


@app.get("/devices/{device_id}/edit", response_class=HTMLResponse)
def device_edit(device_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    device = db.get(Device, device_id)
    if device is None:
        return render(request, db, "error.html", status=404, message="Устройство не найдено.")
    return render(request, db, "device_form.html", device=device, errors={}, form={})


@app.post("/devices/{device_id}/edit")
async def device_update(device_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    device = db.get(Device, device_id)
    if device is None:
        return render(request, db, "error.html", status=404, message="Устройство не найдено.")
    form = await posted(request)
    errors = _device_errors(form, db, device)
    if errors:
        return render(request, db, "device_form.html", status=400, device=device, errors=errors, form=form)
    device.name = form["name"].strip()
    device.address = form["address"].strip()
    device.shared_key = form["shared_key"].strip()
    device.group_name = form.get("group_name", "").strip()
    device.vendor = form["vendor"].strip()
    db.commit()
    request.session["flash"] = "Устройство сохранено."
    return RedirectResponse("/devices", status_code=303)


@app.post("/devices/{device_id}/delete")
async def device_delete(device_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    await posted(request)
    device = db.get(Device, device_id)
    if device is None:
        return render(request, db, "error.html", status=404, message="Устройство не найдено.")
    db.delete(device)
    db.commit()
    request.session["flash"] = "Устройство удалено из инвентаря."
    return RedirectResponse("/devices", status_code=303)


@app.get("/users", response_class=HTMLResponse)
def users_list(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    sort: str = "username",
    direction: str = "asc",
):
    require_admin(request, db)
    allowed = {"username": User.username, "role": User.role, "group": User.group_name}
    column, descending, sort, direction = sort_pair(sort, direction, allowed, "username")
    stmt = select(User)
    if q.strip():
        pattern = like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                User.username.like(pattern, escape="\\"),
                User.role.like(pattern, escape="\\"),
                User.group_name.like(pattern, escape="\\"),
            )
        )
    stmt = stmt.order_by(column.desc() if descending else column.asc())
    return render(request, db, "users.html", users=list(db.scalars(stmt)), q=q, sort=sort, direction=direction)


def _user_errors(form: dict[str, str], db: Session, current: User | None, actor: User) -> dict[str, str]:
    errors: dict[str, str] = {}
    username = form.get("username", "").strip()
    role = form.get("role", "").strip()
    password = form.get("password", "")
    group_name = form.get("group_name", "").strip()
    if not valid_username(username):
        errors["username"] = "Имя: буква, затем буквы, цифры, точка, _ или -, до 64 символов."
    elif db.scalar(select(User).where(User.username == username, User.id != (current.id if current else -1))):
        errors["username"] = "Такое имя уже занято."
    if role not in ROLES:
        errors["role"] = "Роль: admin или user."
    if current is None and len(password) < 8:
        errors["password"] = "Пароль не короче 8 символов."
    if current is not None and password and len(password) < 8:
        errors["password"] = "Новый пароль не короче 8 символов, либо оставьте поле пустым."
    if len(group_name) > 64:
        errors["group_name"] = "Группа не длиннее 64 символов."
    if current is not None and current.id == actor.id and role != "admin":
        errors["role"] = "Нельзя снять с себя роль admin."
    if current is not None and current.role == "admin" and role != "admin" and admin_count(db) <= 1:
        errors["role"] = "Это последний администратор."
    return errors


@app.get("/users/new", response_class=HTMLResponse)
def user_new(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return render(request, db, "user_form.html", account=None, errors={}, form={})


@app.post("/users/new")
async def user_create(request: Request, db: Session = Depends(get_db)):
    actor = require_admin(request, db)
    form = await posted(request)
    errors = _user_errors(form, db, None, actor)
    if errors:
        return render(request, db, "user_form.html", status=400, account=None, errors=errors, form=form)
    db.add(
        User(
            username=form["username"].strip(),
            password_hash=hash_password(form["password"]),
            role=form["role"].strip(),
            group_name=form.get("group_name", "").strip(),
        )
    )
    db.commit()
    request.session["flash"] = "Пользователь веб-интерфейса создан. В tac_plus-ng.cfg он сам не появится."
    return RedirectResponse("/users", status_code=303)


@app.get("/users/{user_id}/edit", response_class=HTMLResponse)
def user_edit(user_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    account = db.get(User, user_id)
    if account is None:
        return render(request, db, "error.html", status=404, message="Пользователь не найден.")
    return render(request, db, "user_form.html", account=account, errors={}, form={})


@app.post("/users/{user_id}/edit")
async def user_update(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = require_admin(request, db)
    account = db.get(User, user_id)
    if account is None:
        return render(request, db, "error.html", status=404, message="Пользователь не найден.")
    form = await posted(request)
    errors = _user_errors(form, db, account, actor)
    if errors:
        return render(request, db, "user_form.html", status=400, account=account, errors=errors, form=form)
    account.username = form["username"].strip()
    account.role = form["role"].strip()
    account.group_name = form.get("group_name", "").strip()
    if form.get("password"):
        account.password_hash = hash_password(form["password"])
    db.commit()
    request.session["flash"] = "Пользователь сохранён."
    return RedirectResponse("/users", status_code=303)


@app.post("/users/{user_id}/delete")
async def user_delete(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = require_admin(request, db)
    await posted(request)
    account = db.get(User, user_id)
    if account is None:
        return render(request, db, "error.html", status=404, message="Пользователь не найден.")
    if account.id == actor.id:
        return render(request, db, "error.html", status=400, message="Нельзя удалить самого себя.")
    if account.role == "admin" and admin_count(db) <= 1:
        return render(request, db, "error.html", status=400, message="Нельзя удалить последнего администратора.")
    db.delete(account)
    db.commit()
    request.session["flash"] = "Пользователь удалён."
    return RedirectResponse("/users", status_code=303)


def _scoped_username(actor: User) -> str | None:
    """None означает «все пользователи» и доступно только admin. Иначе — имя из сессии."""
    if actor.role == "admin":
        return None
    return actor.username


@app.get("/sessions", response_class=HTMLResponse)
def sessions_page(request: Request, db: Session = Depends(get_db)):
    actor = require_user(request, db)
    records = load_records(settings.accounting_log)
    username = _scoped_username(actor)
    if username is not None:
        records = [item for item in records if item["user"] == username]
    return render(
        request,
        db,
        "sessions.html",
        sessions=active_sessions(records),
        refresh=10,
        log_path=settings.accounting_log,
    )


@app.get("/accounting", response_class=HTMLResponse)
def accounting_page(
    request: Request,
    db: Session = Depends(get_db),
    nas: str = "",
    text: str = "",
    since: str = "",
    until: str = "",
    page: int = 1,
):
    actor = require_user(request, db)
    forced = _scoped_username(actor)
    # Параметр user из строки запроса для роли user не читается.
    query_user = request.query_params.get("user", "").strip()
    username = forced if forced is not None else (query_user or None)
    rows = filter_records(
        load_records(settings.accounting_log),
        username=username,
        nas=nas,
        text=text,
        since=since,
        until=until,
    )
    if page < 1:
        page = 1
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start : start + PAGE_SIZE]
    pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    return render(
        request,
        db,
        "accounting.html",
        rows=page_rows,
        total=len(rows),
        page=page,
        pages=pages,
        nas=nas,
        text=text,
        since=since,
        until=until,
        query_user="" if forced is not None else query_user,
        log_path=settings.accounting_log,
    )


@app.get("/account/password", response_class=HTMLResponse)
def password_form(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    return render(request, db, "password.html", error="")


@app.post("/account/password")
async def password_change(request: Request, db: Session = Depends(get_db)):
    actor = require_user(request, db)
    form = await posted(request)
    current = form.get("current_password", "")
    new = form.get("new_password", "")
    again = form.get("new_password_again", "")
    fresh = db.get(User, actor.id)
    if fresh is None or not verify_password(current, fresh.password_hash):
        return render(request, db, "password.html", status=400, error="Текущий пароль не подошёл.")
    if len(new) < 8:
        return render(request, db, "password.html", status=400, error="Новый пароль не короче 8 символов.")
    if new != again:
        return render(request, db, "password.html", status=400, error="Повтор пароля не совпал.")
    fresh.password_hash = hash_password(new)
    db.commit()
    request.session["flash"] = "Пароль изменён."
    return RedirectResponse("/", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return render(
        request,
        db,
        "settings.html",
        accounting_log=settings.accounting_log,
        database_url=settings.database_url,
        cookie_secure=settings.session_cookie_secure,
    )
