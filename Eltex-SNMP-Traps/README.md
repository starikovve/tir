# SNMP-трапы на оборудовании Eltex (MES / ESR)

CLI у Eltex **не единый**: набор команд и ключевых слов зависит от линейки и даже от поколения внутри «MES23xx/53xx». Ниже — только то, что подтверждено официальными страницами docs.eltex-co.ru и руководствами с eltex.ru (загрузки проверены, ноябрь 2026). На устройстве сверяйте `?`.

Плейсхолдеры: `192.0.2.10` (NMS), `CHANGE_ME`. Не копируйте community из чужих примеров.

Семейства, которые нужно различать:

| Семейство | Типичные модели | Стиль CLI |
|---|---|---|
| **MES 6.6 (новое)** | MES2300-xx, MES3300-xx, MES3500I, MES5312, MES53xxA, MES5310-48, MES5400-xx, MES5410-48, MES5500-32, MES5600, MES5700 | `snmp-server server`, `snmp-server host … traps version 2c`, `snmp-server enable traps` |
| **MES 23xx/33xx/35xx/5324 (старшее)** | MES23xx, MES33xx, MES35xx, MES5324 | Тот же стиль, **другой** список ключевых слов (официальная KB отдельная) |
| **MES14xx / 24xx / 3400 / 37xx** | MES14xx, MES24xx, MES3400-xx, MES37xx | Не `snmp-server host`, а `snmp targetaddr` / `snmp notify` / `snmp enable traps` |
| **MES5448 / MES7048** | MES5448, MES7048 | `snmp-server host … traps version 2` (не `2c`), свой набор (`linkmode`, `stpmode`…) |
| **ESR** | ESR-30…ESR-3350 и др. | `snmp-server` (без `server`), host в подрежиме, свои группы трапов, модель `commit` / `confirm` |

---

## 1. Базовая настройка

### 1.1. MES 6.6 и MES 23xx/33xx/35xx/5324

Сначала включают агент (`snmp-server server` — на этих линейках обязателен), затем community и host.

```
configure
snmp-server server
snmp-server view ALL iso included
snmp-server community CHANGE_ME ro view ALL
snmp-server host 192.0.2.10 traps version 2c CHANGE_ME
snmp-server enable traps authentication
snmp-server enable traps link-status
```

- Community: `ro` / `rw`. View — через `snmp-server view` и `community … view NAME` (официально для MES23xx/33xx/35xx/5324).
- На **MES23xx/33xx/35xx/5324** community можно сразу ограничить адресом клиента: `snmp-server community CHANGE_ME ro 192.0.2.10`. Лимит — до **24** записей community/host/user.
- На **MES 6.6** в базовом примере KB адрес у community не указан: `snmp-server community CHANGE_ME ro`.
- `snmp-server host`: IPv4/IPv6/hostname, `traps` или `informs`, `version {1 | 2c | 3 {noauth|auth|priv}}`, community или SNMPv3 user, `udp-port` (default **162**), `filter`, для informs — `timeout` / `retries`, **`vrf NAME`**.
- Source трапов (руководство 6.6.13.5):

```
snmp-server source-interface traps loopback 1
snmp-server source-interface-ipv6 traps loopback 1
```

В таблице команд перечислены te / twe / hu / fo / port-channel / loopback / vlan и опция `vrf`. В release notes 6.6.5.4 упоминается OOB как source-interface для SNMP — синтаксис на коробке уточняйте `?` (в извлечённой таблице 6.6.13.5 `oob`/`gi` явно не попали).

### 1.2. MES14xx / 24xx / 3400 / 37xx

Префикс команд — **`snmp`**, не `snmp-server host`. Официальный пример (community для трапов отдельным index):

```
configure
snmp engineid 00.11.22.33.44.55
snmp view ALL 1 included
snmp user TrapUser
snmp community index 3 name CHANGE_ME security TrapUser
snmp group TrapGroup user TrapUser security-model v2c
snmp access TrapGroup v2c notify ALL
snmp targetparams TrapParams user TrapUser security-model v2c message-processing v2c
snmp targetaddr NmsHost param TrapParams 192.0.2.10 taglist TrapTag
snmp notify NmsNotify tag TrapTag type Trap
```

