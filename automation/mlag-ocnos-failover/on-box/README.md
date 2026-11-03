# On-box failover для MLAG на OcNOS (стейнбай-нода)

Скрипт `mlag-onbox-failover.sh` работает в Linux-шелле OcNOS на **стейнбай-ноде** MCEC-домена.
Он закрывает «слепое пятно» режима strict-active-standby: когда мастер внезапно умирает
(power-cycle, reboot из Linux, APC, crash), стейнбай сам не активируется.

> ⚠️ Это пример. До продакшена прогоните его в лаборатории на вашей версии OcNOS.
> Команды и шаблоны вывода вынесены в переменные. Всё непроверенное помечено ниже.

## Почему on-box, а не внешний мониторинг

- On-box скрипт видит **локальный статус adjacency** MCEC напрямую, без внешней сети и без лишней точки отказа.
- Внешний Zabbix или Linux-бокс арбитром быть не должен. Он видит ноды только через сеть и сам может ошибиться или упасть.
- Внешний мониторинг остаётся **необязательной страховкой**: алерты и контроль, что on-box скрипт жив.
- **Два IDP-линка.** Adjacency переживает падение одного канала, ложные срабатывания реже. Но есть ограничение, см. раздел «Ограничения»: по документации strict-режим настраивается только при одном канале.

## Логика

**Основной сигнал** — локальный adjacency (`show mlag domain summary`, строка `Domain Adjacency : UP/DOWN`).
**Подтверждение** — ping мастера (IDP или mgmt) в VRF management. Один только ping ничего не запускает.

| Adjacency | Локальная роль | Ping мастера | Действие |
|---|---|---|---|
| UP | любая | любой | ничего, счётчик сброшен |
| не распознан | любая | любой | ничего, WARN в лог |
| DOWN | ACTIVE | любой | ничего: плановый CLI-reload мастера, стейнбай сам встал в active |
| DOWN | standby | отвечает | ничего: проблема линка или IDP, только лог |
| DOWN | standby | молчит `FAIL_THRESHOLD` раз подряд | повторная проверка роли. Если всё ещё standby, выполняется `mcec strict-active-standby disable` + `commit`, ставится флаг `in_failover` |

**Grace для планового reload.** Действие выполняется только после `FAIL_THRESHOLD × CHECK_INTERVAL`, по умолчанию 30 с, и только если нода к этому моменту **всё ещё standby**. При reload мастера через CLI OcNOS стейнбай становится active сам, и скрипт ничего не делает.

**Восстановление** (стоит флаг `in_failover`, adjacency UP и мастер пингуется):
1. Скрипт ждёт `RECOVERY_WAIT` (60 с) и перепроверяет.
2. Включает strict обратно: `no mcec strict-active-standby` + `commit`.
3. Если нода всё ещё ACTIVE:
   - `REVERTIVE=yes`: роль вернётся сама по таймеру `switchover type revertive`;
   - `REVERTIVE=no`: в лог пишется, что нужен **ручной** reload через CLI. Автоматический reload только при `AUTO_RELOAD=yes`.

**Почему авто-reload выключен по умолчанию.** Reload — это ещё одно переключение и потеря трафика. Если мастер ожил не полностью (нет `IN_SYNC`), можно остаться совсем без активной ноды. Это решение лучше принимать человеку.

**Служебное:**
- Флаг failover и счётчик хранятся в `/var/lib/mlag-onbox-failover/`, поэтому скрипт идемпотентен.
- `flock` на `/run/mlag-onbox-failover.lock` не даёт запускам наложиться.
- Лог пишется в `/var/log/mlag-onbox-failover.log` и в syslog (тег `mlag-onbox-failover`).

## Настройка

Переменные можно задать в `/etc/default/mlag-onbox-failover` или в окружении.

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `PEER_IP` | `192.0.2.1` | IP мастера (IDP или mgmt), заглушка |
| `PING_VRF` | `management` | VRF для ping. Пусто — default VRF |
| `FAIL_THRESHOLD` | `3` | число подряд проверок «мёртв» |
| `CHECK_INTERVAL` | `10` | интервал проверок в daemon-режиме, с |
| `RECOVERY_WAIT` | `60` | пауза перед возвратом strict, с |
| `REVERTIVE` | `yes` | на mlag-интерфейсах настроен `switchover type revertive` |
| `AUTO_RELOAD` | `no` | авто-reload при non-revertive |
| `DRY_RUN` | `no` | только логировать действия |
| `CLI_BIN` / `CLI_OPT` | `cmlsh` / `-e` | как вызвать CLI OcNOS из bash (**проверить**) |
| `CMD_*`, `RE_*` | см. скрипт | команды и шаблоны вывода |

## Установка и запуск

