# Juniper Junos

Junos не выдаёт `priv-lvl` 15. После успешного логина устройство шлёт авторизацию с сервисом `junos-exec` (имя по умолчанию, см. `system tacplus-options service-name`) и ждёт атрибут `local-user-name`. Значение — имя **локального шаблона** без пароля. Права берутся из `class` этого шаблона.

Если сервер атрибут не прислал или такого пользователя на коробке нет, Junos подставляет шаблон `remote`. Имя обязано быть в нижнем регистре. Нет ни назначенного шаблона, ни `remote` — аутентификация срывается, даже если пароль на TACACS+ верный.

В [`tac_plus-ng.cfg`](../server/tac_plus-ng.cfg) группа admins получает `local-user-name = remote`, operators — `remote-ro`.

Серверы перебираются в порядке конфигурации. Отказ пароля окончательный. Локальный пароль при `authentication-order tacplus` (без слова `password` в списке) используется только когда ни один сервер не ответил. Если в список явно добавить `password`, Junos пойдёт в локальную базу и после **reject**. Для аварийного входа это дыра: достаточно локального пароля, совпадающего по имени. Ниже список из одного `tacplus`.

Учёт настраивается отдельно. Если под `accounting destination tacplus` серверы не указаны, Junos берёт список из `tacplus-server`. Секрет учёта в примере задан явно и совпадает с секретом аутентификации.

Адрес устройства в примере — `192.0.2.24`, ключ `border-mx-key`.

## Конфигурация

`#` в этом блоке — комментарий Junos, `load merge` его принимает. Пароли в `set` не пишите в кавычках с комментарием в той же строке: комментарий к `set` ниже, в таблице.

```junos
system {
    /* Стабильный адрес источника. Интерфейс lo0.0 уже с адресом 192.0.2.24. */
    tacplus-server {
        192.0.2.10 {
            secret "border-mx-key"; /* тот же ключ, что device border-mx на сервере */
            source-address 192.0.2.24;
            timeout 5;              /* секунды, допустимо 1..90; по умолчанию 3 */
            port 49;
            single-connection;      /* один TCP на много запросов; старый демон может не уметь */
        }
        192.0.2.11 {
            secret "border-mx-key";
            source-address 192.0.2.24;
            timeout 5;
            port 49;
        }
    }
    /* tacplus без password: локальная база только если серверы молчат. */
    authentication-order tacplus;
    login {
        class remote-admin {
            permissions all;
        }
        class remote-ro {
            permissions [ view view-configuration ];
        }
        /* Шаблон. Пароля нет: пароль проверяет TACACS+. Имя remote зарезервировано. */
        user remote {
            full-name "TACACS+ admin template";
            uid 2000;
            class remote-admin;
        }
        user remote-ro {
            full-name "TACACS+ read-only template";
            uid 2001;
            class remote-ro;
        }
        user breakglass {
            class super-user;
            authentication {
                /* хеш, не открытый пароль; создаётся set system login user … plain-text-password */
                encrypted-password "$6$замените-хешем";
            }
        }
    }
    accounting {
        events [ login change-log interactive-commands ];
        destination {
            tacplus {
                server {
                    192.0.2.10 {
                        secret "border-mx-key";
                        source-address 192.0.2.24;
                        port 49;
                        timeout 5;
                    }
                    192.0.2.11 {
                        secret "border-mx-key";
                        source-address 192.0.2.24;
                        port 49;
                        timeout 5;
                    }
                }
            }
        }
    }
}
```

Те же операторы командами `set` (так это вносят в рабочую конфигурацию):

