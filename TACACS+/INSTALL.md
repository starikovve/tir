# Установка tac_plus-ng и веб-интерфейса

Учебный стенд на Ubuntu или Debian: демон **tac_plus-ng** (Event-Driven Servers, Marc Huber) и отдельный веб-интерфейс на FastAPI. Веб-интерфейс не входит в поставку демона. В этой версии он **не генерирует** `tac_plus-ng.cfg` и **не перезагружает** демон. Демон читает свой файл конфигурации. Веб-интерфейс хранит в sqlite инвентарь NAS и свои учётные записи и показывает accounting-журнал, который пишет демон.

Пароли веб-входа хранятся как argon2id (соль на каждый пароль, параметры по умолчанию `argon2-cffi`). Пароли в примере `server/tac_plus-ng.cfg` — отдельные лабораторные значения для самого TACACS+.

Подробное описание страниц — в [WEB_UI.md](WEB_UI.md).

## 1. Пакеты для сборки

```bash
sudo apt-get update
sudo apt-get install -y build-essential git libpcre2-dev perl \
  python3 python3-venv python3-pip nginx openssl sqlite3
```

`configure` у event-driven-servers — это Perl-скрипт, не autoconf. PCRE2 для tac_plus-ng обязателен. `--minimum` отключает необязательные библиотеки (TLS, LDAP, c-ares), но без заголовков PCRE2 сборка остановится.

## 2. Сборка tac_plus-ng

```bash
sudo git clone --depth 1 https://github.com/MarcJHuber/event-driven-servers.git \
  /usr/local/src/event-driven-servers
cd /usr/local/src/event-driven-servers
sudo ./configure --minimum tac_plus-ng
sudo make -j"$(nproc)"
sudo make install
```

Бинарник оказывается в `/usr/local/sbin/tac_plus-ng`. Проверка разбора файла без запуска демона:

```bash
sudo tac_plus-ng -P /путь/к/tac_plus-ng.cfg
```

`-P` только проверяет синтаксис и завершается. Флаг `-f` держит процесс на переднем плане — так его и запускает systemd ниже. В примере репозитория стоит `background = yes`; для systemd в копии конфига эту строку меняют на `background = no`.

## 3. Конфиг, каталоги журналов, firewall

```bash
sudo install -d -m 0755 /etc/tac_plus-ng
sudo cp server/tac_plus-ng.cfg /etc/tac_plus-ng/tac_plus-ng.cfg
sudo sed -i 's/background = yes/background = no/' /etc/tac_plus-ng/tac_plus-ng.cfg

sudo install -d -m 2750 -o root -g adm \
  /var/log/tac_plus-ng \
  /var/log/tac_plus-ng/authc \
  /var/log/tac_plus-ng/authz \
  /var/log/tac_plus-ng/acct
# Каталог текущего месяца. Пример пишет acct/%Y/%m/%d.log.
sudo install -d -m 2750 -o root -g adm \
  /var/log/tac_plus-ng/authc/"$(date +%Y/%m)" \
  /var/log/tac_plus-ng/authz/"$(date +%Y/%m)" \
  /var/log/tac_plus-ng/acct/"$(date +%Y/%m)"
```

Каталоги принадлежат группе `adm`. Бит setgid (`2750`) передаёт эту группу новым файлам, а `umask = 0640` в конфиге демона оставляет группе чтение. Пользователя веб-интерфейса (ниже это `tacacsui`) добавляют в группу `adm`, иначе он не откроет accounting. Каталог дня демон сам не создаёт: в следующем месяце команду `install -d` для `%Y/%m` повторяют до старта, либо вешают её на `ExecStartPre` юнита.

Демон слушает TCP/49 на всех адресах (`listen { address = 0.0.0.0 port = 49 }` в примере). Открывайте порт только оттуда, откуда стоят NAS:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 49/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

`ufw enable` без разрешённого SSH отрежет текущую сессию. Сначала `allow OpenSSH`.

Юнит systemd `/etc/systemd/system/tac_plus-ng.service`:

