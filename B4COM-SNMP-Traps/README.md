# SNMP-трапы на коммутаторах B4COM (OcNOS)

Коммутаторы B4COM работают под IP Infusion OcNOS. Отдельной SNMP-документации B4COM нет (на момент подготовки гайда сайт b4com.ru — заглушка), поэтому синтаксис сверен с официальными руководствами **OcNOS 6.6 и 7.0** (System Management, профили DC и SP) на documentation.ipinfusion.com / docs.ipinfusion.com.

> Проверяйте подсказки `?` на своей версии: набор ключевых слов у `snmp-server enable traps` расширялся в 6.6.0 и 7.0.0.
> Все примеры — с плейсхолдерами (`192.0.2.10`, `CHANGE_ME`). Не копируйте community и пароли из чужих конфигов.
> Работайте в **cmlsh**. Оболочка `imish` официально не поддерживается и рассинхронизирует конфигурацию.

**Метки версий:** «все» — есть в справочнике и до 6.6, и в 7.x; **6.6+** / **7.0+** — когда команда или ключевое слово появились в Applicability или в формальном синтаксисе; **★** — актуально для свежих 6.6 / 7.x.

---

## 1. Транзакционный CLI: без `commit` изменения не применяются

OcNOS (cmlsh) — транзакционный CLI (с OcNOS 5.0). Команды в `configure terminal` попадают в candidate-конфиг и **не действуют**, пока не выполнен `commit`.

| Команда | Режим | Назначение |
|---|---|---|
| `configure terminal` | exec | Войти в режим конфигурации |
| `show transaction current` | exec и config | Показать незакоммиченные изменения (без mode-change, `show` и action-команд) |
| `commit` | config | Применить candidate к running-config |
| `commit confirmed timeout <1-86400>` | config | Пробный commit (по умолчанию 300 с); иначе откат. Подтверждение: `confirm-commit`. Отмена: `cancel-commit` (6.3.0+) |
| `abort transaction` | config | Отбросить candidate |
| `show transaction last-aborted` | exec/config | Последняя отменённая транзакция |
| `write` / `write memory` / `copy running-config startup-config` | privileged exec | Сохранить running в startup. `commit` **не** делает это сам |

```
#configure terminal
(config)# ... команды ...
(config)# show transaction current
(config)# commit
(config)# exit
#write
```

Если выйти без `commit`/`abort`, CLI предупредит: `Un-committed transactions present. Please do commit or abort before exiting.`

---

## 2. Базовая настройка SNMP

Порядок как в официальном примере «VRF Management Standard Configuration»: view → community (или user) → host → `snmp-server enable snmp`. Агент слушает **только один VRF одновременно** (management, default или пользовательский). На B4COM обычно используют `vrf management`.

Параметр `vrf NAME` у SNMP-команд появился в **6.5.3**. С **6.6.0** трапы можно отправлять из другого VRF, чем тот, где включён агент: у `snmp-server host` это параметр `host-vrf`. SNMP GET/WALK работают только в VRF, где включён агент; трапы/informs уходят из `host-vrf`.

Максимум **8** SNMP-хостов.

### 2.1. Включение агента

```
snmp-server enable snmp (vrf (NAME|management)|)
no snmp-server enable snmp (vrf (NAME|management)|)
```

```
(config)# snmp-server enable snmp vrf management
```

Команда запускает SNMP-агент по UDP. Без неё опрос и (как правило) отправка трапов не заработают.

### 2.2. View и community (SNMPv2c)

```
snmp-server view VIEW-NAME OID-TREE (included | excluded) (vrf (NAME|management)|)
snmp-server community WORD (view VIEW-NAME version (v1 | v2c) ro | group (network-admin|network-operator) | ro | use-acl WORD) (vrf (NAME|management)|)
```

Имя community — до 32 символов. Встроенные группы `network-admin` и `network-operator` в справочнике описаны как read-only (`network-operator` — default). Можно привязать community к view (`version v1|v2c ro`) или ограничить ACL (`use-acl`).

```
(config)# snmp-server view all .1 included vrf management
(config)# snmp-server community CHANGE_ME group network-operator vrf management
```

