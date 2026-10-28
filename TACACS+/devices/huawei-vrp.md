# Huawei VRP (HWTACACS)

На VRP протокол называется HWTACACS. Для сервера это обычный TACACS+ на TCP/49: тот же ключ, тот же `service == shell`, тот же `priv-lvl`. Отдельного демона «под Huawei» не требуется. Профиль admins/operators из [`tac_plus-ng.cfg`](../server/tac_plus-ng.cfg) подходит, команда просмотра на VRP — `display`, она уже разрешена операторам.

Схема AAA сама по себе ничего не делает, пока не привязана к **домену**. Админский SSH без `@домен` в имени попадает в `default_admin`. Домен `default` — для абонентского доступа, его здесь не трогаем.

`authentication-mode hwtacacs local` спрашивает локальную базу, когда сервер не ответил вовремя. Явный отказ HWTACACS локальный пароль не открывает.

Команды ниже вводятся из system-view. Символ `#` в выводе `display current-configuration` — разделитель секций, который рисует сама VRP. В CLI его как комментарий вставлять нельзя, поэтому в блоке только команды, разбор — таблицей.

Адрес устройства в примере — `192.0.2.23`, ключ `agg-vrp-key`. Уровень привилегии на классической VRP — 0…15. На ветке V600 уровней команд меньше (0…3); лишние `authorization-cmd` такой релиз не примет, их оставляют в пределах существующей шкалы.

## Конфигурация

```text
system-view
hwtacacs enable
hwtacacs-server template TACACS-TPL
 hwtacacs-server authentication 192.0.2.10 49
 hwtacacs-server authentication 192.0.2.11 49 secondary
 hwtacacs-server authorization 192.0.2.10 49
 hwtacacs-server authorization 192.0.2.11 49 secondary
 hwtacacs-server accounting 192.0.2.10 49
 hwtacacs-server accounting 192.0.2.11 49 secondary
 hwtacacs-server shared-key cipher agg-vrp-key
 hwtacacs-server timer response-timeout 5
 hwtacacs-server source-ip 192.0.2.23
 hwtacacs-server user-name original
 quit
aaa
 authentication-scheme TACACS-AUTH
  authentication-mode hwtacacs local
 quit
 authorization-scheme TACACS-AUTHOR
  authorization-mode hwtacacs local
  authorization-cmd 0 hwtacacs local
  authorization-cmd 1 hwtacacs local
  authorization-cmd 15 hwtacacs local
 quit
 accounting-scheme TACACS-ACCT
  accounting-mode hwtacacs
  accounting start-fail online
 quit
 recording-scheme TACACS-REC
  recording-mode hwtacacs TACACS-TPL
 quit
 cmd recording-scheme TACACS-REC
 domain default_admin
  authentication-scheme TACACS-AUTH
  authorization-scheme TACACS-AUTHOR
  accounting-scheme TACACS-ACCT
  hwtacacs-server TACACS-TPL
 quit
 local-user breakglass password irreversible-cipher LabBreakGlass
 local-user breakglass privilege level 15
 local-user breakglass service-type terminal ssh
 quit
```

`local-user … password irreversible-cipher` на части релизов принимает уже зашифрованную строку, а открытый пароль задаётся интерактивно (`local-user breakglass password`). Если образ ругается на открытый текст после `irreversible-cipher`, пароль вводят со строки приглашения, в конфигурации остаётся хеш.

## Построчно

