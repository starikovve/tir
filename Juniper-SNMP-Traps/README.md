# SNMP-трапы на Juniper Junos OS (EX / QFX / SRX / MX)

Синтаксис сверен с актуальной Juniper TechLibrary (Junos OS Network Management + CLI Reference), ноябрь 2026. На конкретной коробке всегда проверяйте `?` (набор категорий и алгоритмов SNMPv3 может отличаться по платформе и релизу).

Плейсхолдеры: `192.0.2.10` (NMS), `CHANGE_ME`, `AUTH_CHANGE_ME`, `PRIV_CHANGE_ME`. Имя trap-group в пакете уходит как community (varbind) — его тоже не оставляйте «боевым» секретом в примерах из сети.

Junos использует candidate-конфиг: изменения применяются только после `commit` (не путать с транзакционным cmlsh OcNOS: здесь нет `abort transaction`, откат candidate — `rollback`).

---

## 1. Базовая настройка (SNMPv2c)

Минимум для отправки трапов: community (для опроса; для самих трапов community в пакете = **имя trap-group**) и хотя бы одна `trap-group` с `targets`. Без trap-group трапы не уходят.

### 1.1. Community и ограничение клиентов

```
set snmp community CHANGE_ME authorization read-only
set snmp community CHANGE_ME clients 192.0.2.10/32
```

- `authorization`: `read-only` (Get / GetNext / GetBulk; **default**) или `read-write` (включая Set; нужен view). На QFX3000 QFabric `read-write` не поддерживается.
- Если `community` нет, все SNMP-запросы отвергаются.
- Если `clients` нет, этим community могут пользоваться **все** клиенты. `restrict` запрещает указанный адрес: `set snmp community CHANGE_ME clients 198.51.100.0/24 restrict`. Указывайте адрес, не hostname; на практике часто задают префикс.

Опционально: `set snmp location "DC1"`, `set snmp contact "noc@example.invalid"`.

### 1.2. Trap-group: version, targets, destination-port, categories

```
set snmp trap-group NMS-V2 version v2
set snmp trap-group NMS-V2 destination-port 162
set snmp trap-group NMS-V2 targets 192.0.2.10
set snmp trap-group NMS-V2 categories authentication
set snmp trap-group NMS-V2 categories chassis
set snmp trap-group NMS-V2 categories link
set snmp trap-group NMS-V2 categories startup
```

| Параметр | Значение | Заметки из документации |
|---|---|---|
| `trap-group NAME` | имя группы | Обязательна хотя бы одна группа. Имя попадает в трап как community. Не используйте зарезервированное `__juniper_internal_trap_group__` |
| `targets` | IPv4 или IPv6, **не** hostname | Хотя бы один получатель |
| `version` | `v1` \| `v2` \| `all` | **Default — `all`**: на каждое событие уходят и v1, и v2. Для NMS обычно явно ставьте `v2` |
| `destination-port` | UDP-порт | Default **162** |
| `categories` | типы трапов | Если опустить — уходят **все** категории, **кроме** `timing-events` (её нужно включать явно) |
| `routing-instance` | имя instance | Все targets группы используют этот instance |

Несколько targets в одной группе допустимы (IPv4 и IPv6 вместе):

```
set snmp trap-group NMS-V2 targets 192.0.2.10
set snmp trap-group NMS-V2 targets 2001:db8::10
```

### 1.3. Routing-instance и `mgmt_junos`

У `[edit snmp trap-group NAME]` есть `routing-instance`: через него уходят трапы ко всем targets группы (Junos 8.3+).

Если включён выделенный management VRF (**Junos 17.3R1+**):

```
set system management-instance
```

Имя instance зарезервировано и жёстко задано как `mgmt_junos` (обычно `fxp0` / `em0`). Трапы в сторону NMS в management-сети:

```
set snmp trap-group NMS-V2 routing-instance mgmt_junos
```

Без `management-instance` трапы по умолчанию идут из inet.0 (если `routing-instance` не задан). Для SNMPv3 то же самое задаётся на `target-address` (`routing-instance`).

В разделе trap-options документация замечает, что SNMP можно ассоциировать только с master routing instance; доставка до NMS при этом настраивается именно `routing-instance` у trap-group / v3 target-address.