Вариант с явным view:

```
(config)# snmp-server community CHANGE_ME view all version v2c ro vrf management
```

Опционально (встречается в официальных примерах):

```
(config)# snmp-server location vrf management "DC1-ROW-A"
(config)# snmp-server contact vrf management "noc@example.invalid"
```

### 2.3. Получатель трапов

Формальный синтаксис (справочник; `udp-port` и `vrf` необязательны). В гайдах 6.6.0+ к нему добавляют `host-vrf`:

```
snmp-server host (A.B.C.D | X:X::X:X | HOSTNAME) traps version (1 | 2c) WORD (|udp-port <1-65535>) (vrf (NAME|management)|)
snmp-server host (A.B.C.D | X:X::X:X | HOSTNAME) informs version (2c WORD | 3 (noauth | auth | priv) WORD) (|udp-port <1-65535>) (vrf (NAME|management)|)
snmp-server host (A.B.C.D | X:X::X:X | HOSTNAME) traps version 3 (noauth | auth | priv) WORD (|udp-port <1-65535>) (vrf (NAME|management)|)
no snmp-server host (A.B.C.D | X:X::X:X | HOSTNAME) (vrf (NAME|management)|)
```

По умолчанию версия **v2c**, UDP-порт **162**. `WORD` — community (v1/v2c) или имя SNMPv3-пользователя. `informs` для v2c и v3; для v1 — только traps. Параметр `vrf` задаёт SNMP-контекст агента, `host-vrf` (**6.6.0+**) — VRF исходящей отправки.

Типичный вариант для management VRF:

```
(config)# snmp-server host 192.0.2.10 traps version 2c CHANGE_ME udp-port 162 vrf management host-vrf management
```

На версиях до 6.6.0 опустите `host-vrf`. IPv6 поддерживается: `snmp-server host 2001:db8::10 traps version 2c CHANGE_ME udp-port 162 vrf management host-vrf management`.

### 2.4. SNMPv3 (пользователь + хост)

```
snmp-server user WORD ((network-operator|network-admin|WORD|) ((auth (md5 | sha) (encrypt|) AUTH-PASSWORD) ((priv (des | aes) PRIV-PASSWORD) |) |) (vrf (NAME|management)|)
no snmp-server user USER-NAME (vrf (NAME|management)|)
```

Имя пользователя: **5–32** алфавитно-цифровых символа. Пароль privacy: **8–33** символа. Длину AUTH-пароля уточните через `?`. `encrypt` — только чтобы заново вставить уже зашифрованную строку из running-config, не для «своего» хеша.

Уровни на `snmp-server host`: `noauth` (noAuthNoPriv), `auth` (authNoPriv), `priv` (authPriv).

```
(config)# snmp-server user nmsv3 auth sha AUTH_CHANGE_ME priv aes PRIV_CHANGE_ME vrf management
(config)# snmp-server host 192.0.2.10 traps version 3 priv nmsv3 udp-port 162 vrf management host-vrf management
```

### 2.5. Готовый блок базовой настройки (v2c, management VRF)

```
configure terminal
snmp-server view all .1 included vrf management
snmp-server community CHANGE_ME group network-operator vrf management
snmp-server host 192.0.2.10 traps version 2c CHANGE_ME udp-port 162 vrf management host-vrf management
snmp-server enable snmp vrf management
commit
exit
write
```

---

## 3. Типы трапов: `snmp-server enable traps`

```
snmp-server enable traps <тип>
no snmp-server enable traps <тип>
```

Режим: configure. Без ключевого типа команда в формальном синтаксисе **не задаётся** — тип обязателен. Отключение — через `no` с тем же типом.

В справочнике Default указан как «Enabled», но в рабочих примерах OcNOS 7.0 `show snmp trap` показывает типы как **disabled**, пока их явно не включат (для `alarms` отдельно сказано: «disabled by default»). Всегда включайте нужные типы явно и проверяйте `show snmp trap`.

Ниже — ключевые слова, подтверждённые в Command Syntax, Parameters/Examples и/или в выводе `show snmp trap` из гайдов 6.6/7.0. Команды `lldp`, `mlag`/`mcec`, `cfm`, `entity` в этих списках и в примере `show snmp trap` **отсутствуют** — в гайд не включены.