| Команда | Зачем |
| --- | --- |
| `system-view` | Переход из user-view в конфигурацию. |
| `hwtacacs enable` | Глобально разрешить HWTACACS. На актуальных VRP уже включено по умолчанию; строка ничего не ломает и видна в конфигурации. |
| `hwtacacs-server template TACACS-TPL` | Именованный шаблон серверов. Домен ссылается на шаблон, не на IP. |
| `hwtacacs-server authentication 192.0.2.10 49` | Куда слать проверку пароля и на какой порт. Три роли настраиваются отдельно, даже если IP один. |
| `hwtacacs-server authentication 192.0.2.11 49 secondary` | Второй сервер аутентификации. `secondary` (и при необходимости `third`) — порядок, не «балансировка». |
| `hwtacacs-server authorization …` | Куда слать запрос оболочки и команд. Без этих строк авторизация не уедет на tac_plus-ng, даже если authentication уже работает. |
| `hwtacacs-server accounting …` | Куда слать учёт. primary и secondary повторяют пару адресов. |
| `hwtacacs-server shared-key cipher agg-vrp-key` | Общий ключ шаблона. `cipher` на вводе принимает текст ключа, в конфигурации хранится маскированное значение. Ключ равен `device agg-vrp`. |
| `hwtacacs-server timer response-timeout 5` | Секунды до объявления сервера недоступным. По умолчанию тоже 5. После тишины срабатывает следующий метод схемы (`local`). |
| `hwtacacs-server source-ip 192.0.2.23` | Адрес источника. Иначе уйдёт адрес выходного интерфейса и сервер не попадёт в `device agg-vrp`. Альтернатива — `source-ip source-loopback <номер>`. |
| `hwtacacs-server user-name original` | Отправить имя так, как его ввели, без дописывания домена. Иначе сервер увидит `alice@default_admin` и не найдёт `user alice`. |
| `quit` | Выход из вида шаблона в system-view. |
| `aaa` | Вид AAA. |
| `authentication-scheme TACACS-AUTH` | Новая схема проверки пароля. Встроенная `default` остаётся нетронутой. |
| `authentication-mode hwtacacs local` | Сначала HWTACACS, при таймауте — локальные `local-user`. |
| `authorization-scheme TACACS-AUTHOR` | Схема авторизации, отдельно от аутентификации. |
| `authorization-mode hwtacacs local` | Уровень привилегии и прочие атрибуты сессии брать с сервера. |
| `authorization-cmd N hwtacacs local` | Команды уровня N спрашивать у сервера. Уровень указывается по одному; уровня без такой строки устройство серверу не показывает, команда выполняется локально. Для админов и операторов этого контура нужны как минимум 0, 1 и 15. |
| `accounting-scheme TACACS-ACCT` | Схема учёта. |
| `accounting-mode hwtacacs` | Слать учёт на HWTACACS, а не в none. |
| `accounting start-fail online` | Пускать пользователя, даже если стартовая accounting-запись не ушла. По умолчанию как раз наоборот (`offline`): нет учёта — нет сессии. Для лаборатории и аварии сервера учёта оставляем `online`. |
| `recording-scheme TACACS-REC` | Отдельная схема записи команд. Это не замена `accounting-scheme`: командный след на VRP включается recording-схемой. |
| `recording-mode hwtacacs TACACS-TPL` | Писать команды на сервер из этого шаблона. |
| `cmd recording-scheme TACACS-REC` | Включить эту запись для команд устройства. |
| `domain default_admin` | Встроенный домен администраторов. Схемы, не привязанные к домену, не используются при логине. |
| `authentication-scheme TACACS-AUTH` | В этом домене — наша схема, не локальная `default`. |
| `authorization-scheme TACACS-AUTHOR` | В этом домене — авторизация через HWTACACS. |
| `accounting-scheme TACACS-ACCT` | В этом домене — учёт через HWTACACS. |
| `hwtacacs-server TACACS-TPL` | Каким шаблоном пользоваться домену. Без строки схемы есть, а слать запрос некуда. |
| `local-user breakglass password …` | Локальный аварийный пользователь. |
| `local-user breakglass privilege level 15` | Его уровень, когда пустило локально. |
| `local-user breakglass service-type terminal ssh` | Разрешить этой учётке консоль и SSH. Без service-type пользователь существует, но войти типом сервиса не может. |

Проверка:

```text
display hwtacacs-server template
display domain default_admin
display aaa configuration
```