```bash
install -m 755 mlag-onbox-failover.sh /usr/local/sbin/
cat > /etc/default/mlag-onbox-failover <<'CFG'
PEER_IP=192.0.2.1
PING_VRF=management
DRY_RUN=yes          # сначала наблюдаем
CFG
/usr/local/sbin/mlag-onbox-failover.sh --dry-run; tail /var/log/mlag-onbox-failover.log
```

**Cron не умеет «каждые 10 секунд»**: минимальный шаг у cron — 1 минута. Есть два варианта.

**1. Daemon-режим (рекомендуется).** Цикл внутри скрипта со `sleep CHECK_INTERVAL`, запуск через systemd:

```ini
# /etc/systemd/system/mlag-onbox-failover.service
[Unit]
Description=OcNOS MLAG on-box failover helper
After=network-online.target

[Service]
ExecStart=/usr/local/sbin/mlag-onbox-failover.sh --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now mlag-onbox-failover
```

Если systemd недоступен, запускайте через cron при загрузке:

```cron
@reboot /usr/local/sbin/mlag-onbox-failover.sh --daemon >/dev/null 2>&1
```

**2. Запасной вариант на cron.** Шесть записей со сдвигом по 10 с (flock не даст запускам пересечься):

```cron
* * * * * /usr/local/sbin/mlag-onbox-failover.sh
* * * * * sleep 10; /usr/local/sbin/mlag-onbox-failover.sh
* * * * * sleep 20; /usr/local/sbin/mlag-onbox-failover.sh
* * * * * sleep 30; /usr/local/sbin/mlag-onbox-failover.sh
* * * * * sleep 40; /usr/local/sbin/mlag-onbox-failover.sh
* * * * * sleep 50; /usr/local/sbin/mlag-onbox-failover.sh
```

Учтите: во время `RECOVERY_WAIT` запуск держит lock около 60 с, поэтому соседние запуски из cron просто выходят.

## Что проверено, а что нет

| Команда | Статус |
|---|---|
| `mcec strict-active-standby disable` / `no mcec strict-active-standby` (configure mode, OcNOS 6.5.2+) | ✅ [OcNOS SP 7.0 L2: mcec strict-active-standby](https://documentation.ipinfusion.com/ocnos-sp-layer-2-7.0/Content/ocnos-layer-2/mc-link-aggr-cli-commands/mcec-strict-active-stand.htm) |
| `commit` после изменений в configure | ✅ CLI транзакционный: [Transaction-based CLI](https://documentation.ipinfusion.com/ocnos-sp-layer-2-7.0/Content/Global-topics/Preface-CLI/transx-based-cmd-line-interf.htm) |
| `show mlag domain summary` / `details` → `Domain Adjacency : UP` | ✅ [MC-LAG Commands](https://docs.ipinfusion.com/service-provider/OcNOS-SP/Layer2-CR/MC-LAG_cmds.html) |
| `show mlag detail` (`Mlag Sync IN_SYNC`) | ✅ есть в справочнике. Строку с локальной ролью active/standby (`RE_ACTIVE`) **проверить** |
| `show mcec` | ❌ в справочниках не найдена (есть `show mcec statistics`). Для adjacency используется `show mlag domain summary` |
| Вызов CLI из bash: `cmlsh -e "<cmd>"` | ❌ **не проверено**: опция неинтерактивного запуска `cmlsh` публично не документирована. Документирован обратный путь, `exec-shell` из CLI (7.0+). Проверьте `cmlsh --help` |

## Ограничения

- **Strict-режим и число каналов.** По документации `mcec strict-active-standby` можно настроить, только если между нодами **один** канал (IDL или IDP). Схема «два IDP» или «IDL + IDP» может не позволить включать и выключать strict. Проверьте в лаборатории.
- **Когда срабатывает disable.** Изменение strict-режима действует **со следующего события adjacency DOWN**. Если выключить strict, когда adjacency уже лежит, стейнбай может не активироваться сразу. Это главный риск всей схемы, его нужно проверить первым. Обходные варианты: заранее держать strict выключенным (ценой риска split-brain) или после disable форсировать событие, например перезапуском IDP. Оба варианта тоже нужно проверить.
- **Split-brain.** Если упали оба IDP или весь канал между нодами, а мастер жив, но не пингуется (ping идёт тем же путём), скрипт решит, что мастер мёртв, и получится dual-active. Пингуйте по независимому пути (mgmt) и держите два физически разных IDP-линка.
- **Сравнение строк.** Шаблоны `RE_*` сравнивают текст вывода. Смена формата при upgrade OcNOS ломает распознавание. В таком случае скрипт ничего не делает и пишет WARN в лог.
- **Скрипт только на стейнбае.** При смене ролей его нужно ставить и на вторую ноду. Он сам проверяет локальную роль и на активной ноде ничего не делает.