```ini
[Unit]
Description=tac_plus-ng
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/sbin/tac_plus-ng -f /etc/tac_plus-ng/tac_plus-ng.cfg
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

```bash
sudo tac_plus-ng -P /etc/tac_plus-ng/tac_plus-ng.cfg
sudo systemctl daemon-reload
sudo systemctl enable --now tac_plus-ng.service
```

## 4. Веб-интерфейс

Каталог приложения — `webui/`:

| Путь | Зачем |
| --- | --- |
| `app/main.py` | Страницы FastAPI |
| `app/models.py` | Таблицы `users` и `devices` |
| `app/auth.py` | argon2id, CSRF, проверка роли |
| `app/acct.py` | Разбор accounting-журнала и открытые сессии |
| `app/settings.py` | Чтение `.env` |
| `app/templates/` | HTML-страницы |
| `requirements.txt` | FastAPI, uvicorn, Jinja2, SQLAlchemy, argon2-cffi, slowapi |
| `.env.example` | Образец переменных, без секретов |

Страницы — обычный HTML через Jinja2. Формы, cookie-сессия и sqlite (SQLAlchemy) живут в одном процессе. Отдельный фронтенд этому стенду не нужен. Пароли веб-входа хеширует argon2id. Лимит попыток входа считает slowapi в памяти процесса.

```bash
sudo useradd --system --home /opt/tacacs-ui --shell /usr/sbin/nologin tacacsui || true
sudo usermod -aG adm tacacsui
sudo mkdir -p /opt/tacacs-ui
sudo cp -a webui/. /opt/tacacs-ui/
sudo python3 -m venv /opt/tacacs-ui/.venv
sudo /opt/tacacs-ui/.venv/bin/pip install -r /opt/tacacs-ui/requirements.txt
sudo chown -R tacacsui:tacacsui /opt/tacacs-ui
```

Файл `/opt/tacacs-ui/.env` (права `640`, владелец `tacacsui`). Секреты только здесь, в репозиторий их не кладут. После записи файла: `sudo chown tacacsui:tacacsui /opt/tacacs-ui/.env && sudo chmod 640 /opt/tacacs-ui/.env`. Строки файла:

```bash
APP_SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=sqlite:////opt/tacacs-ui/tacacs-ui.sqlite
ACCOUNTING_LOG=/var/log/tac_plus-ng/acct
SESSION_COOKIE_SECURE=true
BOOTSTRAP_ADMIN_USER=admin
BOOTSTRAP_ADMIN_PASSWORD=$(openssl rand -hex 12)
LOGIN_RATE_LIMIT=5/minute
```

`SESSION_COOKIE_SECURE=true` ставят за nginx с HTTPS. Если открываете сам uvicorn по HTTP, поставьте `false`: иначе браузер не сохранит cookie и вход не удержится.

Cookie сессии называется `tacacs_ui`. Приложение всегда ставит **HttpOnly** (из JavaScript её не прочитать) и **SameSite=Lax**, срок — 8 часов. Флаг **Secure** включается только переменной `SESSION_COOKIE_SECURE`. Секрет подписи — `APP_SECRET_KEY`, в коде его нет. Пустой или короче 16 символов ключ процесс не запускает.

`LOGIN_RATE_LIMIT` ограничивает `POST /login` с одного адреса. Формат: `число/second`, `число/minute`, `число/hour` или `число/day`. По умолчанию `5/minute`. Счётчик в памяти одного процесса: юнит ниже `--workers` не задаёт. За nginx адрес берётся из заголовка `X-Real-IP` (его выставляет nginx из `$remote_addr`), а не из клиентского `X-Forwarded-For`.

`BOOTSTRAP_ADMIN_*` создаёт первого администратора **только если таблица пользователей пуста**. Повторный запуск пароль не меняет.

Юнит `/etc/systemd/system/tacacs-ui.service`:

```ini
[Unit]
Description=TACACS lab web UI
After=network-online.target tac_plus-ng.service

[Service]
Type=simple
User=tacacsui
Group=tacacsui
WorkingDirectory=/opt/tacacs-ui
EnvironmentFile=/opt/tacacs-ui/.env
ExecStart=/opt/tacacs-ui/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Приложение слушает только localhost. Снаружи его публикует nginx.

Роли:

- `admin` — устройства, пользователи, параметры, все сессии и весь журнал.
- `user` — свои сессии и свои строки журнала (фильтр по имени из сессии, параметр `?user=` игнорируется) и смена своего пароля. Чужие разделы отвечают 403.

## 5. nginx и самоподписанный сертификат

```bash
sudo install -d -m 0755 /etc/nginx/ssl
sudo openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout /etc/nginx/ssl/tacacs.key \
  -out /etc/nginx/ssl/tacacs.crt \
  -subj "/CN=tacacs.lab" \
  -addext "subjectAltName=DNS:tacacs.lab"
sudo chmod 640 /etc/nginx/ssl/tacacs.key
```

`/etc/nginx/sites-available/tacacs-ui`:

```nginx
server {
    listen 80;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;
    ssl_certificate /etc/nginx/ssl/tacacs.crt;
    ssl_certificate_key /etc/nginx/ssl/tacacs.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        # Свой адрес клиента, без префикса, который прислал браузер.
        # По нему веб-интерфейс считает лимит входа (заголовок X-Real-IP).
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/tacacs-ui /etc/nginx/sites-enabled/tacacs-ui
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Браузер предупредит о самоподписанном сертификате. Для лаборатории это ожидаемо.

## 6. Порядок запуска

1. Каталоги журналов и копия `/etc/tac_plus-ng/tac_plus-ng.cfg` (`background = no`).
2. `tac_plus-ng -P`, затем `systemctl enable --now tac_plus-ng`.
3. Пользователь `tacacsui`, venv, `/opt/tacacs-ui/.env`, `systemctl enable --now tacacs-ui`.
4. nginx. Пока uvicorn не слушает `127.0.0.1:8080`, nginx отвечает 502.

Проверка, что веб-процесс поднялся:

```bash
systemctl status tac_plus-ng tacacs-ui nginx
ss -ltnp | grep -E ':49|:443|:8080'
```

## 7. Проверка

```bash
ss -ltnp | grep ':49'
sudo journalctl -u tac_plus-ng -u tacacs-ui -n 50 --no-pager
```

Вход в браузер: `https://адрес-сервера/`, имя и пароль из `BOOTSTRAP_ADMIN_*`. После входа виден обзор.

Сессии появляются из журнала демона, а не из таблицы устройств. Строка start (поля через табуляцию, как в [accounting.md](accounting.md)):

```bash
printf '%s\n' $'2026-10-28 14:01:02 +0000\t192.0.2.21\talice\ttty1\t203.0.113.10\tstart\ttask_id=42\tservice=shell' \
  | sudo tee -a /var/log/tac_plus-ng/acct/"$(date +%Y/%m/%d)".log
sudo chgrp tacacsui /var/log/tac_plus-ng/acct/"$(date +%Y/%m/%d)".log
```

Обновите страницу «Сессии»: строка alice должна быть в списке, пока нет парного `stop` с тем же `task_id`.

Проверка логина TACACS+ с Cisco — команда из [devices/cisco-ios.md](devices/cisco-ios.md):

```ios
test aaa group AAA-TACACS alice alice-lab-password new-code
```

Отдельной утилиты `tactest` в поставке tac_plus-ng нет. С хоста, с которого разрешён адрес в блоке `device`, подойдёт клиент PyPI `tacacs_plus`:

```bash
python3 -m venv /tmp/tacacs-client
/tmp/tacacs-client/bin/pip install tacacs_plus
/tmp/tacacs-client/bin/tacacs_client -u alice -H 127.0.0.1 -k lab-default-key \
  authenticate -p alice-lab-password
```

Ключ должен совпасть с `device`, в чей адрес попал **источник** TCP-сессии. В примере репозитория это сеть `192.0.2.0/24` (ключ `lab-default-key`) и более узкие адреса со своими ключами. Чужой адрес демон отбрасывает ещё до проверки пароля. `127.0.0.1` в пример сам по себе не входит: для проверки с localhost в конфиг добавляют отдельный `device` с этим адресом и тем же ключом, который передаёте в `-k`.

## 8. Контрольный список

- [ ] `tac_plus-ng -P /etc/tac_plus-ng/tac_plus-ng.cfg` завершается без ошибки, `systemctl status tac_plus-ng` — active, `ss` показывает TCP/49.
- [ ] Каталоги `/var/log/tac_plus-ng/{authc,authz,acct}/ГГГГ/ММ` есть, `tacacsui` входит в группу `adm` (`id tacacsui`).
- [ ] `/opt/tacacs-ui/.env` на месте, режим `640`, в репозитории этого файла нет. `APP_SECRET_KEY` и `BOOTSTRAP_ADMIN_PASSWORD` заданы здесь, не в коде.
- [ ] `systemctl status tacacs-ui` — active. После первого запуска появился файл sqlite из `DATABASE_URL`.
- [ ] nginx слушает 443, `nginx -t` чистый. Браузер открывает `https://адрес/` и предупреждает о самоподписанном сертификате.
- [ ] Вход администратора открывает обзор. В ответе `Set-Cookie` у `tacacs_ui` есть `HttpOnly` и `SameSite=Lax`, а при `SESSION_COOKIE_SECURE=true` ещё и `Secure`.
- [ ] Лишняя попытка `POST /login` сверх `LOGIN_RATE_LIMIT` отвечает 429 и текстом «Слишком много попыток входа».
- [ ] Роль `user` на `/devices`, `/users` и `/settings` получает 403. В журнале и сессиях видны только строки с её именем, параметр `?user=` чужое имя не подставляет.
- [ ] Устройство и пользователь создаются, правятся и удаляются. Последнего admin и самого себя удалить нельзя.
- [ ] Строка `start` в accounting появляется на странице «Сессии». `stop` с `cmd` эту сессию не убирает, `stop` без команды — убирает.
