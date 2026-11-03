# Урок 25. Защита от атак

_Блок 5. Безопасность_

```text
Длительность: 60 секунд. Формат: вертикальное видео 9:16 (YouTube Shorts / TikTok).
Стиль: тёмный фон (почти чёрный), моноширинный шрифт, зелёный текст как в терминале, эффект набора текста. Без логотипов, без музыки на фоне голоса, без воды — только суть.

Тема: Урок 25. Защита от атак.

Сюжет по сценам:
0–5 с — хук: Злоумышленник в той же VLAN. Что он может и как его остановить?
5–20 с — Атаки L2: поддельный DHCP-сервер · ARP spoofing · MAC flooding · VLAN hopping
20–40 с — Cisco: `ip dhcp snooping` · `ip dhcp snooping vlan 10` · аплинк: `ip dhcp snooping trust` · `ip arp inspection vlan 10` · `ip verify source` (IP Source Guard)
40–55 с — Против VLAN hopping: `switchport nonegotiate`, неиспользуемые порты в shutdown и в пустой VLAN, native VLAN не 1 · управление: только SSH, `transport input ssh`
55–60 с — финальная строка крупно по центру: «DHCP snooping + DAI + port security + no DTP.»

Закадровый голос (спокойный, уверенный, по-русски):
Защита от атак на втором уровне — это как охрана внутри офиса, а не только на входе. Кто-то может поставить свой DHCP-сервер и раздавать фальшивый шлюз. DHCP snooping разрешает ответы сервера только с доверенных портов. ARP spoofing — когда злоумышленник говорит «я шлюз»; Dynamic ARP Inspection сверяет ARP с таблицей snooping. IP Source Guard не даёт подменить свой адрес. MAC flooding останавливает port security. Против VLAN hopping выключаем автосогласование trunk и не используем VLAN один. А управление устройствами — только по SSH.

Финальная строка-вывод: DHCP snooping + DAI + port security + no DTP.
```