| Ключевое слово / синтаксис | OcNOS | Что включает |
|---|---|---|
| `snmp-server enable traps link` | все | Модуль link-уведомлений («Module notifications enable»). На практике включают конкретные события, см. ниже |
| `snmp-server enable traps link linkDown` | все | IETF linkDown |
| `snmp-server enable traps link linkUp` | все | IETF linkUp |
| `snmp-server enable traps link include-interface-name` | все | Добавить имя интерфейса в varbind linkUp/linkDown (в `show snmp trap` отображается как `linkWithIfname`). Само по себе трапы не генерирует |
| `snmp-server enable traps snmp` | все | Уведомления RFC 1157 |
| `snmp-server enable traps snmp authentication` | все | SNMP authentication failure |
| `snmp-server enable traps alarms` | **7.0+** ★ | Трапы модели аварий OcNOS (Alarm MIB). Нужен FMS, см. ниже. **Не поддерживаются в SNMPv1** |
| `snmp-server enable traps syslog` | **6.6+** ★ | Передача syslog-сообщений SNMP-трапами. Фильтр: `logging snmp-traps` |
| `snmp-server enable traps ospf` | все | OSPFv2 |
| `snmp-server enable traps ospf6` | все | OSPFv3 |
| `snmp-server enable traps bgp` | все | BGP (глобально, не per-neighbor) |
| `snmp-server enable traps isis` | все | IS-IS |
| `snmp-server enable traps vrrp` | все | VRRP |
| `snmp-server enable traps vxlan` | все | VXLAN |
| `snmp-server enable traps pim` | **7.0+** ★ | PIM. Есть в формальном синтаксисе 7.0 DC и в примерах `show running-config snmp` / `show snmp trap`. В формальном синтаксисе 6.6 (DC/SP) ключевого слова нет; на 6.6 проверьте `?` |
| `snmp-server enable traps twamp` | **6.6+** ★ | TWAMP |
| `snmp-server enable traps mpls` | все | MPLS |
| `snmp-server enable traps mplsl3vpn` | все ★ | MPLS L3VPN. В формальном синтаксисе **7.0 DC** есть; в строке синтаксиса 6.6 нет, но слово есть в Parameters и Examples 6.6 |
| `snmp-server enable traps pw` | все | Pseudowire (`mpls pw` в `show snmp trap`) |
| `snmp-server enable traps pwdelete` | все | Удаление pseudowire (`mpls pw delete`) |
| `snmp-server enable traps rsvp` | все | RSVP (`mpls rsvp` в `show snmp trap`). Есть в Parameters и Examples 6.6/7.0, но **пропущено** в строке Command Syntax — на устройстве проверьте `?` |
| `snmp-server enable traps rib` | все | RIB. Аналогично rsvp: Parameters, Examples и строка в `show snmp trap`, но нет в строке Command Syntax |

Формальный синтаксис **OcNOS 7.0 DC** (самый полный):

```
snmp-server enable traps (link(|linkDown|linkUp|include-interface-name)|snmp(|authentication)| mpls|pim|pw|pwdelete|ospf|bgp|isis|mplsl3vpn|vxlan|vrrp|ospf6|syslog|twamp|alarms)
```

Формальный синтаксис **OcNOS 6.6** (DC и SP) уже содержит `syslog` и `twamp`, но **без** `pim`, `alarms` и `mplsl3vpn` в этой строке:

```
snmp-server enable traps (link(|linkDown|linkUp|include-interface-name)|snmp(|authentication)| mpls|pw|pwdelete|ospf|bgp|isis|vxlan|vrrp|ospf6|syslog|twamp)
```

В гайдах 6.5 и старше нет `syslog`/`twamp`/`alarms` в этой команде.

Примечание справочника про CMMD: Critical-логи на консоли соответствуют Alert-трапам, Alert-логи на консоли — Critical-трапам SNMP.

### 3.1. Syslog поверх SNMP: `logging snmp-traps`