Исправление относительно формулировки «snmp-server targetaddr»: в актуальной документации Eltex команды пишутся как **`snmp targetaddr`**, **`snmp notify`**, **`snmp targetparams`**.

Замечания из официальной KB/руководства:

- У каждого community свой уникальный `index`. С ПО **10.3.6** можно ограничить community адресом: `snmp community index 1 name CHANGE_ME security ReadUser 192.0.2.10`.
- EngineID по умолчанию на всей линейке одинаковый (`80.00.08.1c.04.46.53`) — **задайте уникальный** (например, по MAC).
- Агент: `snmp-server enable` / `snmp-server disable` (default: включён).

### 1.3. MES5448 / MES7048

`snmp-server server` в официальной KB **нет**. Community с опциональным `ipaddress`, host с **`version 2`** (не `2c`):

```
configure
snmp-server community CHANGE_ME ro ipaddress 192.0.2.10
snmp-server host 192.0.2.10 traps version 2 CHANGE_ME
```

Для SNMPv3 обязательно `snmp-server engineid local …`, особенно в стеке (иначе при смене мастера engineID меняется и пользователи «отваливаются»).

### 1.4. ESR

Включается **`snmp-server`** (не `snmp-server server`). Community и host — раздельно. Host открывает подрежим; версия трапа в этом подрежиме **не** задаётся как `traps version 2c`.

```
configure
snmp-server
snmp-server community CHANGE_ME v2c ro
snmp-server community CHANGE_ME v2c ro 192.0.2.10
snmp-server host 192.0.2.10
 community CHANGE_ME
 port 162
 source-interface loopback 1
 exit
snmp-server enable traps snmp
commit
confirm
```

- У host: `community`, `port` (default **162**), `source-interface`, `source-address` (иначе — адрес ближайшего к NMS интерфейса), `vrf` задаётся уже в `snmp-server host 192.0.2.10 vrf NAME`.
- Community: `ro`/`rw`, адрес или `client-list`, `v1`/`v2c`, `view`, `vrf`.
- Перед настройкой: зона и IP на интерфейсе, где слушает SNMP (требование руководства ESR 1.40).
- `snmp-server trap link {ietf | cisco}` — формат link-трапов, default **ietf**.

---

## 2. `snmp-server enable traps`: ключевые слова по сериям

Официальные KB прямо пишут: **по умолчанию генерируются не все события** — нужные типы включают явно (кроме случаев, где в руководстве у типа указано «включено»).

### 2.1. Сводная таблица MES (коммутаторы)

Обозначения серий: **6.6** = MES2300/3300/3500I/5312/53xxA/5310-48/5400/5410/5500…; **23xx** = MES23xx/33xx/35xx/5324; **14xx** = MES14xx/24xx/3400/37xx; **5448** = MES5448/MES7048.

