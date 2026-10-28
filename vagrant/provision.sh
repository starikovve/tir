#!/bin/bash
# Идемпотентная подготовка ВМ: tac_plus-ng, веб-интерфейс, nginx.
# Повторный запуск не пересоздаёт .env, самоподписанный сертификат
# и уже собранный бинарник. Код интерфейса, конфиг демона и юниты
# копируются заново, службы перезапускаются.
# Файлы берутся с /vagrant-src и кладутся на диск ВМ: права vboxsf не используем.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG=C.UTF-8
export PATH="/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"

SRC=/vagrant-src

# Пароль первого администратора печатается в самом конце, даже если
# проверка TACACS+ ниже завершится с ошибкой. В репозиторий он не пишется.
print_admin_password() {
  if [[ ! -f /opt/tacacs-ui/.env ]]; then
    return 0
  fi
  local admin_user admin_pass
  admin_user="$(sed -n 's/^BOOTSTRAP_ADMIN_USER=//p' /opt/tacacs-ui/.env)"
  admin_pass="$(sed -n 's/^BOOTSTRAP_ADMIN_PASSWORD=//p' /opt/tacacs-ui/.env)"
  if [[ -z "${admin_pass}" ]]; then
    return 0
  fi
  cat <<EOF

============================================================
Веб-интерфейс: https://192.168.56.10/
Логин: ${admin_user}
Пароль: ${admin_pass}

Пароль лежит только в /opt/tacacs-ui/.env на этой ВМ.
В репозиторий его класть нельзя. Браузер предупредит
о самоподписанном сертификате — для лаборатории это нормально.
============================================================
EOF
}
copy_root=""
on_exit() {
  if [[ -n "${copy_root}" && -d "${copy_root}" ]]; then
    rm -rf "${copy_root}"
  fi
  print_admin_password
}
trap on_exit EXIT

if [[ ! -f "${SRC}/TACACS+/webui/app/main.py" || ! -f "${SRC}/vagrant/server/tac_plus-ng.cfg" ]]; then
  echo "Не вижу ${SRC}/TACACS+ или ${SRC}/vagrant. Общая папка репозитория не смонтировалась." >&2
  exit 1
fi

apt-get update
apt-get install -y \
  build-essential git libpcre2-dev perl ca-certificates \
  python3 python3-venv python3-pip \
  nginx openssl sqlite3 ufw iproute2

# Учётка веб-интерфейса. Группа adm читает журналы демона (setgid на каталоге).
if ! id tacacsui >/dev/null 2>&1; then
  useradd --system --home /opt/tacacs-ui --shell /usr/sbin/nologin tacacsui
fi
usermod -aG adm tacacsui

install -d -o tacacsui -g tacacsui -m 0755 /opt/tacacs-ui
install -m 0755 "${SRC}/vagrant/scripts/tacacs-logdirs" /usr/local/sbin/tacacs-logdirs
sed -i 's/\r$//' /usr/local/sbin/tacacs-logdirs
/usr/local/sbin/tacacs-logdirs

# Сборка демона. Повторный provision её пропускает, пока бинарник на месте.
if [[ ! -x /usr/local/sbin/tac_plus-ng ]]; then
  if [[ ! -d /usr/local/src/event-driven-servers/.git ]]; then
    rm -rf /usr/local/src/event-driven-servers
    git clone --depth 1 https://github.com/MarcJHuber/event-driven-servers.git \
      /usr/local/src/event-driven-servers
  fi
  (
    cd /usr/local/src/event-driven-servers
    ./configure --minimum tac_plus-ng
    make -j"$(nproc)"
    make install
  )
fi

install -d -m 0755 /etc/tac_plus-ng
sed 's/\r$//' "${SRC}/vagrant/server/tac_plus-ng.cfg" > /etc/tac_plus-ng/tac_plus-ng.cfg
chmod 644 /etc/tac_plus-ng/tac_plus-ng.cfg
/usr/local/sbin/tac_plus-ng -P /etc/tac_plus-ng/tac_plus-ng.cfg

# Код веб-интерфейса. .env, база и venv с диска ВМ не затираются.
copy_root="$(mktemp -d)"
tar -C "${SRC}/TACACS+/webui" \
  --exclude .venv \
  --exclude .env \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.sqlite' \
  --exclude '*.sqlite3' \
  -cf - . | tar -C "${copy_root}" -xf -
find "${copy_root}" -type f -print0 | xargs -0 -r sed -i 's/\r$//'
find "${copy_root}" -type d -exec chmod 0755 {} +
find "${copy_root}" -type f -exec chmod 0644 {} +
cp -a "${copy_root}"/. /opt/tacacs-ui/
rm -rf "${copy_root}"
copy_root=""

if [[ ! -x /opt/tacacs-ui/.venv/bin/pip ]]; then
  python3 -m venv /opt/tacacs-ui/.venv
fi
/opt/tacacs-ui/.venv/bin/pip install --upgrade pip
/opt/tacacs-ui/.venv/bin/pip install -r /opt/tacacs-ui/requirements.txt

