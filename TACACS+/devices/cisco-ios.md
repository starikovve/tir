# Cisco IOS и IOS-XE

Клиент TACACS+ встроен. Ниже — IOS 15.2+ и IOS-XE: именованный `tacacs server` и группа серверов. Старый `tacacs-server host` вынесен отдельно, его не смешивают с новым на одном и том же адресе.

Адреса серверов совпадают с [`../server/tac_plus-ng.cfg`](../server/tac_plus-ng.cfg). Ключ в примере — ключ `core-r1` (`192.0.2.21`). На `core-r2` строка `key` другая: `core-r2-key`.

Локального пользователя создают **до** `aaa new-model`. Отказ сервера (неверный пароль) не переключает на `local`. `local` используется, когда группа не ответила.

## Конфигурация

```ios
hostname core-r1
!
! Аварийный вход, если оба TACACS+ молчат. secret хранится хешем, не как key 7.
username breakglass privilege 15 secret LabBreakGlass
!
aaa new-model
!
! Именованный сервер. Дальше на него ссылаются по имени, не по IP.
tacacs server TACACS-1
 address ipv4 192.0.2.10
 key 0 core-r1-key
 timeout 5
 single-connection
!
tacacs server TACACS-2
 address ipv4 192.0.2.11
 key 0 core-r1-key
 timeout 5
 single-connection
!
aaa group server tacacs+ AAA-TACACS
 server name TACACS-1
 server name TACACS-2
 ip tacacs source-interface Loopback0
!
! Глобальный источник на случай запроса мимо группы. Loopback0 уже должен иметь адрес.
ip tacacs source-interface Loopback0
!
! default — список, который линии берут сами. local только при недоступности группы.
aaa authentication login default group AAA-TACACS local
aaa authentication enable default group AAA-TACACS enable
! Отдельный список: последовательная консоль не спрашивает TACACS+.
aaa authentication login CONSOLE local
!
! Старт оболочки. Без ответа priv-lvl с сервера сессия не откроется.
aaa authorization exec default group AAA-TACACS local
! Уровни перечисляют по одному. 2–14 здесь никто не получает, их нет в списке.
aaa authorization commands 0 default group AAA-TACACS local
aaa authorization commands 1 default group AAA-TACACS local
aaa authorization commands 15 default group AAA-TACACS local
! Иначе команды уже из режима configure уходят на устройство без вопроса серверу.
aaa authorization config-commands
!
aaa accounting exec default start-stop group AAA-TACACS
aaa accounting commands 1 default start-stop group AAA-TACACS
aaa accounting commands 15 default start-stop group AAA-TACACS
!
! Консоль не наследует авторизацию команд, пока это не включено. Для первого включения
! разумнее оставить консоль на локальном списке (см. line con 0) и не ставить эту строку,
! пока VTY уже проверен.
! aaa authorization console
!
line con 0
 login authentication CONSOLE
!
line vty 0 4
 login authentication default
 authorization exec default
 authorization commands 1 default
 authorization commands 15 default
 accounting exec default
 accounting commands 1 default
 accounting commands 15 default
 transport input ssh
```

## Построчно