| Ключевое слово / синтаксис | Серии | Что делает (по официальным текстам) |
|---|---|---|
| `snmp-server enable traps` (без аргумента) | 6.6, 23xx, 5448 | 6.6: «включает поддержку SNMP trap-сообщений» (default включено). **5448: включает все типы**; также в руководстве 5448 эта же форма описана как «флаг аутентификации» (формулировки в одном руководстве расходятся — на устройстве проверяйте `show snmp`) |
| `authentication` | **6.6** (есть в KB и в руководстве 6.6.13.5). В списке KB **23xx нет** | На 6.6: трапы по событиям **login / logout / reject** (не только SNMP auth-failure). Default в руководстве: включено |
| `cpu` | 6.6 (KB), 23xx (KB), 5448 (KB) | В KB перечислено, отдельной расшифровки в извлечённых таблицах 6.6.13.5 нет. На **14xx** есть иная команда: `snmp-server enable traps cpu rate-limit [queue]` — превышение cpu-rate-limit (default выключено) |
| `dhcp-snooping` / `dhcp-snooping limit clients` | 6.6, 23xx (KB: `dhcp-snooping`; руководство 6.6: `dhcp-snooping limit clients`) | Достигнут предел числа DHCP-клиентов. Default в 6.6.13.5: **выключено** |
| `erps` | 6.6, 23xx | Трапы протокола ERPS. Default в 6.6.13.5: включено |
| `flex-link` | 6.6 (KB), 23xx (KB) | В KB есть; в главе Flex-link руководства 6.6.13.5 отдельной команды `enable traps flex-link` в извлечённом тексте нет — на коробке проверяйте `?`. Flex-link — резервирование канала (Ethernet / Port-channel) |
| `ipv6` / `ipv6 ospf` | 6.6, 23xx (KB: `ipv6`; руководство 6.6: **`ipv6 ospf`**) | OSPF для IPv6. Default в 6.6.13.5: включено |
| `l2protocol-tunnel` | 6.6, 23xx | Есть в KB и в примере конфигурации руководства 6.6.13.5 |
| `link-status` | 6.6, 23xx (KB, глобально). На 6.6 дополнительно per-interface `snmp trap link-status` | Смена состояния линка. На 6.6 interface-команда **по умолчанию включена** |
| `mac-notification` / `mac-notification change` / `flapping` | 6.6, 23xx (KB: `mac-notification`). Руководство 6.6: `change` (default **выкл.**) и `flapping` (default **вкл.**) | Изменение MAC-таблицы / MAC-flapping. Для `change` ещё нужны `mac address-table notification change` и на порту `snmp trap mac-notification change` |
| `memory` | 6.6 (KB), 23xx (KB), 5448 (KB) | В KB перечислено; детального описания в извлечённых главах руководств нет |
| `ospf` | 6.6, 23xx | Трапы OSPF. Default в 6.6.13.5: включено |
| `sensor` | 6.6 (KB), 23xx (KB), 5448 (KB) | В KB перечислено; детального описания в извлечённых главах нет |
| `storage` | 6.6 (KB), 23xx (KB), 5448 (KB) | В KB перечислено; детального описания в извлечённых главах нет |
| `vrrp` / `vrrp errors` | **6.6** (есть). В списке KB **23xx нет**. 5448: `vrrp` | 6.6: ошибки VRRP (`ttl-error`, `version-error`, `checksum-error`, `virtual-router-id-error`), default включено. 5448: трапы VRRPv2/v3, default включено |
| `port-security` | **только 23xx** (KB) | В списке 6.6 KB нет |
| `transceiver-alarm` | **только 23xx** (KB) | Аварии трансиверов; в списке 6.6 KB нет |
| `bgp` / `bgp state-changes limited` | **5448** | Два трапа RFC 4273: переход соседства в ESTABLISHED и выход из него. Default **выключено**. Формат в руководстве: `snmp-server enable traps bgp state-changes limited` |
| `linkmode` | **5448** | Глобальный флаг Link Up/Down. Default включено. Портовые трапы уходят, только если на порту ещё включён Link Trap |
| `stpmode` | **5448** | New root и topology change. Default включено |
| `multiusers` | **5448** | Второй пользователь вошёл на терминал (EIA-232/Telnet), пока сессия уже открыта. Default включено |
| `violation` | **5448** | Нарушение привязки MAC к порту (частота по умолчанию 30 с). Default **выключено**. Есть и на интерфейсе |
| `fip-snooping` | **5448** (руководство; в коротком списке KB нет) | FIP/FCoE snooping. Default включено; на порту нужен флаг Link Trap |
| `coldstart` / `warmstart` | **14xx** (`snmp enable traps …`) | Холодный старт / перезагрузка по `reload`. Default включено |
| `snmp enable traps snmp` / authentication-failure | **14xx** | В `show snmp traps`: `authentication-failure-traps`, default **Disable**. В подсказке `snmp enable traps ?` есть группа `snmp` |
| `errdisable …` | **14xx** | `snmp-server enable traps errdisable {storm-control\|loopback-detection\|udld}`, default включено. В `show snmp traps` также видны `errdisable-port-security` и `errdisable-overheat` — отдельных ключей в извлечённой таблице 10.4.6 нет |
| `dry-contacts` | **14xx** | Сухие контакты. Команда в руководстве: `snmp-server enable traps dry-contacts`. Default выключено |

Ключевые слова вроде `stp`, `loopback-detection`, `poe`, `environment`, `config` как глобальные типы **на MES 6.6/23xx в проверенных списках не найдены** (для ESR — свои, см. ниже). Не включайте их «на всякий случай».

Точечное включение (MES 6.6):

```
snmp-server enable traps authentication
snmp-server enable traps link-status
snmp-server enable traps ospf
snmp-server enable traps vrrp errors
snmp-server enable traps mac-notification change
no snmp-server enable traps dhcp-snooping limit clients
```