---

## 2. `trap-options`

Действуют, только если настроена хотя бы одна trap-group. Default: опции выключены, source address = адрес исходящего интерфейса.

```
set snmp trap-options source-address lo0
set snmp trap-options agent-address outgoing-interface
set snmp trap-options enterprise-oid
```

| Statement | Что делает |
|---|---|
| `source-address lo0` | Source всех трапов = **наименьший** адрес, настроенный на `lo0`. Это ключевое слово `lo0`, а не юнит `lo0.0`. Альтернатива — конкретный IPv4, который уже висит на интерфейсе устройства. В гайде SNMP Traps также допускают IPv6 |
| `source-address 192.0.2.1` | Фиксированный IP (должен быть настроен на интерфейсе). Трап отправится, только если source — валидный настроенный адрес |
| `agent-address outgoing-interface` | Только SNMPv1: поле agent-address = IP исходящего интерфейса (RFC 1157). Иных значений нет |
| `enterprise-oid` | Добавить `snmpTrapEnterprise` и в **стандартные** трапы (по умолчанию объект есть только в enterprise-specific). С Junos 10.0 |
| `logical-system NAME` | В гайде SNMP Traps — задать logical-system как source |
| `routing-instance NAME` | В том же гайде — задать routing-instance как source (это не то же самое, что `routing-instance` у trap-group) |
| `context-oid` | Junos 17.1+: для трапов из не-default logical-system / routing-instance добавить context OID в varbind |

Типичный вариант для стабильной идентификации устройства на NMS: loopback как source (`source-address lo0`) плюс адрес на `lo0.0`.

---

## 3. Категории `trap-group categories`

