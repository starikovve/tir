# FortiGate с нуля: понятный гайд

> Адреса в примерах условные (192.0.2.x, 198.51.100.x, 203.0.113.x, 10.x). Ключи и пароли — заглушки `CHANGE_ME`.
> Синтаксис CLI дан для FortiOS 7.x; на вашей версии сверяйтесь с [docs.fortinet.com](https://docs.fortinet.com).
> Метки версий: **«7.0+»** — с этой версии и новее, **«до 6.4»** — только в старых, **★** — актуально для 7.2 / 7.4 / 7.6.

## 1. Что такое FortiGate и зачем он нужен

FortiGate — это **NGFW** (Next-Generation Firewall). Обычный файрвол — охранник, который смотрит только на «адрес и номер двери» (IP и порт). NGFW — охранник, который ещё и открывает посылку и проверяет, что внутри.

| Функция | Что делает | Аналогия |
|---|---|---|
| Firewall | Пропускает или блокирует трафик по правилам | Турникет на входе |
| IPS | Ищет атаки по сигнатурам и аномалиям | Металлоискатель |
| Antivirus | Проверяет файлы на вирусы | Рентген багажа |
| Web/DNS filter | Блокирует сайты по категориям | Список запрещённых мест |
| Application control | Распознаёт приложения (Telegram, YouTube…) | Охранник, узнающий людей в лицо |
| VPN | Шифрованные туннели между офисами и для удалённых сотрудников | Бронированный фургон |
| FortiSandbox | Подозрительный файл запускается в изолированной «песочнице» (отдельное устройство или облако) | Комната, где посылку вскрывают сапёры |

**UTM / Security profiles** — набор этих проверок (AV, IPS, Web filter, App control, DNS filter…). Профили создаются отдельно и **подключаются к firewall-политике**: «этот трафик пропустить, но проверить антивирусом и IPS».

## 2. Архитектура FortiOS

**FortiGate = железо + FortiOS.** Железо даёт порты и ускорители (ASIC: NP — сетевой процессор для быстрой пересылки, CP — для шифрования и проверки контента). FortiOS — операционная система, в которой живут политики, маршрутизация, VPN и профили.

- Управление: GUI (HTTPS), CLI (SSH/консоль), API, FortiManager.
- Конфигурация — дерево `config … edit … set … next … end`:

```
config system interface      # войти в раздел
    edit "port1"              # выбрать объект (или создать)
        set ip 192.0.2.1 255.255.255.0
        set allowaccess ping https ssh
    next                      # сохранить объект, остаться в разделе
end                           # сохранить и выйти из раздела
```

Изменения применяются сразу по `next`/`end` (отдельного `commit` нет).

## 3. VDOM (Virtual Domains)

**Зачем.** VDOM — это как несколько независимых файрволов в одной коробке: у каждого свои интерфейсы, политики, маршруты, VPN и админы. Используют для разделения клиентов, отделов или сред (prod/test).

**Включение** (выкидывает из сессии, но без перезагрузки; текущая конфигурация уходит в VDOM `root`):

```
config system global
    set vdom-mode multi-vdom      # 6.4+ ★ ; до 6.4: set vdom-admin enable
end
```

**Создание и переключение:**

```
config vdom
    edit SALES        # создать/войти в VDOM SALES
        show system interface
    next
end

config global          # глобальные настройки (интерфейсы, HA, админы)
    config system interface
        edit port3
            set vdom SALES   # отдать порт VDOM-у
        next
    end
end
```

**Связь между VDOM — vdom-link.** VDOM изолированы. Чтобы трафик ходил между ними, создают виртуальный «кабель» vdom-link: у него два конца `<имя>0` и `<имя>1`.

```
config global
    config system vdom-link
        edit "vl-sales"          # имя не должно совпадать с именем VDOM
        next
    end
    config system interface
        edit "vl-sales0"
            set vdom SALES
            set ip 10.255.0.2 255.255.255.252
        next
        edit "vl-sales1"
            set vdom root
            set ip 10.255.0.1 255.255.255.252
        next
    end
end
```

Дальше всё как между двумя отдельными файрволами: **в каждом VDOM** нужен маршрут через свой конец линка и **политика**, разрешающая трафик с/на интерфейс vdom-link. Типичная схема — SALES выходит в интернет через root: в SALES `static 0.0.0.0/0 → vl-sales0`, в root маршрут до сети SALES через `vl-sales1` и политика `vl-sales1 → wan1` с NAT.

## 4. Интерфейсы

| Тип | Зачем | Пример |
|---|---|---|
| Physical | Обычный порт | `port1`, `wan1` |
| VLAN | Подинтерфейс с тегом 802.1Q на физическом | см. ниже |
| Loopback | Всегда «up», для управления, BGP, VPN | `type loopback` |
| Aggregate | LACP-агрегация портов (LAG) | `type aggregate` |
| SD-WAN | Несколько WAN как один логический с правилами выбора канала | `config system sdwan` |

```
config system interface
    edit "vlan10"
        set vdom root
        set interface "port2"
        set vlanid 10
        set ip 10.10.10.1 255.255.255.0
        set allowaccess ping
    next
    edit "lo-mgmt"
        set vdom root
        set type loopback
        set ip 10.0.0.1 255.255.255.255
    next
    edit "agg1"
        set vdom root
        set type aggregate
        set member "port5" "port6"
        set lacp-mode active
    next
end
```

SD-WAN (кратко, синтаксис `config system sdwan` — **6.4+ ★**; до 6.4 — `config system virtual-wan-link`): провайдеры добавляются как члены SD-WAN, а правила выбирают канал по задержке/потерям (performance SLA).

```
config system sdwan
    set status enable
    config members
        edit 1
            set interface "wan1"
            set gateway 198.51.100.1
        next
        edit 2
            set interface "wan2"
            set gateway 203.0.113.1
        next
    end
end
```

## 5. Зоны и firewall-политики: как идёт трафик

**Зона** — группа интерфейсов, чтобы писать одну политику на несколько интерфейсов (например, все VLAN пользователей).

```
config system zone
    edit "LAN"
        set interface "vlan10" "vlan20"
        set intrazone deny       # трафик между VLAN внутри зоны тоже через политики
    next
end
```

**Путь пакета (упрощённо):**

```
вход (srcintf/zone) → маршрут: определяется dstintf → поиск политики (srcintf + dstintf + адреса + сервис + расписание)
   → action accept/deny → security profiles (AV, IPS, Web…) → NAT → выход
```

- Политика матчится по паре **srcintf → dstintf** (интерфейсы или зоны), затем по адресам, пользователям и сервисам.
- Политики проверяются **сверху вниз**, срабатывает **первая** подходящая. Порядок важен.
- В конце — **implicit deny** (неявный запрет всего).
- Политики **stateful**: обратный трафик сессии разрешается автоматически.

```
config firewall policy
    edit 10
        set name "LAN-to-Internet"
        set srcintf "LAN"
        set dstintf "wan1"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set service "HTTP" "HTTPS" "DNS"
        set schedule "always"
        set utm-status enable
        set av-profile "default"
        set ips-sensor "default"
        set webfilter-profile "default"
        set ssl-ssh-profile "certificate-inspection"
        set nat enable
        set logtraffic all
    next
end
```

## 6. NAT

**SNAT** (подмена адреса источника, «выход в интернет»): в политике `set nat enable` — адрес меняется на IP выходного интерфейса. Нужен другой адрес или пул — **IP pool**:

```
config firewall ippool
    edit "pool-out"
        set startip 203.0.113.10
        set endip 203.0.113.10
        set type overload        # PAT: много внутренних → один внешний
    next
end
config firewall policy
    edit 10
        set ippool enable
        set poolname "pool-out"
    next
end
```

**DNAT** (публикация сервера наружу) — **VIP** (virtual IP) + политика, где VIP стоит в `dstaddr`:

```
config firewall vip
    edit "web-srv"
        set extintf "wan1"
        set extip 203.0.113.20
        set mappedip "10.10.20.10"
        set portforward enable
        set extport 443
        set mappedport 443
    next
end
config firewall policy
    edit 20
        set name "Inet-to-Web"
        set srcintf "wan1"
        set dstintf "vlan20"
        set srcaddr "all"
        set dstaddr "web-srv"
        set action accept
        set service "HTTPS"
        set schedule "always"
        set ips-sensor "default"
    next
end
```

**Central NAT** (6.0+) — альтернативный режим (`config system settings` → `set central-nat enable`): SNAT задаётся отдельной таблицей `config firewall central-snat-map`, а DNAT — VIP, которые применяются до политик. Удобно при большом количестве правил; включать на рабочей системе осторожно — меняется логика.

## 7. Маршрутизация

**Статика:**

```
config router static
    edit 1
        set dst 0.0.0.0 0.0.0.0
        set gateway 198.51.100.1
        set device "wan1"
    next
    edit 2
        set dst 10.20.0.0 255.255.0.0
        set gateway 10.10.10.254
        set device "vlan10"
    next
end
```

**OSPF (кратко):**

```
config router ospf
    set router-id 10.0.0.1
    config area
        edit 0.0.0.0
        next
    end
    config network
        edit 1
            set prefix 10.10.10.0 255.255.255.0
            set area 0.0.0.0
        next
    end
end
```

**BGP (кратко):**

```
config router bgp
    set as 65001
    set router-id 10.0.0.1
    config neighbor
        edit "198.51.100.2"
            set remote-as 65002
        next
    end
    config network
        edit 1
            set prefix 203.0.113.0 255.255.255.0
        next
    end
end
```

Проверка: `get router info routing-table all`, `get router info ospf neighbor`, `get router info bgp summary`.

## 8. VPN

### IPsec site-to-site (route-based)

Четыре шага: **phase1** (кто с кем и как договариваемся), **phase2** (какой трафик шифруем), **маршрут** в туннель, **политики** в обе стороны.

```
config vpn ipsec phase1-interface
    edit "to-branch"
        set interface "wan1"
        set ike-version 2            # IKEv2 рекомендуется для 7.x ★
        set peertype any
        set net-device disable
        set proposal aes256-sha256
        set dhgrp 14
        set remote-gw 198.51.100.50
        set psksecret CHANGE_ME
    next
end
config vpn ipsec phase2-interface
    edit "to-branch-p2"
        set phase1name "to-branch"
        set proposal aes256-sha256
        set dhgrp 14
        set src-subnet 10.10.0.0 255.255.0.0
        set dst-subnet 10.20.0.0 255.255.0.0
    next
end
config router static
    edit 10
        set dst 10.20.0.0 255.255.0.0
        set device "to-branch"
    next
end
config firewall policy
    edit 30
        set name "LAN-to-Branch"
        set srcintf "LAN"
        set dstintf "to-branch"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set service "ALL"
        set schedule "always"
    next
    edit 31
        set name "Branch-to-LAN"
        set srcintf "to-branch"
        set dstintf "LAN"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set service "ALL"
        set schedule "always"
    next
end
```

Параметры phase1/phase2 (proposal, DH, PSK, подсети) должны совпадать с другой стороной.

### SSL VPN и удалённый доступ (зависит от версии!)

- **Важно:** начиная с **FortiOS 7.6.3 режим SSL VPN tunnel mode удалён на всех моделях** (в GUI и CLI, настройки при обновлении не переносятся). Fortinet рекомендует до обновления перейти на **IPsec dial-up VPN** (IKEv2, можно поверх **TCP 443**, FortiClient 7.4.1+) или **ZTNA**.
- Веб-режим остался под названием **Agentless VPN**, но на моделях с 2 ГБ RAM (40F, 60F/61F, 90G и др.) недоступен; на G-серии entry-level SSL VPN убран ещё в 7.2.12/7.4.8.
- **До 7.6.2 включительно** SSL VPN настраивается в `config vpn ssl settings` + портал + политика с интерфейсом `ssl.root`.

Источники: [Release notes 7.6.3](https://docs2.fortinet.com/document/fortigate/7.6.3/fortios-release-notes/173430/ssl-vpn-tunnel-mode-replaced-with-ipsec-vpn), [Changes on SSL VPN modes from 7.6.3](https://community.fortinet.com/fortigate-3/technical-tip-changes-on-ssl-vpn-modes-starting-from-v7-6-3-204117).

## 9. High Availability (FGCP, active-passive)

Два одинаковых FortiGate (модель и версия FortiOS) образуют кластер: один **primary** обрабатывает трафик, второй **secondary** синхронизирует конфигурацию и сессии и забирает работу при отказе. Связь между ними — **heartbeat**-порты (лучше два, отдельными кабелями).

```
config system ha
    set group-name "FGT-HA"
    set group-id 10
    set mode a-p
    set password CHANGE_ME
    set hbdev "port9" 50 "port10" 50
    set session-pickup enable
    set override disable
    set priority 200              # на втором узле меньше, например 100
    set monitor "wan1" "port2"    # при падении этих портов — переключение
end
```

Проверка: `get system ha status`, `diagnose sys ha checksum cluster` (конфигурации совпадают?). Тестовый failover без смены приоритетов: `execute ha failover set 1` (7.0+).

## 10. Логи и отчёты

- Куда пишутся: **memory** (мало, теряется при перезагрузке), **disk** (на моделях с диском), **FortiAnalyzer** / FortiCloud / syslog — для хранения и отчётов.
- Логировать трафик включают в политике: `set logtraffic all` или `utm`.
- Отчёты (FortiView, Reports) — в GUI; полноценные — в FortiAnalyzer.

```
config log fortianalyzer setting
    set status enable
    set server 10.0.0.50
end

execute log filter category 0        # 0 = traffic, 1 = event ...
execute log filter field dstip 10.10.20.10
execute log filter view-lines 50
execute log display
```

## 11. Лицензии FortiGuard

FortiGuard — облачные сервисы Fortinet: обновления сигнатур **AV и IPS**, базы **Web/DNS filter**, App control, Sandbox Cloud, IP-репутация. Без подписки файрвол работает, но защитные профили перестают обновляться или не работают (web-filter rating). Обычно покупают бандлы (например, UTP/ATP/Enterprise) плюс FortiCare (поддержка и прошивки).

```
get system status                  # серийный номер, версия
diagnose autoupdate versions       # версии баз сигнатур и сроки контрактов
execute update-now                 # принудительное обновление
diagnose debug rating              # доступность серверов рейтинга FortiGuard
```

Для обновлений устройству (management VDOM) нужен доступ в интернет и DNS.
