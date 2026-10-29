# Примеры конфигов TACACS+ с Active Directory и уровнями доступа

Это рабочие примеры из обсуждения:

- `tac_plus-ng-ad-levels.cfg` — конфиг tac_plus-ng с подключением к AD через MAVIS/LDAP и тремя уровнями (15 / 7 / 1).
- `cisco-ios-example.cfg` — пример настройки устройства Cisco IOS/IOS-XE под эти уровни.

В AD нужно создать группы с CN `ADMIN`, `OPERATOR`, `READONLY`.
`mavis_tacplus-ng_ldap.pl` забирает это имя из `memberOf` (`LDAP_MEMBEROF_REGEX`) и отдаёт его как группу tac_plus-ng. Регистр CN должен совпасть с `group` в конфиге.
Если юзер в нескольких группах — срабатывает самое верхнее правило (приоритет ADMIN > OPERATOR > READONLY).

| Порт | Когда |
| --- | --- |
| 389 LDAP, 636 LDAPS | Один домен. В конфиге включён 636. |
| 3268 GC, 3269 GC по TLS | Весь лес. На GC `memberOf` — только universal-группы, `LDAP_BASE` — корень леса. 3268 без TLS не рекомендуется. |

Серверный файл поправлен и проверен: `tac_plus-ng -P TACACS+/examples/tac_plus-ng-ad-levels.cfg`.

Пароли и ключи — лабораторные, замени на боевые.
