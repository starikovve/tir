# FortiGate: шпаргалка по быстрой диагностике

> Колонка **FortiOS** показывает, с какой версии работает команда: «все» — работает на любой актуальной версии; **★** — команда, актуальная для свежих версий (7.2 / 7.4 / 7.6).
> В multi-VDOM режиме команды выполняются внутри нужного VDOM (`config vdom` → `edit <имя>`) или в `config global`.
> Перед использованием проверьте синтаксис подсказкой `?` на своей версии.

## Система

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `get system status` | все | Модель, серийник, версия, режим VDOM и HA. Первая команда |
| `get hardware status` | все | CPU, RAM, диск, чипы. Проверить железо и наличие диска |
| `diagnose hardware deviceinfo nic port1` | все | Порт: скорость, дуплекс, ошибки и CRC. Подозрение на физику |
| `get system performance status` | все | CPU, память, сессии, uptime. Перегрузка |
| `get system performance top` | все | Процессы по CPU (как top). Какой демон грузит |
| `diagnose sys logdisk usage` | все | Заполненность лог-диска по VDOM ¹ |
| `get log disk setting` | все | Настройки логов на диск ¹ |

¹ Отдельной команды `get log disk` нет: настройки показывает `get log disk setting`, заполненность диска — `diagnose sys logdisk usage`.

## Сеть

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `get router info routing-table all` | все | Активные маршруты. Куда уходит трафик |
| `get router info routing-table database` | все | Все маршруты, включая неактивные. Почему маршрут не выбран |
| `diagnose ip route list` | все | Маршруты ядра. Глубокая проверка |
| `diagnose sniffer packet any 'host 10.10.20.10' 4` | все | Захват пакетов с именем интерфейса (Ctrl+C — стоп). Дошёл ли пакет |
| `execute ping 198.51.100.1` | все | Ping с FortiGate |
| `execute ping-options source 10.10.10.1` | все | Source для ping, например для проверки VPN |
| `execute traceroute 198.51.100.1` | все | Трассировка |
| `get system interface physical` | все | Link, скорость, дуплекс портов |
| `diagnose ip arp list` | все | ARP-таблица. Виден ли сосед на L2 |
| `diagnose sys sdwan health-check` | 6.4+ ★ | Состояние SLA-проб SD-WAN (в 6.2 и раньше — `diagnose sys virtual-wan-link health-check`) |
| `diagnose sys sdwan service` | 6.4+ ★ | Какие SD-WAN правила и какой канал выбраны |

## Firewall и политики

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `get firewall policy` | все | Список политик. Правило есть? |
| `diagnose firewall iprope list 100004` | все | Политики в ядре (группа 100004 — forward) |
| `diagnose firewall iprope lookup <src> <sport> <dst> <dport> <proto> <srcintf>` | 6.2+ | Какая политика сработает, без трафика ² |

² Порядок аргументов `iprope lookup` различается между версиями. Проверьте его через `?`.

**`diagnose debug flow`** (все версии) — почему пакет пропущен или отброшен:

```
diagnose debug reset
diagnose debug flow filter clear
diagnose debug flow filter addr 10.10.20.10
diagnose debug flow show function-name enable
diagnose debug flow trace start 10
diagnose debug enable
# ...сгенерировать трафик; искать policy id, SNAT/DNAT, "Denied by forward policy check"...
diagnose debug disable
diagnose debug reset
```

## VPN

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `diagnose vpn ike gateway list` | все | IKE (phase1): established, peer, версия IKE. Туннель не поднимается |
| `diagnose vpn tunnel list` | все | IPsec SA (phase2): SPI, счётчики enc/dec. Up, но трафик не идёт |
| `get vpn ipsec tunnel details` | все | Детали туннелей: селекторы, трафик |
| `get vpn ipsec tunnel summary` | все | Краткий статус туннелей |
| `diagnose vpn ike log filter rem-addr4 198.51.100.50` | 7.0+ ★ | Фильтр IKE-отладки по пиру (до 7.0: `diagnose vpn ike log-filter dst-addr4 …`) |
| `diagnose debug application ike -1` → `diagnose debug enable` | все | Лог согласования IKE (proposal, PSK). Потом `diagnose debug disable` |
| `diagnose vpn ssl list` / `get vpn ssl monitor` | до 7.6.2 | Сессии SSL VPN. С 7.6.3 tunnel mode удалён, вместо него IPsec dial-up |