Введено в **OcNOS 6.6.0**. Вместе с `snmp-server enable traps syslog` задаёт минимальную серьёзность сообщений, уходящих трапами:

```
logging snmp-traps (<0-7>)
no logging snmp-traps
```

`no` возвращает значение по умолчанию: **3 (error)**. Чем больше число, тем больше сообщений (включая менее серьёзные).

| Уровень | Имя в справочнике 6.6/7.0 |
|---|---|
| 0 | emergency |
| 1 | alert |
| 2 | critical |
| 3 | error (default) |
| 4 | oper-notify / debug-warn |
| 5 | oper-info / debug-notify — нумерация 5 и 6 в HTML-таблице параметров сверстана без цифр, восстановлено по порядку |
| 6 | debug-info (в примерах справочника: `logging snmp-traps 6`) |
| 7 | в таблице параметров имя не подписано; в конфигурационных примерах используют `logging snmp-traps 7`. Уточните `?` на устройстве |

В тех же примерах встречается `logging remote facility local4` как дополнительный фильтр facility. Для минимального набора достаточно `logging snmp-traps` и `snmp-server enable traps syslog`.

### 3.2. Alarms (7.0+): сначала FMS

1. Включить Fault Management System: `fault-management enable`
2. Проверка: `show fms status` (`FMS Status: Enabled`, `FMS Node Application Status: Up`)
3. `snmp-server enable traps alarms` и `commit`
4. Трапы alarms **не работают по SNMPv1** (нужны v2c или v3)
5. После даунгрейда OcNOS, по документации, включить alarm-трапы уже нельзя
6. В примере также ставят `logging level all 5` — это общий уровень логирования, не замена `logging snmp-traps`

---

## 4. Примеры точечного включения

Только link up/down, с именем интерфейса в varbind:

```
configure terminal
snmp-server enable traps link linkDown
snmp-server enable traps link linkUp
snmp-server enable traps link include-interface-name
commit
```

Только auth-failure:

```
configure terminal
snmp-server enable traps snmp authentication
commit
```

Протоколы, если они реально крутятся на коробке (иначе только шум на NMS):

```
configure terminal
snmp-server enable traps bgp
snmp-server enable traps ospf
snmp-server enable traps ospf6
snmp-server enable traps isis
snmp-server enable traps vrrp
snmp-server enable traps pim
commit
```

MPLS/L2VPN/L3VPN (где применимо):

```
configure terminal
snmp-server enable traps mpls
snmp-server enable traps mplsl3vpn
snmp-server enable traps pw
snmp-server enable traps pwdelete
snmp-server enable traps rsvp
commit
```

Syslog-трапы, только error и выше:

```
configure terminal
snmp-server enable traps syslog
logging snmp-traps 3
commit
```

Alarms (7.0+):

```
configure terminal
fault-management enable
snmp-server enable traps alarms
commit
```

Отключить один тип:

```
configure terminal
no snmp-server enable traps bgp
commit
```

---

## 5. Просмотр статуса

| Команда | Режим | Что показывает |
|---|---|---|
| `show snmp trap` | exec | Типы трапов, описание, Enabled yes/no. Есть в официальных примерах 6.6/7.0 (отдельная страница Command Reference с этого зеркала не загрузилась) |
| `show running-config snmp` | privileged exec | Фрагмент running-config по SNMP |
| `show snmp` | exec | Агент включён/выключен, contact, location, community, users, tcp-session |
| `show snmp host` | exec | Получатели: Host, Port, Version, Level, Type (trap/inform), SecName, VRF |
| `show snmp community` | exec | Community, группа, view, version |
| `show snmp group` | exec | Community/user, group, version, Read/Write/Notify view |
| `show snmp user` | exec | SNMPv3-пользователи: Auth, Priv, Group |
| `show snmp view` | exec | Список view |
| `show fms status` | exec | Нужен, если включены alarms |
| `show transaction current` | exec/config | Незакоммиченный candidate |

Фрагмент вывода `show snmp trap` (OcNOS 7.0, после включения только alarms):