| Команда | Зачем |
| --- | --- |
| `username breakglass privilege 15 secret …` | Локальная учётка уровня 15. Срабатывает, когда метод `local` достигнут, то есть серверы не ответили. |
| `aaa new-model` | Включает AAA. Пока его нет, `tacacs server` и списки методов не управляют входом. Снимается отдельной процедурой, не «отменой одной строки» вслепую. |
| `tacacs server TACACS-1` | Объект сервера. Имя локальное, на tac_plus-ng оно не уходит. |
| `address ipv4 192.0.2.10` | Куда открывать TCP/49. |
| `key 0 core-r1-key` | Общий ключ этого NAS. `0` значит «дальше открытый текст в этой команде». В running-config IOS покажет тип 7, это не криптостойкое хранение. Ключ обязан совпасть с `device core-r1 { key = … }`. |
| `timeout 5` | Сколько секунд ждать ответ, прежде чем считать сервер недоступным и перейти к следующему. |
| `single-connection` | Держать один TCP и мультиплексировать запросы. tac_plus-ng это умеет. Если посередине режут простаивающий TCP, симптом — «зависшие» логины; тогда строку убирают. |
| `aaa group server tacacs+ AAA-TACACS` | Именованная группа. В методах пишут её, а не `group tacacs+` (последняя означает «все серверы, сконфигурированные на коробке»). |
| `server name TACACS-1` | Порядок опроса: сначала первый ответивший по списку. Второй используется после таймаута первого. |
| `ip tacacs source-interface Loopback0` | Внутри группы: адрес источника пакетов к серверу. Тот же адрес должен быть в `device` на tac_plus-ng. |
| `ip tacacs source-interface Loopback0` (глобально) | То же для запросов, которые пошли не через группу. |
| `aaa authentication login default group AAA-TACACS local` | Проверка пароля на VTY/SSH. `local` — только если группа не ответила. Явный FAIL с сервера локальный пароль не открывает. |
| `aaa authentication enable default group AAA-TACACS enable` | `enable` спрашивает TACACS+ (пользователь `$enab15$` / enable-пароль в конфиге демона), иначе локальный `enable secret`. |
| `aaa authorization exec default group AAA-TACACS local` | Можно ли открыть оболочку и с каким `priv-lvl`. В профиле admins это `set priv-lvl = 15` при пустом `cmd`. |
| `aaa authorization commands N default …` | Каждую команду уровня N послать на сервер. N — один уровень, диапазона в синтаксисе нет. |
| `aaa authorization config-commands` | Авторизовать и команды режима конфигурации. Без строки фильтруется в основном exec. |
| `aaa accounting exec default start-stop …` | Запись старта и завершения оболочки. |
| `aaa accounting commands N default start-stop …` | Отдельная accounting-запись на команду этого уровня. Попадает в `accounting log` tac_plus-ng. |
| `aaa authentication login CONSOLE local` | Имя списка методов для консоли. В группе TACACS+ его нет. |
| `line con 0` / `login authentication CONSOLE` | Последовательная консоль использует список CONSOLE, а не default. |
| `line vty 0 4` | Четыре виртуальных терминала SSH (диапазон расширяют по факту). |
| `login authentication default` | Явно привязать логин VTY к списку default. После `aaa new-model` это и так список по умолчанию; строка фиксирует намерение. |
| `authorization exec default` | На этой линии запрашивать авторизацию оболочки. |
| `authorization commands 1|15 default` | На этой линии запрашивать авторизацию команд. Без строк на line глобальный `aaa authorization commands` на VTY может не применяться так, как ждут. |
| `accounting exec|commands … default` | Включить учёт, уже объявленный в AAA, на этой линии. |
| `transport input ssh` | Не принимать telnet на этих VTY. |

Проверка с коробки, не открывая вторую сессию администратора:

```ios
test aaa group AAA-TACACS alice alice-lab-password new-code
show tacacs
show aaa servers
```

## Устаревший синтаксис

На старом IOS вместо блока `tacacs server`:

```ios
tacacs-server host 192.0.2.10 key 0 core-r1-key timeout 5
tacacs-server host 192.0.2.11 key 0 core-r1-key timeout 5
!
aaa group server tacacs+ AAA-TACACS
 server 192.0.2.10
 server 192.0.2.11
 ip tacacs source-interface Loopback0
```

`tacacs-server host` объявляет сервер одной строкой: адрес, ключ, таймаут. В группе на него ссылаются адресом (`server 192.0.2.10`), не именем. `single-connection` на этой ветке задаётся так: `tacacs-server host 192.0.2.10 single-connection` (набор ключевых слов зависит от релиза). Смысл списков `aaa authentication` / `authorization` / `accounting` тот же.

Не держите на одном маршрутизаторе и `tacacs-server host 192.0.2.10`, и `tacacs server` с тем же адресом: часть релизов применяет один из двух определений и молча игнорирует второе.
