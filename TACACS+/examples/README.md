# Примеры конфигов TACACS+ с Active Directory и уровнями доступа

Это рабочие примеры из обсуждения:

- `tac_plus-ng-ad-levels.cfg` — конфиг tac_plus-ng с подключением к AD через MAVIS/LDAP и тремя уровнями (15 / 7 / 1).
- `cisco-ios-example.cfg` — пример настройки устройства Cisco IOS/IOS-XE под эти уровни.

В AD нужно создать группы: `ADMIN`, `OPERATOR`, `READONLY`.
Если юзер в нескольких группах — срабатывает самое верхнее правило (приоритет ADMIN > OPERATOR > READONLY).

Пароли и ключи — лабораторные, замени на боевые.