## VDOM

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `config system global` → `set vdom-mode multi-vdom` | 6.4+ | Включить VDOM (до 6.4: `set vdom-admin enable`) |
| `config vdom` → `edit <имя>` | все | Войти в VDOM |
| `next` / `end` | все | Выйти из объекта / раздела |
| `config global` | все | Глобальный контекст: интерфейсы, HA, админы |
| `diagnose sys vd list` | все | Список VDOM с внутренними ID |
| `get system vdom-link` | все | Список vdom-link (в `config global`) |

## Сессии

Сначала задайте фильтр:

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `diagnose sys session filter clear` | все | Сбросить фильтр |
| `diagnose sys session filter src 10.10.10.5` | все | Фильтр (также `dst`, `dport`, `proto`, `policy`) |
| `diagnose sys session list` | все | Сессии по фильтру: политика, NAT, offload |
| `diagnose sys session clear` | все | ⚠️ Удаляет сессии по фильтру, **без фильтра — все** |
| `diagnose sys session full-stat` | все | Статистика таблицы сессий, переполнение |

## UTM и FortiGuard

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `diagnose debug rating` | все | Связь с серверами рейтинга FortiGuard. Web filter не работает |
| `get webfilter status` | все | Статус web filter и лицензии |
| `diagnose autoupdate versions` | все | Версии баз AV и IPS, сроки контрактов |
| `execute update-now` | все | Обновить сигнатуры сейчас |

## Логи

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `execute log filter device disk` | все | Источник логов для просмотра (`memory`, `disk`, `fortianalyzer`; в старых версиях — числом) |
| `execute log filter category 0` | все | Категория: 0 traffic, 1 event, 3 webfilter… (`?` покажет список) |
| `execute log filter field dstip 10.10.20.10` | все | Фильтр по полю (srcip, dstport, policyid…) |
| `execute log filter view-lines 50` | все | Сколько строк показывать |
| `execute log display` | все | Показать логи по фильтру |
| `execute log filter reset` | все | Сбросить фильтр |
| `diagnose log test` | все | Сгенерировать тестовые логи. Проверить, что логи доходят до FAZ/syslog |
| `get log fortianalyzer setting` | все | Настройки отправки логов в FortiAnalyzer |
| `diagnose test application miglogd 6` | все | Статистика демона логов miglogd (номера тестов — через `?`) |
| `execute log fortianalyzer test-connectivity` | все | Проверить связь и авторизацию с FortiAnalyzer |

## HA

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `get system ha status` | все | Роли узлов, здоровье, причина переключения |
| `diagnose sys ha checksum cluster` | все | Совпадает ли конфигурация на узлах |
| `execute ha manage <id> <admin>` | все | CLI на другом узле кластера |
| `execute ha failover set 1` / `unset 1` | 7.0+ | Ручной failover для теста (без смены приоритетов) |

## Перезагрузка и сброс

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `execute reboot` | все | Перезагрузка (с подтверждением) |
| `execute shutdown` | все | Корректное выключение |
| `execute factoryreset` | все | ⚠️ **ОПАСНО:** сброс к заводским настройкам, стирает всю конфигурацию. Только после бэкапа и с доступом к консоли |

## Сохранение конфигурации

| Команда | FortiOS | Что делает / когда нужна |
|---|---|---|
| `execute backup config tftp fgt.conf 10.0.0.50` | все | Бэкап на TFTP (также `ftp`, `usb`). Перед изменениями |
| `execute backup full-config tftp fgt-full.conf 10.0.0.50` | все | Бэкап с дефолтными значениями |
| `show` / `show full-configuration` | все | Текущая конфигурация раздела |
| `get system config status` | ? | Из исходного списка. В документации не найдена, проверьте `?` ³ |

³ Если `get system config status` на вашей версии нет, состояние конфигурации можно проверить так: `diagnose sys ha checksum show` (контрольные суммы), `execute revision list config` (ревизии конфига).