```text
set system tacplus-server 192.0.2.10 secret "border-mx-key"
set system tacplus-server 192.0.2.10 source-address 192.0.2.24
set system tacplus-server 192.0.2.10 timeout 5
set system tacplus-server 192.0.2.10 port 49
set system tacplus-server 192.0.2.10 single-connection
set system tacplus-server 192.0.2.11 secret "border-mx-key"
set system tacplus-server 192.0.2.11 source-address 192.0.2.24
set system tacplus-server 192.0.2.11 timeout 5
set system tacplus-server 192.0.2.11 port 49
set system authentication-order tacplus
set system login class remote-admin permissions all
set system login class remote-ro permissions view
set system login class remote-ro permissions view-configuration
set system login user remote full-name "TACACS+ admin template"
set system login user remote uid 2000
set system login user remote class remote-admin
set system login user remote-ro full-name "TACACS+ read-only template"
set system login user remote-ro uid 2001
set system login user remote-ro class remote-ro
set system login user breakglass class super-user
set system accounting events login
set system accounting events change-log
set system accounting events interactive-commands
set system accounting destination tacplus server 192.0.2.10 secret "border-mx-key"
set system accounting destination tacplus server 192.0.2.10 source-address 192.0.2.24
set system accounting destination tacplus server 192.0.2.10 port 49
set system accounting destination tacplus server 192.0.2.10 timeout 5
set system accounting destination tacplus server 192.0.2.11 secret "border-mx-key"
set system accounting destination tacplus server 192.0.2.11 source-address 192.0.2.24
set system accounting destination tacplus server 192.0.2.11 port 49
set system accounting destination tacplus server 192.0.2.11 timeout 5
```

## Построчно

| Команда | Зачем |
| --- | --- |
| `set system tacplus-server 192.0.2.10 secret "…"` | Первичный сервер и общий ключ. В конфигурации Junos секрет хранится зашифрованным (`$9$…`). |
| `… source-address 192.0.2.24` | Источник пакетов к TACACS+. Должен быть адресом интерфейса этой коробки и совпасть с `device border-mx`. |
| `… timeout 5` | Ожидание ответа, секунды. По исчерпании опрашивается следующий сервер. |
| `… port 49` | Порт. 49 и так порт по умолчанию; строка фиксирует его явно. |
| `… single-connection` | Не открывать новый TCP на каждый запрос. Если сервер флаг не поддерживает, связь с ним пропадёт — строку удаляют. |
| `set system tacplus-server 192.0.2.11 …` | Второй сервер, без `single-connection` в примере, чтобы был виден минимальный набор. Ключ тот же: на сервере оба адреса можно завести отдельными `device` с одним секретом. |
| `set system authentication-order tacplus` | Сначала TACACS+. Локальный пароль — неявный запасной метод только при недоступности серверов. |
| `set system login class remote-admin permissions all` | Класс полного админа для шаблона `remote`. Близкий встроенный класс — `super-user`. |
| `set system login class remote-ro permissions view` | Операционные команды просмотра. |
| `… permissions view-configuration` | Чтение конфигурации без права её менять. Вместе с `view` это класс только для чтения. |
| `set system login user remote … class remote-admin` | Шаблон, не человек. Пароль не задают. Сюда попадают admins с сервера и любой TACACS-пользователь без своего `local-user-name`. |
| `… uid 2000` | Числовой uid шаблона. Должен быть свободен. У `remote` и `remote-ro` uid разные. |
| `set system login user remote-ro … class remote-ro` | Шаблон оператора. Имя совпадает с `set local-user-name = remote-ro` в профиле operators. |
| `set system login user breakglass class super-user` | Аварийная локальная учётка. Пароль задаётся интерактивно (`plain-text-password`) или готовым хешем. |
| `set system accounting events login` | Писать вход и выход. |
| `… change-log` | Писать изменение конфигурации. |
| `… interactive-commands` | Писать введённые команды. Это основной командный accounting на Junos; отдельного `authorization commands`, как на IOS, нет. |
| `set system accounting destination tacplus server 192.0.2.10 secret "…"` | Куда слать учёт. Секрет свой у этой сессии, его сверяют с ключом `device` на том же сервере. |
| `… source-address / port / timeout` | Те же смысл и значения, что у `tacplus-server`, но для учёта. Их легко забыть и уйти на адрес выходного интерфейса. |
| сервер `192.0.2.11` в accounting | Второй приёмник учёта, если первый не ответил. |

Дополнительно, уже на сервере, Junos понимает вендорные атрибуты `allow-commands`, `deny-commands`, `allow-configuration`, `deny-configuration`. В этом контуре они не используются: граница прав проведена классом шаблона, и она одинаково действует, даже если авторизация TACACS+ недоступна, а пользователя пустило локально по шаблону.

Посмотреть, куда сели активные сессии:

```text
show system users
show network-access tacplus state
```

Вторая команда есть не на каждом выпуске Junos (её переносили между ветками). Факт запроса виден в `authentication log` tac_plus-ng.