```
#show snmp trap
-------------------------------------------------
Trap type     Description     Enabled
---------------------------------------------------
link          linkUp          no
link          linkDown        no
link          linkWithIfname  no
vxlan         notification    no
mpls          notification    no
mpls          pw              no
mpls          pw delete       no
mpls-l3vpn    notification    no
ospf          notification    no
ospf6         notification    no
isis          notification    no
snmp          authentication  no
mpls          rsvp            no
pim           notification    no
twamp         notification    no
syslog        notification    no
alarms        notification    yes
vrrp          notification    no
rib           notification    no
bgp           notification    no
```

Именно этот список — ориентир, какие типы ОС реально знает на 7.0 DC.

---

## 6. Важные ограничения

В справочниках OcNOS 6.6/7.0 (System Management, SNMP Command Reference; отдельно просмотрены BGP-команды Layer-3) **не найдено**:

- управления BGP-трапами per-neighbor — есть только глобальное `snmp-server enable traps bgp`;
- управления link-трапами per-interface (нет аналога Cisco `snmp trap link-status` в проверенных страницах) — только глобальные `snmp-server enable traps link linkUp` / `linkDown`.

То есть включили BGP — трапы пойдут по всем пирам; включили link — по всем интерфейсам. Фильтровать «лишние» события нужно на NMS (Zabbix и т.п.): по ifIndex/ifName, peer address, severity. Если на конкретной сборке B4COM/OcNOS под `?` в интерфейсном или BGP-neighbor режиме вдруг появится отдельная команда — она не из проверенных страниц 6.6/7.0.

Другие ограничения из документации:

| Ограничение | Источник |
|---|---|
| Не больше 8 SNMP-хостов | `snmp-server host` |
| SNMP-агент работает только в одном VRF | SNMP Config |
| GET/WALK — только в VRF агента; трапы могут уходить из другого `host-vrf` (6.6.0+) | Syslog / VRF examples |
| Alarm-трапы не поддерживаются в SNMPv1 | Alarm MIB 7.0 |
| Для alarms нужен `fault-management enable` | Alarm MIB 7.0 |
| `commit` не сохраняет startup — нужен `write` | commit / write |

---

## 7. Рекомендуемый минимальный набор

Цель: link up/down, authentication failure, syslog и (на 7.0) alarms — без протокол-шума BGP/OSPF/MPLS, если он не нужен.

### 7.0 ★ (links + alarms + auth + syslog)

```
configure terminal
!
! SNMP agent on management VRF
snmp-server view all .1 included vrf management
snmp-server community CHANGE_ME group network-operator vrf management
snmp-server host 192.0.2.10 traps version 2c CHANGE_ME udp-port 162 vrf management host-vrf management
snmp-server enable snmp vrf management
!
! Link traps + ifName in varbind
snmp-server enable traps link linkDown
snmp-server enable traps link linkUp
snmp-server enable traps link include-interface-name
!
! Auth failures (RFC 1157 authenticationFailure)
snmp-server enable traps snmp authentication
!
! Syslog-over-SNMP: error and above (default severity)
snmp-server enable traps syslog
logging snmp-traps 3
!
! Alarm MIB traps (OcNOS 7.0+; not SNMPv1)
fault-management enable
snmp-server enable traps alarms
!
commit
exit
write
```

Проверка: `show snmp trap` (нужные строки — yes), `show fms status`, `show snmp host`, `show running-config snmp`.

### 6.6 (без alarms)

Тот же блок, но **без** `fault-management enable` и `snmp-server enable traps alarms` — этих слов нет в формальном синтаксисе 6.6. Syslog уже доступен.

---

## 8. Диагностика

**На коммутаторе**

1. `show transaction current` — нет ли незакоммиченного куска.
2. `show snmp` — `SNMP Protocol: Enabled`.
3. `show snmp host` — правильные IP, порт 162, version, VRF.
4. `show snmp trap` — нужные типы yes.
5. Досягаемость NMS из management VRF:

```
# ping 192.0.2.10 vrf management
```

Синтаксис: `ping WORD ... (vrf (NAME|management)|)`. При необходимости: `source-ip`, `count`, `timeout`.

