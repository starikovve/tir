"""Разбор accounting-журнала tac_plus-ng.

Формат строки (руководство демона): поля через табуляцию
время, адрес NAS, имя, порт, адрес клиента, тип (start/stop/update),
затем пары атрибут=значение. task_id есть почти всегда.
"""

from pathlib import Path

MAX_BYTES = 8_000_000


def _read_tail(path: Path) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > MAX_BYTES:
            handle.seek(size - MAX_BYTES)
            handle.readline()
        raw = handle.read()
    return raw.decode("utf-8", errors="replace")


def log_files(root: str) -> list[Path]:
    """Только путь из настроек. Пользовательский ввод сюда не подмешивается."""
    path = Path(root)
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    return sorted(item for item in path.rglob("*.log") if item.is_file())


def parse_line(line: str) -> dict | None:
    parts = [item.strip() for item in line.rstrip("\n").split("\t")]
    if len(parts) < 6 or not parts[0] or not parts[2]:
        return None
    attrs: dict[str, str] = {}
    cmd_args: list[str] = []
    for item in parts[6:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key == "cmd-arg":
            cmd_args.append(value)
        else:
            attrs.setdefault(key, value)
    command = attrs.get("cmd", "")
    if command and cmd_args:
        command = command + " " + " ".join(cmd_args)
    elif not command and cmd_args:
        command = " ".join(cmd_args)
    return {
        "ts": parts[0],
        "nas": parts[1],
        "user": parts[2],
        "port": parts[3],
        "nac": parts[4],
        "kind": parts[5].lower(),
        "task_id": attrs.get("task_id", ""),
        "priv": attrs.get("priv-lvl", attrs.get("priv_level", "")),
        "command": command,
        "service": attrs.get("service", ""),
    }


def load_records(root: str) -> list[dict]:
    records: list[dict] = []
    try:
        files = log_files(root)
    except OSError:
        return []
    for path in files:
        try:
            text = _read_tail(path)
        except OSError:
            continue
        for line in text.splitlines():
            parsed = parse_line(line)
            if parsed:
                records.append(parsed)
    records.sort(key=lambda item: item["ts"])
    return records


def active_sessions(records: list[dict]) -> list[dict]:
    """Открытые сессии: start без последующего stop самой сессии.

    Командный учёт NAS тоже шлёт как stop, но с текстом команды (cmd / cmd-arg).
    Такой stop сессию не закрывает: иначе первая же команда убирает её из списка.
    Закрывает только stop без команды. Если task_id пустой, пара ищется по порту.
    """
    open_sessions: dict[tuple[str, str, str], dict] = {}
    for record in records:
        marker = record["task_id"] or record["port"]
        key = (record["nas"], record["user"], marker)
        if record["kind"] == "start":
            open_sessions[key] = record
        elif record["kind"] == "stop" and not record["command"]:
            open_sessions.pop(key, None)
    sessions = list(open_sessions.values())
    sessions.sort(key=lambda item: item["ts"], reverse=True)
    return sessions


def filter_records(
    records: list[dict],
    *,
    username: str | None,
    nas: str,
    text: str,
    since: str,
    until: str,
) -> list[dict]:
    nas_q = nas.strip().lower()
    text_q = text.strip().lower()
    since_key = _bound(since, end=False)
    until_key = _bound(until, end=True)
    chosen: list[dict] = []
    for record in records:
        if username is not None and record["user"] != username:
            continue
        if nas_q and nas_q not in record["nas"].lower():
            continue
        if text_q and text_q not in record["command"].lower() and text_q not in record["service"].lower():
            continue
        stamp = record["ts"][:19]
        if since_key and stamp < since_key:
            continue
        if until_key and stamp > until_key:
            continue
        chosen.append(record)
    chosen.sort(key=lambda item: item["ts"], reverse=True)
    return chosen


def _bound(value: str, *, end: bool) -> str:
    raw = value.strip().replace("T", " ")
    if not raw:
        return ""
    if len(raw) == 10:
        return raw + (" 23:59:59" if end else " 00:00:00")
    if len(raw) == 16:
        return raw + (":59" if end else ":00")
    return raw[:19]
