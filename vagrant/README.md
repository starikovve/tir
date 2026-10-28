# Стенд TACACS+ в VirtualBox

Одна команда `vagrant up` на Windows поднимает Ubuntu 24.04. Внутри сами ставятся tac_plus-ng, веб-интерфейс (FastAPI, sqlite) и nginx с самоподписанным сертификатом на `https://192.168.56.10/`. Ansible нет: гость готовит shell-скрипт `provision.sh`.

Пароль первого администратора скрипт печатает в конце провижининга. В репозиторий он не попадает: он только в `/opt/tacacs-ui/.env` на диске ВМ. Каталог `.vagrant/` тоже не коммитят — туда Vagrant пишет журнал, и в нём этот пароль есть.

## Что поставить на Windows

Нужны VirtualBox и Vagrant, и сеть наружу: первый запуск скачивает бокс `bento/ubuntu-24.04`, а ВМ по NAT ставит пакеты и клонирует исходники демона.

PowerShell, от администратора, если winget этого просит:

```powershell
winget install --id Oracle.VirtualBox -e --accept-package-agreements --accept-source-agreements
winget install --id Hashicorp.Vagrant -e --accept-package-agreements --accept-source-agreements
```

Тот же набор через Chocolatey, если он уже установлен:

```powershell
choco install virtualbox vagrant -y
```

Либо установщики с сайтов VirtualBox и Vagrant. После установки закройте PowerShell и откройте новое окно, чтобы подхватился `PATH`.

Проверка:

```powershell
VBoxManage --version
vagrant --version
```

## Запуск

Подставьте путь к клону репозитория. Команды Vagrant запускают из каталога `vagrant`, рядом с `Vagrantfile`.

```powershell
Set-Location C:\src\tir\vagrant
vagrant up
```

Дальше Vagrant сам создаёт ВМ, прописывает адрес `192.168.56.10` и запускает `provision.sh`. Повторный `vagrant up`, когда машина уже есть, просто её включает. Пока в конце вывода не появится блок с логином и паролем, стенд не готов: идёт скачивание бокса и сборка tac_plus-ng.

Скрипт идемпотентный. Его можно прогнать ещё раз, не уничтожая ВМ. Уже созданные `.env`, сертификат и бинарник демона он не перевыпускает.

```powershell
vagrant provision
```

Оболочка гостя:

```powershell
vagrant ssh
```

Выключить и удалить ВМ (пароль администратора уходит вместе с диском):

```powershell
vagrant destroy -f
```

## Войти в веб-интерфейс

Откройте в браузере:

```powershell
Start-Process https://192.168.56.10/
```

Сертификат самоподписанный, имя в нём — `192.168.56.10`. Предупреждение ожидаемо.

- Chrome и Edge: «Дополнительно», затем «Перейти на сайт 192.168.56.10 (небезопасно)».
- Firefox: «Дополнительно» → «Принять риск и продолжить».

На странице «Вход в веб-интерфейс» имя `admin`, пароль — из конца вывода `vagrant up`. Это учётка веб-интерфейса, не пользователь TACACS+.

Если окно с паролем уже закрыто:

```powershell
vagrant ssh -c 'sudo grep ^BOOTSTRAP_ADMIN_PASSWORD= /opt/tacacs-ui/.env'
```

После входа открывается «Обзор». Справа в шапке имя и подпись «администратор».

## Добавить устройство

Пункт «Устройства» → «Добавить устройство».

| Поле | Пример |
| --- | --- |
| Имя | `core-r1` |
| Адрес или префикс | `192.168.56.1` |
| Ключ TACACS+ | `lab-vagrant-key` |
| Группа | `lab` |
| Тип | `cisco` |

«Сохранить» возвращает к списку. Строка лежит в sqlite веб-интерфейса. Демон её не читает: его устройства уже описаны в `/etc/tac_plus-ng/tac_plus-ng.cfg` (копия `vagrant/server/tac_plus-ng.cfg`). Для сети `192.168.56.0/24` и для `127.0.0.1` там ключ `lab-vagrant-key`.

## Посмотреть сессии