6. Сгенерировать link-трап (после commit): `interface <if>` → `shutdown` / `no shutdown` → `commit`. Для alarms в официальном примере делают то же самое и смотрят трап Alarm MIB (`1.3.6.1.4.1.36673.3400...`).

**На NMS (например, Linux с net-snmp)**

Слушать UDP/162 и смотреть, доходит ли пакет с адреса коммутатора:

```
# tcpdump -ni eth0 udp port 162
# snmptrapd -f -Lo
```

Если пакет не виден: маршрут/ACL/firewall до UDP/162, неверный `host-vrf`, агент выключен, типы трапов выключены, или конфиг не закоммичен. Если пакет есть, а Zabbix молчит — разбор и фильтры на стороне NMS (community/user, MIB, item/trigger).

Краткий SNMP GET для проверки, что агент отвечает в management VRF (с NMS, которой этот VRF доступен):

```
# snmpget -v2c -c CHANGE_ME 192.0.2.1 sysName.0
```

(`192.0.2.1` — адрес коммутатора; community тот же.) MIB файлы OcNOS: https://github.com/IPInfusion/OcNOS (ветка = версия OcNOS; префикс IPI — проприетарные MIB).

---

## 9. Источники

Проверено по страницам IP Infusion (OcNOS 6.6 / 7.0, DC и SP), ноябрь 2026:

- [snmp-server enable traps (OcNOS DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/snmp-server-enable-traps.htm)
- [snmp-server enable traps (OcNOS DC 6.6)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-6-6/Content/System-management/snmp-server-enable-traps.htm)
- [snmp-server enable traps (OcNOS SP 6.6)](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-6-6/Content/System-management/snmp-server-enable-traps.htm)
- [snmp-server enable snmp (DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/snmp-server-enable-snmp.htm)
- [snmp-server community (DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/snmp-server-community.htm)
- [snmp-server view (DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/snmp-server-view.htm)
- [snmp-server user (DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/snmp-server-user.htm)
- [snmp-server host (SP 6.6)](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-6-6/Content/snmp-server_host.htm)
- [SNMP Configuration (SP 7.0)](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-7.0/Content/System-management/snmp-config.htm)
- [SYSLOG messages over SNMP traps (DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/syslog-msgs-snmp-traps.htm) — в тексте примера опечатка `snmpserver` без дефиса; верная команда: `snmp-server enable traps syslog`
- [logging snmp-traps (DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/Common/syslog-cmds/logging-snmp-traps.htm)
- [SNMP Configuration for Alarm MIB Support (DC 7.0)](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/snmp-configuration-for-alarm-mib-support.htm)
- [show snmp](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/show-snmp.htm), [show snmp community](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/show-snmp-community.htm), [show snmp host](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/show-snmp-host.htm), [show snmp group](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/show-snmp-group.htm), [show snmp user](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/show-snmp-user.htm), [show snmp view](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/show-snmp-view.htm), [show running-config snmp](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-7.0/Content/System-management/show-running-config-snmp.htm)
- [commit](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-6-6/Content/Common/cml-cmds/commit.htm), [abort transaction](https://documentation.ipinfusion.com/ocnos-dc-sys-mgmt-6-6/Content/Common/cml-cmds/abort-transaction.htm), [show transaction current](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-6-6/Content/Common/cml-cmds/show-transaction-current.htm), [Transaction-based CLI](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-6-6/Content/Global-topics/Preface-CLI/transx-based-cmd-line-interf.htm)
- [write](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-6-6/Content/System-management/write.htm)
- [ping](https://documentation.ipinfusion.com/ocnos-sp-sys-mgmt-7.0/Content/System-management/ping.htm)
- MIB: [github.com/IPInfusion/OcNOS](https://github.com/IPInfusion/OcNOS)

Старые зеркала той же команды (менее полный синтаксис, без syslog/twamp/alarms/pim): [docs.ipinfusion.com SNMP Commands (SP)](https://docs.ipinfusion.com/service-provider/OcNOS-SP/Sysman_Cmds/SNMP_Commands.html), [SNMP Config 6.5](https://docs.ipinfusion.com/service-provider-6.5/OcNOS_SP/SNMP-Config/SNMP_Config.html).
