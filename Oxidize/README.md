# Oxidized: резервные копии конфигураций сетевых устройств

Краткий учебный разбор [Oxidized](https://github.com/ytti/oxidized): как поставить сборщик, описать устройства трёх вендоров и забрать сохранённые конфигурации из git и REST.

Адреса в примерах — документационные сети из RFC 5737 (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`). Пароли вымышленные. В поле пароля не должно быть символа `:`, потому что это разделитель `router.db`.

## 1. Что это и зачем

Oxidized по расписанию заходит на сетевое оборудование (SSH, при необходимости Telnet), снимает конфигурацию моделью под конкретную ОС и кладёт текст в хранилище. В этом разборе хранилище — git-репозиторий: каждое изменение конфигурации становится коммитом.

Модель — это не шаблон конфига, а сценарий команд для данной ОС. Ниже используются три встроенные модели:

- `ios` — Cisco IOS;
- `junos` — Junos;
- `sros` — Nokia SR OS (бывший TiMOS).

Отдельный gem `oxidized-web` поднимает веб-страницу и REST. Им смотрят список узлов и двигают узел в голову очереди сбора.

Файл настроек — YAML без расширения: `~/.config/oxidized/config`. Список устройств для источника CSV — `~/.config/oxidized/router.db`. Каталог можно перенести переменной `OXIDIZED_HOME`.

## 2. Установка

Нужен либо контейнер, либо gem на хосте. Конфигурация в обоих случаях одна и та же: каталог `~/.config/oxidized` (в контейнере это домашний каталог пользователя `oxidized`).

### Docker

Официальный образ — `oxidized/oxidized`. Внутри процесс работает от пользователя `oxidized` с UID 30000, поэтому каталог на хосте должен принадлежать этому UID. Порт 8888 — веб-интерфейс и REST. Чтобы порт, проброшенный на хост, открывался, в `config` адрес `rest` должен быть `0.0.0.0:8888`, а не `127.0.0.1`.

```bash
# Каталог на хосте. В контейнере он станет домашним ~/.config/oxidized
mkdir -p ~/oxidized-config

# Файлы в томе создаёт UID 30000, ему же нужна запись в этот каталог
sudo chown 30000:30000 ~/oxidized-config

# Образ oxidized/oxidized, проброс 8888/tcp, том на место ~/.config/oxidized
sudo docker run --rm \
  -v ~/oxidized-config:/home/oxidized/.config/oxidized \
  -p 8888:8888/tcp \
  docker.io/oxidized/oxidized:latest
```

Пустой каталог при первом старте только порождает шаблон `config`, после чего процесс завершается с просьбой его отредактировать. Положите готовые `config` и `router.db` (разделы 3 и 4) в `~/oxidized-config` и запустите команду ещё раз. Остановить контейнер в этом примере можно Ctrl+C: флаг `--rm` удалит контейнер, том на хосте останется.

Журнал такого запуска виден в том же терминале. Для фонового режима добавьте `-d --name oxidized` и читайте журнал командой `docker logs -f oxidized`.

### Gem

Ниже пакеты для Debian 12 и Ubuntu 22.04 и новее, как в инструкции проекта. На Ubuntu пакет `libssh2-1-dev` лежит в компоненте `universe`. Имена пакетов на других дистрибутивах другие; полный список есть в README Oxidized.

```bash
# Репозиторий universe нужен Ubuntu для libssh2-1-dev
sudo add-apt-repository universe

# Зависимости сборки native-расширений oxidized (ssh, sqlite, yaml, git-библиотека)
sudo apt install ruby ruby-dev libsqlite3-dev libssl-dev pkg-config cmake \
  libssh2-1-dev libicu-dev zlib1g-dev g++ libyaml-dev libzstd-dev

# Сам сборщик и веб/REST. Без oxidized-web ключ rest в config не заработает
gem install oxidized oxidized-web
```

Запускать процесс лучше от отдельного пользователя, не от root:

```bash
# Учётная запись, под которой будет жить ~/.config/oxidized
sudo useradd -s /bin/bash -m oxidized
sudo su - oxidized
```

Дальше команды `oxidized` выполняются уже от этого пользователя. Каталог `~/.config/oxidized` появится при первом запуске.

## 3. Файл config

Путь: `~/.config/oxidized/config` (в Docker — `~/oxidized-config/config` на хосте).

Порядок перекрытия значений, от слабого к сильному: глобальные ключи, затем модель, затем группа, затем модель внутри группы, затем поля конкретной строки `router.db`. `timeout`, `timelimit` и `retries` задаются глобально: это пределы ожидания ответа и всего задания, а не переменные группы. Логин, пароль и `vars.enable` можно задать на каждом уровне.

Ключ `rest: 0.0.0.0:8888` — прежняя форма включения `oxidized-web`. Она всё ещё работает. Начиная с oxidized-web 0.16 предпочтительна секция `extensions.oxidized-web` (`load`, `listen`, `port`). Если указан `rest`, секция `extensions` игнорируется, поэтому в примере её нет.

Хук в конце необязателен. Текущий хук `exec` не разбирает `<%= %>`. В дочерний процесс он передаёт переменные окружения: `OX_EVENT`, `OX_NODE_NAME`, `OX_NODE_GROUP`, `OX_NODE_MODEL` и другие `OX_*`.

```yaml
---
username: backup                         # логин, если его нет ни в группе, ни в router.db
password: Doc-Global-Pass                # такой же запасной пароль (в примере вымышленный)
model: ios                               # модель по умолчанию
interval: 3600                           # секунды между полными кругами опроса
debug: false                             # true или флаг --debug поднимают уровень журнала до debug
threads: 30                              # верхняя граница числа одновременных сборов
timeout: 20                              # секунды ожидания одной операции при сборе
timelimit: 300                           # секунды на всё задание одного узла, затем статус timelimit
retries: 3                               # сколько раз повторить неудачный сбор до события node_fail
prompt: !ruby/regexp /^([\w.@-]+[#>]\s?)$/  # приглашение CLI, если своё не задала модель
next_adds_job: true                      # GET /node/next/<имя> сразу ставит отдельное задание сбора
rest: 0.0.0.0:8888                       # oxidized-web на всех IPv4-интерфейсах, порт 8888
vars:
  enable: Doc-Global-Enable              # пароль enable, если группа и строка устройства его не задали
groups:
  cisco:                                 # имя группы совпадает с полем group в router.db
    username: cisco-ro                   # логин устройств этой группы
    password: Cisco-Doc-Pass             # пароль группы cisco
    model: ios                           # модель Cisco IOS
    vars:
      enable: Cisco-Enable               # пароль привилегированного режима IOS
  juniper:
    username: junos-ro                   # логин группы Junos
    password: Junos-Doc-Pass             # пароль группы Junos
    model: junos                         # модель Junos
  nokia:
    username: sros-ro                    # логин группы Nokia SR OS
    password: Sros-Doc-Pass              # пароль группы SR OS
    model: sros                          # модель Nokia SR OS
pid: ~/.config/oxidized/pid              # файл с PID процесса
input:
  default: ssh, telnet                   # сначала SSH, если не вышло — Telnet
  debug: false                           # true пишет отладочный журнал сессии
  ssh:
    secure: false                        # не останавливать сбор из-за незнакомого ключа хоста
output:
  default: git                           # каждое изменение конфигурации — коммит
  git:
    user: Oxidized                       # имя автора коммита
    email: oxidized@example.com          # почта автора коммита
    repo: "~/.config/oxidized/devices.git"  # каталог bare-репозитория
    single_repo: true                    # все группы в одном репозитории, путь group/имя
source:
  default: csv                           # список узлов читается из router.db
  csv:
    file: ~/.config/oxidized/router.db   # путь к списку
    delimiter: !ruby/regexp /:/          # разделитель полей — двоеточие
    map:                                 # номер поля, считая с нуля
      name: 0                            # адрес или имя, куда подключаться
      model: 1                           # ios, junos или sros
      group: 2                           # cisco, juniper или nokia
      username: 3                        # логин этого узла, перекрывает группу
      password: 4                        # пароль этого узла, перекрывает группу
    vars_map:
      enable: 5                          # пароль enable этого узла
model_map:                               # необязательные псевдонимы имени модели
  cisco: ios
  juniper: junos
  nokia: sros
logger:
  appenders:
    - type: stderr                       # журнал в терминал (и в docker logs)
    - type: file
      file: ~/.config/oxidized/oxidized.log  # тот же журнал в файл
hooks:                                   # блок можно удалить, на сбор он не влияет
  log_backup:
    type: exec                           # выполнить команду оболочки
    events: [node_success, node_fail]    # удачный сбор и исчерпание retries
    cmd: 'echo "$OX_EVENT $OX_NODE_NAME group=$OX_NODE_GROUP" >> /tmp/oxidized-hooks.log'
    async: true                          # не задерживать очередь, пока команда пишет строку
    timeout: 30                          # предел самой команды хука, не SSH к устройству
```

При `single_repo: true` файл узла лежит в репозитории как `группа/имя`, например `cisco/192.0.2.11`. Без этого ключа Oxidized заводит отдельный bare-репозиторий на каждую группу рядом с указанным `repo`: `cisco.git`, `juniper.git`, `nokia.git`.

Коммит появляется, когда текст конфигурации изменился. Репозиторий создаётся при первой успешной записи, вручную `git init` не нужен. Это bare-репозиторий: рабочей копии файлов нет, читать их нужно через `git show` и `git log`.

## 4. Файл router.db

Рядом с `config`. Одна строка — одно устройство. Строка, у которой первый непробельный символ `#`, пропускается. Пустая строка не комментарий: источник CSV сделает из неё узел с пустым именем, поэтому пустых строк быть не должно.

Поля слева направо совпадают с `map` и `vars_map` из раздела 3: имя, модель, группа, логин, пароль, enable. Значения в строке перекрывают группу. У Junos и SR OS последнее поле пустое намеренно: эти модели не запрашивают пароль enable, но пустое поле всё равно записывается в `vars` узла и перекрывает глобальный `enable`.

```text
# name:model:group:username:password:enable
# Документационные адреса RFC 5737 и вымышленные пароли. Двоеточие в пароле нельзя.
192.0.2.11:ios:cisco:cisco-ro:Cisco-Doc-Pass:Cisco-Enable
192.0.2.12:ios:cisco:cisco-ro:Cisco-Doc-Pass:Cisco-Enable
# У junos пароль enable не используется, поле после последнего двоеточия пустое
198.51.100.21:junos:juniper:junos-ro:Junos-Doc-Pass:
198.51.100.22:junos:juniper:junos-ro:Junos-Doc-Pass:
# То же для Nokia SR OS, модель sros
203.0.113.31:sros:nokia:sros-ro:Sros-Doc-Pass:
203.0.113.32:sros:nokia:sros-ro:Sros-Doc-Pass:
```

`name` здесь — адрес, на который Oxidized открывает SSH. Отдельной колонки `ip` в этом примере нет.

## 5. Шаблон ERB для группы cisco

Oxidized не подставляет ERB в снятую с устройства конфигурацию. Её текст пишет модель (для IOS это вывод команд устройства вроде `show running-config`) и затем, если так настроено, фильтр секретов. Сам файл `config` — обычный YAML.

Внутри Oxidized другие механизмы, и это не ERB:

- хук `exec` подставляет данные переменными `$OX_NODE_NAME` и остальными `$OX_*`;
- файлы моделей — код Ruby (`#{node.name}` доступен в блоках `pre` и `post` экземпляра модели);
- страницы `oxidized-web` собраны на Haml.

Шаблон ниже нужен для другого: команда `erb` на хосте генерирует строки `router.db` группы `cisco`. Oxidized этот файл не открывает. Сохраните его, например, как `cisco-group.erb` рядом со своими заметками, не в каталог, откуда Oxidized читает `config`.

Режим `-T -` обрезает перевод строки у тегов `-%>`. Без обрезки служебные строки ERB превратятся в пустые строки `router.db`, а пустая строка станет узлом с пустым именем.

```erb
<%# Этот файл — генератор строк router.db для группы cisco. Oxidized его не читает. -%>
<%# Запуск: erb -T - cisco-group.erb >> ~/.config/oxidized/router.db -%>
<%# Два вымышленных устройства. Поля те же, что map/vars_map в config. -%>
<% devices = [
     { name: "192.0.2.11", user: "cisco-ro", pass: "Cisco-Doc-Pass", enable: "Cisco-Enable" },
     { name: "192.0.2.12", user: "cisco-ro", pass: "Cisco-Doc-Pass", enable: "Cisco-Enable" }
   ] -%>
# группа cisco, строки собраны командой erb
<% devices.each do |device| -%>
<%= device[:name] %>:ios:cisco:<%= device[:user] %>:<%= device[:pass] %>:<%= device[:enable] %>
<% end -%>
```

```bash
# -T - включает обрезку строк, заканчивающихся на -%>
# >> дописывает в router.db. Повторный запуск продублирует те же узлы
erb -T - cisco-group.erb >> ~/.config/oxidized/router.db
```

В Docker цель дописывания — файл на томе, `~/oxidized-config/router.db`. После правки списка узлов работающий процесс подхватит его запросом `GET /reload` (или перезапуском).

## 6. Запуск сбора и просмотр результата

Перед стартом на месте должны лежать `config` и `router.db`. Первый успешный сбор создаст bare-репозиторий.

Gem, от пользователя `oxidized`:

```bash
# Обычный процесс: опрос раз в interval и приём REST на порту из config
oxidized

# Тот же процесс с журналом уровня debug в настроенные appenders
oxidized --debug
```

Одна из этих команд, не обе сразу. В Docker используется команда из раздела 2.

Журнал:

```bash
# Копия журнала из appender type: file
tail -f ~/.config/oxidized/oxidized.log

# Строки необязательного хука log_backup
tail -f /tmp/oxidized-hooks.log
```

В контейнере файл журнала лежит на томе: `~/oxidized-config/oxidized.log`. Поток stderr того же процесса показывает `docker logs -f oxidized`.

Веб-интерфейс: [http://127.0.0.1:8888/](http://127.0.0.1:8888/). Корень сразу перенаправляет на `/nodes`.

```bash
# JSON-список узлов: имя, модель, группа, статус и время последнего сбора
curl -sS http://127.0.0.1:8888/nodes.json

# Поставить 192.0.2.11 в голову очереди.
# При next_adds_job: true для него создаётся отдельное задание.
# Без суффикса .json ответ — редирект на /nodes, тело сбора в этот ответ не входит.
curl -sS -D - -o /dev/null http://127.0.0.1:8888/node/next/192.0.2.11

# Тот же сдвиг очереди, но тело ответа — JSON-строка ok
curl -sS http://127.0.0.1:8888/node/next/192.0.2.11.json
```

Сохранённый текст попадает в git, когда сбор успешен и текст отличается от предыдущего коммита. Путь внутри репозитория при `single_repo: true` — `cisco/192.0.2.11`. На хосте с gem репозиторий — `~/.config/oxidized/devices.git`. В Docker тот же каталог на томе — `~/oxidized-config/devices.git`.

```bash
# История коммитов bare-репозитория
git --git-dir ~/.config/oxidized/devices.git log --oneline

# Текст последней копии IOS-узла (каталог — группа, имя файла — name)
git --git-dir ~/.config/oxidized/devices.git show HEAD:cisco/192.0.2.11

# История одного узла Junos и одного узла SR OS
git --git-dir ~/.config/oxidized/devices.git log -p -- juniper/198.51.100.21
git --git-dir ~/.config/oxidized/devices.git log -p -- nokia/203.0.113.31
```

Для тома Docker замените `--git-dir` на `~/oxidized-config/devices.git`. Пока устройство недоступно (а документационные адреса из примера недоступны), в `nodes.json` будет ошибка сбора, коммита не будет, и `git show` сообщит, что репозитория или пути ещё нет. Это ожидаемо: появление коммита означает, что SSH до устройства прошёл и модель вернула конфигурацию.
