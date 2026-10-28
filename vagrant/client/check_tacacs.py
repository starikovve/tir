#!/usr/bin/env python3
"""Проверка TACACS+ с самой ВМ.

Клиент ходит на 127.0.0.1:49. Источник такого TCP — тоже 127.0.0.1,
поэтому ключ обязан совпасть с device vagrant-local в tac_plus-ng.cfg.
Пользователь alice и пароль — лабораторные, они же в конфиге демона.
"""

import socket
import sys

from tacacs_plus.client import TACACSClient
from tacacs_plus.flags import TAC_PLUS_AUTHEN_TYPE_ASCII, TAC_PLUS_AUTHEN_TYPE_PAP

HOST = "127.0.0.1"
PORT = 49
KEY = "lab-vagrant-key"
USER = "alice"
PASSWORD = "alice-lab-password"


def try_auth(authen_type, password):
    """Один запрос. Таймаут и обрыв сокета не роняют весь скрипт."""
    client = TACACSClient(HOST, PORT, KEY, timeout=5)
    try:
        reply = client.authenticate(USER, password, authen_type=authen_type)
    except (socket.timeout, OSError) as exc:
        return False, str(exc)
    return bool(reply.valid), reply.human_status


def main() -> int:
    chosen = None
    for authen_type, title in (
        (TAC_PLUS_AUTHEN_TYPE_ASCII, "ASCII"),
        (TAC_PLUS_AUTHEN_TYPE_PAP, "PAP"),
    ):
        ok, status = try_auth(authen_type, PASSWORD)
        print(f"{title}, верный пароль: {status}")
        if ok:
            chosen = authen_type
            break
    if chosen is None:
        print("Сервер не принял пароль alice. Проверьте ключ device и что порт 49 слушается.")
        return 1

    bad_ok, status = try_auth(chosen, "wrong-password")
    print(f"Неверный пароль: {status}")
    if bad_ok:
        print("Неверный пароль неожиданно прошёл.")
        return 1

    print("Проверка TACACS+ прошла: alice пускает, чужой пароль — нет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
