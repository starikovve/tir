# Шпаргалка: команды MLAG/MCEC в OcNOS

> Сверено со справочником *OcNOS SP Layer 2 Command Reference — MC-LAG Commands*
> (https://docs.ipinfusion.com/service-provider/OcNOS-SP/Layer2-CR/MC-LAG_cmds.html).
> Команды с пометкой **«проверьте на вашей версии OcNOS»** в этом справочнике не найдены или отличаются.

## Диагностика (privileged exec)

| Команда | Что показывает |
|---|---|
| `show mcec` | Общее состояние MCEC: adjacency, роль, strict-режим. **Проверьте на вашей версии OcNOS** (в справочнике есть `show mlag domain`) |
| `show mcec domain` | Параметры домена. **Проверьте на вашей версии OcNOS** (аналог в справочнике `show mlag domain`) |
| `show mcec statistics` | Статистика hello и info PDU. Счётчики RX hello должны расти |
| `show mlag detail` | Детали MLAG-интерфейсов, в том числе `Mlag Sync` (`IN_SYNC`) |
| `show mlag stp-synchronization status` | Статус синхронизации STP между нодами |
| `debug mcec all` / `no debug mcec all` | Включить или выключить все отладочные логи MCEC (варианты: `timer`, `event`, `hello`, `info`, `cli`, `mac-sync`, `all`) |
| `clear mcec statistics` | Сбросить счётчики PDU |

## Strict active-standby (OcNOS 6.5.2+)

Все три команды этого раздела **проверьте на вашей версии OcNOS**: их нет в SP-справочнике. Возможен вариант `strict-active-standby` внутри `mcec domain configuration`.

| Команда | Действие |
|---|---|
| `mcec strict-active-standby` | Включить strict-режим (дефолт с 6.5.2): стейнбай не берёт роль при падении adjacency |
| `mcec strict-active-standby disable` | Отключить strict: стейнбай активируется при падении adjacency (аварийный выход при смерти мастера) |
| `no mcec strict-active-standby` | Вернуть strict к дефолтному состоянию (enabled) |

## Переключение роли (interface mlagN)

| Команда | Действие |
|---|---|
| `switchover type revertive <N>` | После восстановления изначально активная нода забирает роль через N секунд, по умолчанию 10. В справочнике диапазон `<1-255>`, а не `<1-3600>`: **проверьте на вашей версии OcNOS** |
| `switchover type non-revertive` | Роль обратно не возвращается |
| `no switchover type (revertive\|non-revertive)` | Снять настройку |

## Домен MCEC

```text
configure terminal
mcec domain configuration
 domain-address 1111.2222.3333                                  ! HHHH.HHHH.HHHH, одинаковый на обеих нодах
 domain-system-number 1                                         ! 1 на первой ноде, 2 на второй
 domain-priority 32768                                          ! 1-65535, по умолчанию 32768; выше - живёт при split-brain
 domain-hello-timeout long                                      ! long | short
 intra-domain-link po100                                        ! IDL, интерфейс для data-трафика
 intra-domain-peer 192.0.2.12 source-address 192.0.2.11 vrf management   ! IDP
exit
```

| Команда | Назначение |
|---|---|
| `mcec domain configuration` | Вход в режим настройки домена |
| `domain-address <HHHH.HHHH.HHHH>` | Идентификатор домена, одинаковый на обеих нодах |
| `domain-system-number <1-2>` | Номер ноды в домене |
| `domain-priority <1-65535>` | Приоритет ноды, по умолчанию 32768 |
| `domain-hello-timeout (long\|short)` | Таймаут hello |
| `intra-domain-link <IFNAME>` | Интерфейс IDL |
| `intra-domain-peer A.B.C.D source-address A.B.C.D [vrf VRF]` | IP-пир IDP, можно через VRF management |

## MLAG-интерфейс

```text
configure terminal
interface mlag1
 switchport
 bridge-group 1
 switchport mode trunk
 switchport trunk allowed vlan all
 mode active-standby
 switchover type revertive 10
exit
interface po1
 switchport
 bridge-group 1
 switchport mode trunk
 mlag 1                                ! привязка port-channel к mlag1
exit
```

| Команда | Назначение |
|---|---|
| `interface mlagN` | Создать или войти в MLAG-интерфейс |
| `switchport` | Перевести интерфейс в L2 |
| `bridge-group <N>` | Привязать к bridge |
| `switchport mode trunk` | Режим trunk |
| `mlag <1-256>` | На port-channel: привязать его к MLAG-инстансу |
| `mode active-standby` | Режим MLAG active-standby. `active-active` **проверьте на вашей версии OcNOS** |

Адреса и имена интерфейсов в примерах условные.