Пункт «Сессии». Пока NAS ничего не присылал, таблица пустая. Демонстрационную открытую сессию alice дописывает скрипт в госте:

```powershell
vagrant ssh -c 'sudo /usr/local/sbin/tacacs-demo-session'
```

Обновите `https://192.168.56.10/sessions` (страница и сама обновляется каждые 10 секунд). Строка alice остаётся, пока в журнале нет `stop` без команды с тем же `task_id`. «Журнал» показывает и эту строку, и более поздние.

## Проверка клиента TACACS+

С самой ВМ клиент ходит на `127.0.0.1:49` ключом `lab-vagrant-key` и логином `alice` / `alice-lab-password`. Верный пароль должен пройти, заведомо неверный — нет. `vagrant up` запускает эту проверку сам. Повторить:

```powershell
vagrant ssh -c 'sudo /usr/local/bin/check-tacacs'
```

Фрагмент для Cisco IOS / IOS-XE лежит в `nas/cisco-ios.cfg` и внутри ВМ в `/usr/local/share/tacacs/cisco-ios.cfg`. Сервер в нём — `192.168.56.10`, ключ — `lab-vagrant-key`. Адрес источника на маршрутизаторе должен попадать в `192.168.56.0/24`, иначе демон отбросит пакет до пароля. С коробки, не закрывая текущий вход:

```ios
test aaa group AAA-TACACS alice alice-lab-password new-code
```

С хоста Windows тем же ключом, если установлен Python и пакет `tacacs_plus`. Источник будет `192.168.56.1`, он входит в `device vagrant-net`:

```powershell
py -3 -m pip install tacacs_plus
tacacs_client -u alice -H 192.168.56.10 -k lab-vagrant-key authenticate -p alice-lab-password
```

Команда `tacacs_client` оказывается в `Scripts` того Python, куда встал пакет. Нулевой код выхода — пароль принят.

## Если что-то пошло не так

Общая папка Windows не хранит права Unix. Скрипт поэтому копирует код в `/opt` и конфиг в `/etc`, а не запускает их с `/vagrant`. В `Vagrantfile` перед передачей в гостя из `provision.sh` убираются символы CR. В `.gitattributes` у скриптов и `Vagrantfile` зафиксирован LF. Если правили файл в редакторе, который дописал CRLF, сделайте в каталоге репозитория:

```powershell
git add --renormalize vagrant
git status
```

Порты и службы из гостя:

```powershell
vagrant ssh -c 'systemctl status tac_plus-ng tacacs-ui nginx --no-pager'
vagrant ssh -c 'ss -ltn sport = :49 or sport = :443 or sport = :8080'
vagrant ssh -c 'journalctl -u tac_plus-ng -u tacacs-ui -n 80 --no-pager'
```

- Браузер пишет, что сайт не открывается. Проверьте, что ВМ запущена (`vagrant status`) и что адаптер VirtualBox Host-Only смотрит в `192.168.56.0/24` (обычно адрес хоста `192.168.56.1`). Чужая подсеть на этом адаптере не отдаст `192.168.56.10`.
- Страница 502. nginx есть, uvicorn нет. Смотрите `journalctl -u tacacs-ui`.
- Вход «не держится». Открывайте именно `https://`, не обходя предупреждение о сертификате через голый HTTP мимо редиректа. Флаг Secure у cookie включён.
- «Слишком много попыток входа». Лимит `5/minute` с одного адреса. Подождите минуту.
- Сессии пустые после демо-скрипта. Пользователь веб-интерфейса `tacacsui` должен быть в группе `adm`. Проверка: `vagrant ssh -c 'id tacacsui'`.
- Сборка демона оборвалась. Повторите `vagrant provision`: пока нет `/usr/local/sbin/tac_plus-ng`, скрипт собирает его снова.
- Проверка `check-tacacs` не проходит, а веб открывается. Порт 49 и ключ `device vagrant-local` — в `journalctl -u tac_plus-ng`.
- Нужен чистый пароль заново. `vagrant destroy -f`, затем `vagrant up`: новый `.env` и новый пароль в конце вывода.