### 2.2. ESR: группы `snmp-server enable traps`

Без аргумента — **все** типы. С аргументом — группа (иногда с подтипом). Без подтипа в группе включаются все её трапы. Документация ESR 1.24 / 1.40:

| Команда | Назначение |
|---|---|
| `snmp-server enable traps` | Все типы |
| `snmp-server enable traps snmp [authentication\|coldstart\|linkdown\|linkup]` | Неверное community/пароль v3; рестарт SNMP-сервера; link down/up |
| `snmp-server enable traps config [commit\|confirm]` | Операции с конфигурацией: `commit` / `confirm` |
| `snmp-server enable traps entity [config-change]` | Операции с running-config |
| `snmp-server enable traps entity-sensor [threshold]` | Пересечение порогов датчиков |
| `snmp-server enable traps environment [pwrin\|pwrin-insert\|fan\|fan-speed-changed\|fan-speed-high\|memory-flash-low\|memory-flash-critical-low\|memory-ram-low\|memory-ram-critical-low\|cpu-load\|cpu-overheat-temp\|cpu-critical-temp\|cpu-supercooling-temp\|switch-overheat-temp\|switch-supercooling-temp\|board-overheat-temp\|board-supercooling-temp\|sfp-overheat-temp\|sfp-supercooling-temp]` | БП, вентиляторы, NAND/RAM, температура CPU/платы/SFP. В примере документации опечатка `enviroment` — верная команда **`environment`** |
| `snmp-server enable traps envmon [fan\|shutdown\|supply\|temperature]` | Вентиляторы, выключение, БП, температурные датчики. В примере опечатка `fun` — параметр **`fan`** |
| `snmp-server enable traps files-operations [successful\|failed\|canceled]` | Операции с файлами |
| `snmp-server enable traps flash [insertion\|removal]` | Внешние flash-накопители |
| `snmp-server enable traps interfaces [rx-utilization-high\|tx-utilization-high\|number-high]` | Утилизация / число IP-интерфейсов |
| `snmp-server enable traps ports [port-counters-errors]` | Ошибки счётчиков на чипе коммутации |
| `snmp-server enable traps screens [dest-limit\|source-limit\|icmp-threshold\|…]` | Срабатывание Screen/DoS-защит (длинный список в CLI Reference) |
| `snmp-server enable traps syslog` | Syslog-сообщения как SNMP-трапы |
| `snmp-server enable traps wifi [wifi-tunnels-number-in-bridge-high\|wifi-tunnels-operation]` | Wi-Fi контроллер / softgre |

Минимум, близкий к «link + auth + cpu/memory + sensor»:

```
snmp-server enable traps snmp authentication
snmp-server enable traps snmp linkup
snmp-server enable traps snmp linkdown
snmp-server enable traps environment cpu-load
snmp-server enable traps environment memory-ram-low
snmp-server enable traps environment memory-ram-critical-low
snmp-server enable traps entity-sensor threshold
```

---

## 3. Per-interface: `snmp trap link-status`

Подтверждено официально:

| Серия | Команда | Default |
|---|---|---|
| **MES 6.6** | В режиме интерфейса (и range): `snmp trap link-status` / `no …` | **Включено** («о состоянии настраиваемого порта») |
| **MES14xx/24xx/3400/37xx** | `snmp trap link-status` (подсказка `snmp trap ?` в KB). Также `snmp trap mac-address-table change [learnt\|removed]` (default выкл.) | Link Status в `show snmp traps` включён **на всех портах** (пример KB) |
| **MES5448/7048** | На интерфейсе: `snmp trap link-status`. Глобально: `snmp trap link-status all`. Нужен включённый флаг **Link Up/Down** (`snmp-server enable traps linkmode`) | linkmode по умолчанию включён |
| **ESR** | На физ. интерфейсе (gi/te/twe/fo/hu/**oob**): `[no] snmp trap link-status` | В англ. CLI Reference: **Enabled**. В рус. тексте 1.40 описание ошибочно говорит «о туннеле»; по смыслу и OID `ifLinkUpDownTrapEnable` это link up/down интерфейса |

На **MES23xx/33xx/35xx/5324** отдельной страницы с interface-командой в проверенных KB нет; есть глобальное `snmp-server enable traps link-status`. Наличие `snmp trap link-status` на порту **не подтверждено** — проверяйте `?` в `config-if`.

Глобальная категория (`enable traps link-status` / `linkmode` / `snmp linkup|linkdown`) и флаг на порту работают вместе: выключили порт — с этого порта link-трапы не уходят.

---

## 4. Различия серий (сводка)

| Тема | MES 6.6 | MES 23xx/33xx/35xx/5324 | MES14xx/24xx/37xx | MES5448/7048 | ESR |
|---|---|---|---|---|---|
| Включение агента | `snmp-server server` | `snmp-server server` | `snmp-server enable` (default вкл.) | не требуется в KB | `snmp-server` |
| Host | `snmp-server host … traps version 2c` | то же | `snmp targetaddr` + `notify` + `targetparams` | `snmp-server host … traps version 2` | `snmp-server host IP` → подрежим, `community` |
| Список трапов | auth, cpu, dhcp-snooping, erps, flex-link, ipv6, l2protocol-tunnel, link-status, mac-notification, memory, ospf, sensor, storage, vrrp | как 6.6, **без** auth/vrrp, **плюс** port-security, transceiver-alarm | coldstart/warmstart, snmp/auth-failure, errdisable, cpu rate-limit, dry-contacts; link/MAC — по портам | bgp, cpu, linkmode, memory, multiusers, sensor, storage, stpmode, violation, vrrp (+ fip-snooping в руководстве) | Группы snmp/config/environment/envmon/entity/… |
| `enable traps` без аргументов | поддержка трапов | не описано как «все» | нет такого в KB | **все типы** | **все типы** |
| Per-interface link | да, default вкл. | не подтверждено | да, default все порты | да + `link-status all`, нужен linkmode | да, default вкл., есть на OOB |
| Проверка | `show snmp` | `show snmp` | **`show snmp traps`**, `show snmp` | `show snmp` | `show running-config`, `show running-config full interfaces … \| include snmp` |
| Сохранение | `copy running-config startup-config` | типично то же (явной строки `write` в 6.6.13.5 нет) | `write startup-config` | `write memory [confirm]` или `copy system:running-config nvram:startup-config` | `commit` + `confirm`; `save` — candidate во flash |
| VRF / OOB | `host … vrf`, `source-interface … vrf` | не раскрыто в короткой KB | — | `show snmp source-interface` есть в руководстве | `host … vrf`, `community … vrf`, `source-interface` |

Не смешивайте MES23xx (старое поколение) и MES2300/5400 (ПО 6.6): списки `enable traps` **официально разные**.

---

## 5. Проверка и тест

```
show snmp
show running-config | include snmp
```

- **MES14xx/24xx/3400/37xx:** обязательно `show snmp traps` (статус типов, cpu-rate-limit, список портов с Link Status и MAC).
- **MES 6.6:** `show snmp`, также `show snmp views`, `show snmp groups`, `show snmp users`, `show snmp engineID`, `show snmp [vrf NAME | all]`. Команда `show snmp traps` в руководстве 6.6.13.5 **не найдена**.
- **MES5448:** `show snmp`, `show snmp-server`, `show snmp source-interface`.
- **ESR:** `show running-config` / `show configuration changes`; для порта: `show running-config full interfaces gigabitethernet 1/0/1 | include snmp`. Отдельная `show snmp traps` в проверенных страницах ESR не описана.

На NMS:

```
# tcpdump -ni eth0 udp port 162
# snmptrapd -f -Lo
```

Провокация: выключить/включить интерфейс (link), запрос с неверным community (authentication), на ESR — `commit` без/с `confirm` (если включены `traps config`).

---

## 6. Минимальный набор (link + authentication + cpu/memory + sensor)

### 6.1. MES 6.6 (2300/3300/5400/53xxA…)

```
configure
snmp-server server
snmp-server community CHANGE_ME ro
snmp-server host 192.0.2.10 traps version 2c CHANGE_ME
snmp-server enable traps authentication
snmp-server enable traps link-status
snmp-server enable traps cpu
snmp-server enable traps memory
snmp-server enable traps sensor
snmp-server source-interface traps loopback 1
exit
copy running-config startup-config
```

`cpu` / `memory` / `sensor` взяты из официальной KB этой линейки; в таблице команд SNMP руководства 6.6.13.5 они не расшифрованы — после настройки смотрите `show snmp` и при сомнении `snmp-server enable traps ?`.

На access-портах, где link-трапы не нужны:

```
interface gigabitethernet 1/0/10
 no snmp trap link-status
```

### 6.2. MES 23xx/33xx/35xx/5324

Тот же каркас, но **`authentication` в официальном списке нет**. Вместо отсутствующих типов — то, что есть:

```
configure
snmp-server server
snmp-server community CHANGE_ME ro 192.0.2.10
snmp-server host 192.0.2.10 traps version 2c CHANGE_ME
snmp-server enable traps link-status
snmp-server enable traps cpu
snmp-server enable traps memory
snmp-server enable traps sensor
exit
copy running-config startup-config
```

### 6.3. ESR

```
configure
snmp-server
snmp-server community CHANGE_ME v2c ro 192.0.2.10
snmp-server host 192.0.2.10
 community CHANGE_ME
 source-interface loopback 1
 exit
snmp-server enable traps snmp authentication
snmp-server enable traps snmp linkup
snmp-server enable traps snmp linkdown
snmp-server enable traps environment cpu-load
snmp-server enable traps environment memory-ram-low
snmp-server enable traps environment memory-ram-critical-low
snmp-server enable traps entity-sensor
exit
commit
confirm
```

### 6.4. MES14xx/24xx и MES5448

На 14xx/24xx после блока targetaddr/notify:

```
snmp enable traps coldstart
snmp enable traps warmstart
snmp enable traps snmp
snmp-server enable traps cpu rate-limit
```

Link уже default на портах; auth-failure по умолчанию выключен — его как раз включает группа `snmp`. Сохранить: `write startup-config`.

На 5448: `snmp-server enable traps linkmode`, `cpu`, `memory`, `sensor` (из KB), плюс на нужных портах `snmp trap link-status`. Отдельного `authentication` в списке KB нет (есть «флаг аутентификации» у `enable traps` без аргумента — формулировка спорная). Сохранить: `write memory`.

---

## 7. Сохранение конфигурации

| Платформа | Как закрепить изменения |
|---|---|
| MES 6.6 / 23xx | Candidate сразу в running при вводе команд. В flash: **`copy running-config startup-config`** (руководство 6.6.13.5) |
| MES14xx/24xx | **`write startup-config`** (или `write url`) |
| MES5448/7048 | **`write memory [confirm]`** или `copy system:running-config nvram:startup-config` |
| ESR | Ввод идёт в **candidate-config**. Активация: **`commit`** (привилегированный режим). Запускается таймер подтверждения, default **600 с** (`system config-confirm timeout`). Пока нет **`confirm`**, по таймеру running откатится (candidate при этом сохранится). Досрочно отменить применённое: `restore`. Сбросить неактивированный candidate: `rollback`. Показать diff: `show configuration changes`. **`save`** пишет candidate во flash. running-config, по KB, и так хранится в энергонезависимой памяти |

---

## 8. Отличия от OcNOS/B4COM и Juniper

Сравнение с гайдами `/workspace/b4com-snmp/B4COM-SNMP-Traps/README.md` и `/workspace/juniper-snmp/Juniper-SNMP-Traps/README.md`.

| Тема | Eltex | OcNOS / B4COM | Junos |
|---|---|---|---|
| Единство CLI | Несколько семейств с разным синтаксисом | Один CLI OcNOS (нюансы 6.6/7.0) | Единый `trap-group` + categories |
| Включение типов | `enable traps <keyword>` (MES/ESR) или `snmp enable traps` + портовые флаги (14xx) | `snmp-server enable traps <тип>` глобально | Категории у `trap-group`; default — все, кроме `timing-events` |
| Link per-interface | Есть на MES 6.6, 14xx, 5448, ESR; на старых 23xx не подтверждено | В документации OcNOS 6.6/7.0 только глобально | `traps` / `no-traps` на физическом и логическом, default вкл. |
| Authentication | На MES 6.6 — login/logout/reject; на 14xx — auth-failure (default выкл.); на ESR — `traps snmp authentication` | `snmp authentication` | Категория `authentication` |
| Syslog → трап | На ESR: `enable traps syslog`. На MES в проверенных списках отдельного syslog-типа нет | `enable traps syslog` + `logging snmp-traps <0-7>` | `event-options … then raise-trap` |
| Commit | MES: сразу running, отдельно write/copy. ESR: `commit` + обязательный `confirm` (таймер 600 с) | cmlsh: `commit`, затем `write` в startup | `commit` / `commit confirmed N` (минуты), `rollback` |
| Management VRF | MES 6.6: `vrf` у host и source-interface. ESR: `host … vrf`, community `vrf` | `vrf management` + `host-vrf` (6.6+) | `mgmt_junos` + `routing-instance` |
| Source address | MES 6.6: `source-interface traps`. ESR: `source-interface` / `source-address` | В проверенных страницах OcNOS отдельного аналога нет | `trap-options source-address lo0` |
| Получатель | MES 6.6/23xx/5448: `snmp-server host`. 14xx: targetaddr/notify. ESR: host-подрежим | `snmp-server host … version 2c` | Имя `trap-group` уходит как community |
| Проверка | 14xx: `show snmp traps`. Остальные MES: в основном `show snmp`. ESR: running-config | `show snmp trap`, `show snmp host` | `show snmp statistics`, `request snmp spoof-trap` |

---

## 9. Источники

Страницы и PDF с eltex.ru / docs.eltex-co.ru открывались на момент подготовки гайда (ноябрь 2026):

- [Управление по SNMP: MES2300/3300/3500I/5312/53xxA/5310-48/5400/5410/5500](https://docs.eltex-co.ru/pages/viewpage.action?pageId=533659677)
- [Управление по SNMP: MES23xx/33xx/35xx/5324](https://docs.eltex-co.ru/pages/viewpage.action?pageId=45462244)
- [Управление по SNMP: MES5448/MES7048](https://docs.eltex-co.ru/pages/viewpage.action?pageId=238813205)
- [Настройка SNMPv2: MES14xx, MES24xx, MES3400, MES37xx](https://docs.eltex-co.ru/pages/viewpage.action?pageId=141819929)
- [Фильтрация OID на MES23xx/33xx/35xx/5324](https://docs.eltex-co.ru/pages/viewpage.action?pageId=588677670)
- [Руководство пользователя MES Series 6.6.13.5 (PDF)](https://eltex.ru/storage/upload_center/files/51/MES_Series_user_manual_6.6.13.5.pdf)
- [Описание сообщений SNMP TRAP MES2300/3300/3500/5312/53xxA/5400/5500 (PDF)](https://eltex.ru/storage/upload_center/files/57/MES2300-%D1%85%D1%85_MES3300-xx_MES3500-xx_MES5312_MES53xxA_MES5400_MES5500_SNMP_TRAP_reference.pdf)
- [Мониторинг MES по SNMP 6.6.13.5 (PDF)](https://eltex.ru/storage/upload_center/files/17/MES_configuration_and_monitoring_via_SNMP_6.6.13.5.pdf)
- [Руководство пользователя MES14xx/24xx/3400/37xx 10.4.6 (PDF)](https://eltex.ru/storage/upload_center/files/35/MES_Series_user_manual_10.4.6.pdf)
- [Описание SNMP TRAP MES14xx/24xx/3400/37xx (PDF)](https://eltex.ru/storage/upload_center/files/60/MES14xx_MES24xx_MES3400-xx_MES37%D1%85%D1%85_TRAP_reference.pdf)
- [Руководство пользователя MES5448/MES7048 8.4.0.11.6 (PDF)](https://eltex.ru/storage/upload_center/files/62/MES5448_MES7048_user_manual_8.4.0.11.6.pdf)
- [Управление SNMP, ESR 1.24](https://docs.eltex-co.ru/pages/viewpage.action?pageId=499679783)
- [Настройка SNMP-сервера и TRAP, ESR 1.40](https://docs.eltex-co.ru/pages/viewpage.action?pageId=662246284)
- [Конфигурирование интерфейсов, ESR 1.40](https://docs.eltex-co.ru/pages/viewpage.action?pageId=662246226) (`snmp trap link-status`)
- [Особенности применения конфигурации на ESR](https://docs.eltex-co.ru/pages/viewpage.action?pageId=258605915) (`commit` / `confirm` / `restore` / `rollback` / `save`)