# Секреты только здесь. Повторный запуск уже созданный файл не меняет,
# иначе пароль в выводе перестанет совпадать с базой.
if [[ ! -s /opt/tacacs-ui/.env ]]; then
  secret="$(openssl rand -hex 32)"
  password="$(openssl rand -hex 12)"
  if [[ -f /opt/tacacs-ui/tacacs-ui.sqlite ]]; then
    echo "База уже есть, а .env нет. Новый пароль к существующим пользователям не применится." >&2
  fi
  umask 077
  cat > /opt/tacacs-ui/.env <<EOF
APP_SECRET_KEY=${secret}
DATABASE_URL=sqlite:////opt/tacacs-ui/tacacs-ui.sqlite
ACCOUNTING_LOG=/var/log/tac_plus-ng/acct
SESSION_COOKIE_SECURE=true
BOOTSTRAP_ADMIN_USER=admin
BOOTSTRAP_ADMIN_PASSWORD=${password}
LOGIN_RATE_LIMIT=5/minute
EOF
  umask 022
fi
chown -R tacacsui:tacacsui /opt/tacacs-ui
chown tacacsui:tacacsui /opt/tacacs-ui/.env
chmod 640 /opt/tacacs-ui/.env

install -d -m 0755 /etc/nginx/ssl
if [[ ! -f /etc/nginx/ssl/tacacs.crt || ! -f /etc/nginx/ssl/tacacs.key ]]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout /etc/nginx/ssl/tacacs.key \
    -out /etc/nginx/ssl/tacacs.crt \
    -subj "/CN=192.168.56.10" \
    -addext "subjectAltName=IP:192.168.56.10,DNS:tacacs.lab,DNS:tacacs"
fi
chown root:root /etc/nginx/ssl/tacacs.key /etc/nginx/ssl/tacacs.crt
chmod 640 /etc/nginx/ssl/tacacs.key
chmod 644 /etc/nginx/ssl/tacacs.crt

cat > /etc/nginx/sites-available/tacacs-ui <<'EOF'
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
        # Адрес клиента с сокета nginx, без префикса из браузера.
        # Веб-интерфейс считает по нему лимит входа.
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF
ln -sfn /etc/nginx/sites-available/tacacs-ui /etc/nginx/sites-enabled/tacacs-ui
rm -f /etc/nginx/sites-enabled/default
nginx -t

cat > /etc/systemd/system/tac_plus-ng.service <<'EOF'
[Unit]
Description=tac_plus-ng
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/usr/local/sbin/tacacs-logdirs
ExecStart=/usr/local/sbin/tac_plus-ng -f /etc/tac_plus-ng/tac_plus-ng.cfg
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/tacacs-ui.service <<'EOF'
[Unit]
Description=TACACS lab web UI
After=network-online.target tac_plus-ng.service

[Service]
Type=simple
User=tacacsui
Group=tacacsui
# Журналы демона читает группа adm. Без неё страница сессий пустая.
SupplementaryGroups=adm
WorkingDirectory=/opt/tacacs-ui
EnvironmentFile=/opt/tacacs-ui/.env
ExecStart=/opt/tacacs-ui/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

install -m 0755 "${SRC}/vagrant/scripts/tacacs-demo-session" /usr/local/sbin/tacacs-demo-session
sed -i 's/\r$//' /usr/local/sbin/tacacs-demo-session

install -d -m 0755 /opt/tacacs-client /usr/local/share/tacacs
sed 's/\r$//' "${SRC}/vagrant/client/check_tacacs.py" > /opt/tacacs-client/check_tacacs.py
chmod 644 /opt/tacacs-client/check_tacacs.py
sed 's/\r$//' "${SRC}/vagrant/nas/cisco-ios.cfg" > /usr/local/share/tacacs/cisco-ios.cfg
chmod 644 /usr/local/share/tacacs/cisco-ios.cfg
if [[ ! -x /opt/tacacs-client/.venv/bin/pip ]]; then
  python3 -m venv /opt/tacacs-client/.venv
fi
/opt/tacacs-client/.venv/bin/pip install 'tacacs_plus>=2.6,<3'
cat > /usr/local/bin/check-tacacs <<'EOF'
#!/bin/bash
exec /opt/tacacs-client/.venv/bin/python /opt/tacacs-client/check_tacacs.py "$@"
EOF
chmod 755 /usr/local/bin/check-tacacs

# Сначала SSH, потом enable. Иначе следующий vagrant ssh не попадёт в ВМ.
ufw allow OpenSSH
ufw allow 49/tcp
ufw allow 443/tcp
ufw --force enable

systemctl daemon-reload
systemctl enable tac_plus-ng.service tacacs-ui.service nginx
systemctl restart tac_plus-ng.service
systemctl restart tacacs-ui.service
systemctl restart nginx

ready=0
for _ in $(seq 1 40); do
  if ss -ltn 'sport = :49' | grep -q LISTEN \
    && ss -ltn 'sport = :8080' | grep -q LISTEN \
    && ss -ltn 'sport = :443' | grep -q LISTEN; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "${ready}" -ne 1 ]]; then
  echo "Порты 49, 8080 или 443 не открылись." >&2
  systemctl status tac_plus-ng tacacs-ui nginx --no-pager || true
  journalctl -u tac_plus-ng -u tacacs-ui -n 80 --no-pager || true
  exit 1
fi

/usr/local/bin/check-tacacs
