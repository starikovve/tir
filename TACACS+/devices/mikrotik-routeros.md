# MikroTik RouterOS

Своего клиента TACACS+ в RouterOS нет. Ни `/user tacacs`, ни порта 49, ни общего ключа TACACS+ в этой системе не существует; выдумывать такие команды нельзя. Запросы на встроенный TACACS+ в форуме MikroTik годами висят невыполненными. Для входа администратора (SSH, Telnet, WinBox, WebFig, API) RouterOS умеет локальную базу и **RADIUS**.

Ниже — эта замена, не «TACACS+ другими словами». Следствия протокола, а не настроек:

- авторизация выдаётся один раз, атрибутом группы в Access-Accept (`Mikrotik-Group`). Покомандной авторизации нет;
- учёт `/user aaa accounting` — это вход и выход, не каждая команда;
- пароль RADIUS прячется по правилам RADIUS, тело запроса не шифруется целиком, как в TACACS+.

Сервер tac_plus-ng из этого каталога RADIUS-запросы примет только после отдельной настройки `radius` в его конфигурации. Проще поставить рядом обычный RADIUS (FreeRADIUS и аналоги) с клиентом `192.0.2.25` и тем же смыслом групп: `full` для админов, `read` для операторов. К tac_plus-ng эти команды устройство не подключают.

Локальная база проверяется **раньше** RADIUS. Если имя уже есть в `/user`, внешний сервер не спрашивают. Обратной стороны у этого правила нет: пользователь, которого нет локально, при мёртвом RADIUS не попадёт внутрь «запасным» паролем. Аварийный вход — локальный пользователь с тем именем, под которым реально заходят в аварию, плюс доступ не только по IP управления.

WinBox и WebFig считают CHAP. SSH и Telnet — PAP. На RADIUS должны быть включены оба, иначе половина способов входа молча не пройдёт.

## Конфигурация (RADIUS)

```routeros
# Встроенные группы full и read уже есть. Своя группа нужна, только если политик не хватает.
# /user group add name=noc policy=ssh,read,write,test,winbox,web,api,reboot,!ftp

# Клиент RADIUS. service=login — именно административный вход, не PPP и не hotspot.
/radius add address=192.0.2.10 secret="lab-radius-key" service=login timeout=3s

# Второй сервер. RouterOS опрашивает записи /radius с нужным service.
/radius add address=192.0.2.11 secret="lab-radius-key" service=login timeout=3s

# Источник — адрес на самом маршрутизаторе, тот, что прописан клиентом на RADIUS.
/radius set [find address=192.0.2.10] src-address=192.0.2.25
/radius set [find address=192.0.2.11] src-address=192.0.2.25

# use-radius включает внешнюю проверку. default-group подставляется, если сервер не прислал группу
# или прислал группу из exclude-groups.
# exclude-groups=full не даёт поднять себе полные права подменой RADIUS,
# если у того, кто правит /radius, нет policy=policy.
/user aaa set use-radius=yes accounting=yes default-group=read exclude-groups=full
```

На RADIUS в Access-Accept для админа возвращают `Mikrotik-Group = full`, для оператора — `Mikrotik-Group = read` (вендор MikroTik, 14988). Имена групп должны существовать в `/user group`.

## Построчно

| Команда | Зачем |
| --- | --- |
| `/radius add address=192.0.2.10 secret="lab-radius-key" service=login timeout=3s` | Сервер, секрет и служба. Без `service=login` записи учёта и логина администратора на этот хост не уйдут. `timeout=3s` — явное ожидание; значение по умолчанию короткое, по WAN сервер выглядит мёртвым. |
| вторая строка `/radius add … 192.0.2.11` | Резервный RADIUS. Это не TACACS+ secondary и не общий ключ из `tac_plus-ng.cfg`. |
| `/radius set … src-address=192.0.2.25` | Источник RADIUS-пакетов. На сервере клиентом (NAS) должен быть этот адрес, иначе Access-Request отбросят по неизвестному клиенту. |
| `/user aaa set use-radius=yes` | Разрешить спрашивать RADIUS, если имени нет в `/user`. Пока `no`, блок `/radius` на вход администратора не влияет. |
| `accounting=yes` | Слать accounting на логин и логаут. Статистика трафика интерфейсов сюда не входит. Промежуточные обновления — отдельное `interim-update` (по умолчанию `0s`, только start/stop). |
| `default-group=read` | Группа, если сервер промолчал про `Mikrotik-Group`. `read` не даёт менять конфигурацию. Ставить сюда `full` опасно. |
| `exclude-groups=full` | Даже если RADIUS прислал `full`, подставить `default-group`. Защита от повышения привилегий через подмену сервера RADIUS. |

Полезные проверки, все ещё про RADIUS:

```routeros
/radius monitor 0
/user aaa print
/user active print
```

`/radius monitor` показывает счётчики access-request и timeout. Нулевые requests при попытке входа значат, что запрос не создаётся: `use-radius=no`, у записи нет `service=login`, или имя уже есть локально.