Источник списка: актуальный CLI Reference `categories` (не устаревшая короткая страница QFX, где набор был неполным) и тема [SNMP Traps](https://www.juniper.net/documentation/us/en/software/junos/network-mgmt/topics/topic-map/snmp-traps.html).

**Default:** если `categories` не указаны, в группу входят все типы, **кроме** `timing-events`.

| Категория | Описание | Платформа / замечание |
|---|---|---|
| `authentication` | Authentication failures (неверный community и т.п.) | все |
| `chassis` | Шасси и среда (питание, температура, FRU) | все |
| `chassis-cluster` | Уведомления кластера | **Только SRX Series** (явно в CLI Reference) |
| `configuration` | Изменения конфигурации | все |
| `link` | link up/down; также DS-3/DS-1 line status, IPv6 interface state, Passive Monitoring PIC overload | все; без этой категории нет link-трапов, даже если на интерфейсе стоит `traps` |
| `otn-alarms` | OTN-аварии (есть подкатегории) | платформы с OTN (типично MX/PTX/ACX). Если подкатегории не указать — по аналогии с SONET ожидаются все типы; **перечень подкатегорий в текущих HTML-страницах categories / SNMP Traps не перечислен** — смотрите `set snmp trap-group NAME categories otn-alarms ?` |
| `remote-operations` | Remote operations | все |
| `rmon-alarm` | RMON rising/falling alarms | все |
| `routing` | Протоколы маршрутизации (BGP и др.) — **глобальная** категория, не per-neighbor | все |
| `services` | Circuit/connection up/down, CPU exceeded, alarms, status changes | В CLI Reference не помечена как MX-only; на практике нужна там, где есть services/circuit |
| `sonet-alarms` | SONET/SDH alarms (подкатегории — ниже) | платформы с SONET/SDH. Без подкатегорий — **все** SONET-типы |
| `startup` | Cold start и warm start | все |
| `timing-events` | Timing events/defects | **Не входит в default**, включать явно |
| `vrrp-events` | VRRP: смена primary, ошибки аутентификации | все |

Категории `dot3oam-events` в актуальном CLI Reference `categories` и в теме SNMP Traps **нет** — в рабочие списки не включаем.

### Подкатегории `sonet-alarms`

Если указать конкретные — уходят только они; если не указать — все:

| Подкатегория | Описание (TechLibrary) |
|---|---|
| `loss-of-light` | Loss of light |
| `pll-lock` | PLL lock |
| `loss-of-frame` | Loss of frame |
| `loss-of-signal` | Loss of signal |
| `severely-errored-frame` | Severely errored frame |
| `line-ais` | Line AIS |
| `path-ais` | Path AIS |
| `loss-of-pointer` | Loss of pointer |
| `ber-defect` | SONET/SDH BER defect |
| `ber-fault` | SONET/SDH BER fault |
| `line-remote-defect-indication` | Line RDI |
| `path-remote-defect-indication` | Path RDI |
| `remote-error-indication` | Remote error indication |
| `unequipped` | Unequipped |
| `path-mismatch` | Path mismatch |
| `loss-of-cell` | Loss of cell delineation |
| `vt-ais` | VT AIS |
| `vt-loss-of-pointer` | VT loss of pointer |
| `vt-remote-defect-indication` | VT RDI |
| `vt-unequipped` | VT unequipped |
| `vt-label-mismatch` | VT label mismatch |
| `vt-loss-of-cell` | VT loss of cell delineation |

Пример (только LOS и LOF):

```
set snmp trap-group NMS-V2 categories sonet-alarms loss-of-signal
set snmp trap-group NMS-V2 categories sonet-alarms loss-of-frame
```

---

## 4. Per-interface контроль: `traps` / `no-traps`

В отличие от OcNOS/B4COM (только глобальное `snmp-server enable traps link ...`), в Junos link-трапы можно включать и выключать **на интерфейсе**.

**Default (и физический, и логический интерфейс):** уведомления SNMP **отправляются**, когда меняется состояние интерфейса или соединения. Это не отменяет необходимость категории `link` в trap-group.

Иерархия (CLI Reference `traps`, в т.ч. страница Junos 13.2 с полным hierarchy level; формулировка default — в актуальных темах Physical / Logical Interfaces):

- `[edit interfaces INTERFACE]` — физический
- `[edit interfaces INTERFACE unit UNIT]` — логический
- `[edit interfaces interface-range NAME]` — диапазон
- `[edit logical-systems LS interfaces INTERFACE unit UNIT]`

```
# явно включить (обычно не нужно — и так default)
set interfaces ge-0/0/0 traps
set interfaces ge-0/0/0 unit 0 traps

# отключить link-трапы на физическом порту (access/unused)
set interfaces ge-0/0/23 no-traps

# отключить только на логическом юните (физический при этом может слать свои)
set interfaces ge-0/0/0 unit 100 no-traps

# диапазон
set interfaces interface-range ACCESS member-range ge-0/0/10 to ge-0/0/23
set interfaces interface-range ACCESS no-traps
```

На MX enhanced subscriber management `traps` в dynamic-profiles работает, только если сначала включён `interface-mib`; Juniper не рекомендует включать уведомления на всех динамических subscriber-интерфейсах.

Итого фильтр link-трапов двухуровневый: категория `link` в trap-group **и** `traps`/`no-traps` на интерфейсе.

---

## 5. SNMPv3 (кратко)

Трапы/informs v3 задаются не через `trap-group`, а через `notify` + `target-address` + `target-parameters`. Права на отправку — в VACM (`security-to-group` + `access` с `notify-view`). Client-list для ограничения опроса в v3 **не поддерживается** (в отличие от v2c); при необходимости фильтруют lo0 firewall.

Сначала задайте local engine ID — по нему считаются ключи USM:

```
set snmp engine-id use-mac-address
```

(варианты: `use-default-ip-address` или `local <hex-id>`).

Полный пример (auth SHA + priv AES128, notify type trap):

```
# views
set snmp view ALL oid .1 include

# USM user
set snmp v3 usm local-engine user nmsv3 authentication-sha authentication-password AUTH_CHANGE_ME
set snmp v3 usm local-engine user nmsv3 privacy-aes128 privacy-password PRIV_CHANGE_ME

# VACM: user -> group, group access (notify/read)
set snmp v3 vacm security-to-group security-model usm security-name nmsv3 group NMS-GROUP
set snmp v3 vacm access group NMS-GROUP default-context-prefix security-model usm security-level privacy context-match exact
set snmp v3 vacm access group NMS-GROUP default-context-prefix security-model usm security-level privacy read-view ALL
set snmp v3 vacm access group NMS-GROUP default-context-prefix security-model usm security-level privacy notify-view ALL

# notify + filter + target
set snmp v3 notify NMS-NOTIFY type trap tag nms-tag
set snmp v3 notify-filter NMS-FILTER oid .1 include
set snmp v3 target-parameters NMS-TP parameters message-processing-model v3
set snmp v3 target-parameters NMS-TP parameters security-model usm
set snmp v3 target-parameters NMS-TP parameters security-level privacy
set snmp v3 target-parameters NMS-TP parameters security-name nmsv3
set snmp v3 target-parameters NMS-TP notify-filter NMS-FILTER
set snmp v3 target-address NMS-TA address 192.0.2.10
set snmp v3 target-address NMS-TA port 162
set snmp v3 target-address NMS-TA tag-list nms-tag
set snmp v3 target-address NMS-TA target-parameters NMS-TP
set snmp v3 target-address NMS-TA routing-instance mgmt_junos
```

- `notify type` — `trap` (без подтверждения) или `inform` (с подтверждением).
- `tag` у notify должен входить в `tag-list` у target-address (несколько тегов — в кавычках через пробел).
- `security-level`: для USM — `authentication` или `privacy`; для v1/v2c — `none`.
- Default UDP-порт target-address — 162. `address-mask` обязателен, если target-address используется ещё и как ограничение community для v1/v2c.
- Пароль после commit превращается в ключ; «голый» пароль из конфига можно убрать, ключ останется.
- На одного пользователя — один тип privacy.

---

## 6. `event-options` и `then raise-trap`

Любое syslog-событие, для которого нет «родного» SNMP-трапа, можно превратить в трап. Политика:

```
[edit event-options policy POLICY]
    events <event-id>;
    then {
        raise-trap;
    }
```

Официальный пример из темы SNMP Traps (событие `ui_mgd_terminate`, Junos 8.1+):

```
set event-options policy RAISE-UI-TERM events ui_mgd_terminate
set event-options policy RAISE-UI-TERM then raise-trap
```

Как искать имена событий:

```
help syslog ?
help syslog UI_MGD_TERMINATE
```

`help syslog ?` перечисляет события; `help syslog <ID>` показывает текст и атрибуты (в `<угловых скобках>`). Часть сообщений не видна в `set event-options policy NAME events ?` — их всё равно можно указать, см. «Use Nonstandard System Log Messages to Trigger Event Policies». Регистр в официальном примере — нижний (`ui_mgd_terminate`); в `help syslog` ID обычно в верхнем. Проверяйте на своей версии.

Фильтр по атрибуту (ищите точные имена в `help syslog`):

```
set event-options policy P events EVENT_ID
set event-options policy P attributes-match EVENT_ID.attribute-name equals value
set event-options policy P then raise-trap
```

Трап уйдёт тем же получателям, что настроены в trap-group / SNMPv3 notify.

---

## 7. Проверка и commit

### Commit (candidate → running)

```
show | compare
commit check
commit comment "snmp traps minimal"
```

| Команда | Назначение |
|---|---|
| `show \| compare` | Diff candidate и активной конфигурации |
| `commit check` | Только проверка синтаксиса, без активации |
| `commit` | Проверка + активация |
| `commit confirmed` / `commit confirmed 5` | Временный commit; подтвердить повторным `commit` или `commit check`. Таймаут **в минутах**, default **10**. Иначе автоматический rollback |
| `rollback` / `rollback 0` | Загрузить последнюю закоммиченную конфигурацию в candidate (сбросить незакоммиченное) |
| `rollback 1` | Предыдущая закоммиченная (до 49 копий) |
| `show system commit` | История commit и отложенный rollback после `commit confirmed` |

### Операционные команды SNMP

```
show configuration snmp
show snmp statistics
show snmp mib walk system
show snmp mib get sysName.0
show snmp v3
```

- `show snmp statistics` — счётчики, в т.ч. Output `Traps` (`snmpOutTraps`), Input `Bad community names`.
- `show snmp mib walk` / `get` / `get-next` — локальные значения MIB (OID или имя subtree, например `system`, `interfaces`).
- `show snmp v3` — пользователи, группы, engine.

Тестовая генерация трапа (**Junos 8.2+**):

```
request snmp spoof-trap ?
request snmp spoof-trap dummy
request snmp spoof-trap linkDown variable-bindings "ifIndex[14]=14, ifAdminStatus[14]=1, ifOperStatus[14]=2"
```

`dummy` (или иное несуществующее имя) печатает список доступных trap-имён. Объекты без указанных instance/value подставятся автоматически. Альтернатива для `authentication`: запрос с неверным community — должен уйти authentication-трап.

Захват на исходящем интерфейсе (fxp0/em0/me0 — по платформе):

```
monitor traffic interface fxp0 matching "udp port 162"
```

(в теме SNMP Traps для проверки как раз рекомендуют `monitor traffic`.)

---

## 8. Рекомендуемый минимальный набор

link + authentication + chassis + startup. Версия явно `v2` (чтобы не слать ещё и v1 из-за default `all`). Source — `lo0`. Clients ограничены NMS.

### 8.1. SNMPv2c

```
set snmp trap-options source-address lo0

set snmp community CHANGE_ME authorization read-only
set snmp community CHANGE_ME clients 192.0.2.10/32

set snmp trap-group NMS-V2 version v2
set snmp trap-group NMS-V2 destination-port 162
set snmp trap-group NMS-V2 targets 192.0.2.10
set snmp trap-group NMS-V2 categories authentication
set snmp trap-group NMS-V2 categories chassis
set snmp trap-group NMS-V2 categories link
set snmp trap-group NMS-V2 categories startup
# set snmp trap-group NMS-V2 routing-instance mgmt_junos

# при необходимости убрать шум с access-портов:
# set interfaces interface-range ACCESS member-range ge-0/0/10 to ge-0/0/23
# set interfaces interface-range ACCESS no-traps

show | compare
commit check
commit comment "minimal snmpv2c traps"
```

Иерархический вид того же:

```
snmp {
    trap-options {
        source-address lo0;
    }
    community CHANGE_ME {
        authorization read-only;
        clients {
            192.0.2.10/32;
        }
    }
    trap-group NMS-V2 {
        version v2;
        destination-port 162;
        categories {
            authentication;
            chassis;
            link;
            startup;
        }
        targets {
            192.0.2.10;
        }
    }
}
```

На SRX в кластере добавьте `categories chassis-cluster`. На коробке с OTN/SONET — соответствующие категории, только если они нужны NMS.

### 8.2. Опционально SNMPv3

Блок из раздела 5 (user `nmsv3`, privacy, target 192.0.2.10). Категории v2c-группы на v3 notify не переносятся автоматически: v3 определяет *куда* и *как* слать, а набор событий для «классических» категорий по-прежнему задаётся trap-group, либо фильтруется `notify-filter` по OID. На практике часто оставляют trap-group для классификации и добавляют v3 target, либо переходят полностью на v3 notify + filter. Уточняйте поведение совмещения trap-group и v3 notify на своём релизе (в документации это разведены как два механизма доставки).

---

## 9. Junos vs OcNOS / B4COM

Сравнение с гайдом репозитория `B4COM-SNMP-Traps/README.md`.

| Тема | Junos OS | OcNOS / B4COM |
|---|---|---|
| Модель включения | `trap-group` + **категории** (`link`, `routing`, `chassis`…) | Глобальные ключевые слова `snmp-server enable traps <тип>` (`link linkUp`, `bgp`, `ospf`…) |
| Link-трапы | Глобальная категория `link` **и** per-interface `traps` / `no-traps` (default: и физические, и логические интерфейсы шлют) | Только глобально; per-interface в документации OcNOS 6.6/7.0 не найден |
| BGP / routing | Категория `routing` — тоже глобально, не per-neighbor | `snmp-server enable traps bgp` — только глобально |
| Syslog → трап | `event-options policy … then raise-trap` (любое syslog-событие) | `snmp-server enable traps syslog` + `logging snmp-traps <0-7>` (порог серьёзности, OcNOS 6.6+) |
| Management VRF | `set system management-instance` → instance **`mgmt_junos`** (17.3R1+); у группы: `routing-instance mgmt_junos` | `snmp-server enable snmp vrf management` и `host … vrf management host-vrf …` (host-vrf с 6.6.0) |
| Source address трапа | `trap-options source-address lo0` \| IP | В проверенных страницах OcNOS отдельного аналога `source-address lo0` нет |
| Commit | Candidate: `show \| compare`, `commit check`, `commit`, `commit confirmed N` (минуты), `rollback` | cmlsh: `show transaction current`, `commit`, `abort transaction`; отдельно `write` в startup |
| Получатели | `trap-group targets` (имя группы = community в трапе). Для v3 — `target-address` | `snmp-server host …`, максимум 8 хостов |
| Версия трапа | `version v1\|v2\|all` (**default all = v1 и v2 сразу**) | `traps version 1\|2c` или v3 на каждом host |
| SNMPv3 | USM + VACM + notify / target-address / target-parameters / notify-filter | `snmp-server user` + `snmp-server host … version 3 {noauth\|auth\|priv}` |
| Проверка | `show snmp statistics`, `request snmp spoof-trap`, `monitor traffic … matching "udp port 162"` | `show snmp trap`, `show snmp host`; отдельного spoof-trap в гайде OcNOS нет |

---

## 10. Источники

Проверено по Juniper TechLibrary, ноябрь 2026:

- [SNMP Traps](https://www.juniper.net/documentation/us/en/software/junos/network-mgmt/topics/topic-map/snmp-traps.html) — категории (включая подкатегории SONET), trap-group, trap-options, raise-trap, spoof/monitor
- [categories (CLI Reference)](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/categories-edit-snmp.html) — полный список категорий, default (все кроме `timing-events`), `chassis-cluster` = SRX
- [trap-group](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/trap-group-edit-snmp.html)
- [version](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/version-edit-snmp.html), [destination-port](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/destination-port-edit-snmp.html), [routing-instance (SNMP)](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/routing-instance-edit-snmp.html)
- [community](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/community-edit-snmp.html), [authorization](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/authorization-edit-snmp.html), [clients](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/clients-edit-snmp.html)
- [trap-options](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/trap-options-edit-snmp.html), [source-address](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/source-address-edit-snmp.html), [agent-address](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/agent-address-edit-snmp.html), [enterprise-oid](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/enterprise-oid-edit-snmp-trap-options.html)
- [traps / no-traps (interfaces)](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/traps-edit-interfaces.html), иерархия в т.ч. [Junos 13.2 traps](https://www.juniper.net/documentation/en_US/junos13.2/topics/reference/configuration-statement/traps-edit-interfaces.html)
- Default и синтаксис: [Physical Interfaces — Enable SNMP Notifications](https://www.juniper.net/documentation/us/en/software/junos/interfaces-fundamentals/topics/topic-map/physical-interface-properties.html), [Logical Interfaces](https://www.juniper.net/documentation/us/en/software/junos/interfaces-ethernet-switches/topics/topic-map/switches-interface-logical-transformed.html)
- [Configure SNMPv3](https://www.juniper.net/documentation/us/en/software/junos/network-mgmt/topics/topic-map/configure-snmpv3.html), [SNMPv3 Traps](https://www.juniper.net/documentation/us/en/software/junos/network-mgmt/topics/topic-map/snmpv3-traps.html)
- [raise-trap](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/raise-trap-edit-event-options.html), [Event Policies Overview](https://www.juniper.net/documentation/us/en/software/junos/automation-scripting/topics/concept/junos-script-automation-event-notifications-and-policy-overview.html) (`help syslog`)
- [request snmp spoof-trap](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/command/request-snmp-spoof-traps-command.html)
- [show snmp statistics](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/command/show-snmp-statistics.html), [show snmp mib](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/command/show-snmp-mib.html), [show snmp v3](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/command/show-snmp-v3.html)
- [management-instance](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/management-instance-edit-system.html)
- [Commit the Configuration](https://www.juniper.net/documentation/us/en/software/junos/cli/topics/topic-map/junos-configuration-commit.html)
- Сравнение: `/workspace/b4com-snmp/B4COM-SNMP-Traps/README.md`
