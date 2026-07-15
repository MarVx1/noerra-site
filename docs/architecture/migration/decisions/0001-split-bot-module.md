# ADR 0001 (migration): разбор `bot/bot.py` на модули

## Статус

Выполнено (коммиты `61800c6`, `10261d3`, 2026-07-14).

## Контекст

`bot/bot.py` вырос до 1283 строк: диспетчер, инициализация Bot,
клавиатуры, публикация статей, все callback-обработчики модерации,
команды, Knowledge Core команды, кластерные колбэки — всё в одном файле.

## Решение

Вынесено по ответственности, каждый модуль регистрирует свои обработчики
на общем `dp`, импортированном из `bot/bot.py`:

- `bot/keyboards.py` — inline-клавиатуры.
- `bot/publishing.py` — `_publish_article`, `send_for_moderation`,
  `send_draft_for_editor`, digest-кандидаты.
- `bot/callbacks.py` — `on_approve/on_reject/on_draft_*/on_digest_*`.
- `bot/commands.py` — `/start`, `/digest`, `/stats`, `/invalidate_cache`,
  `/help`, `/drafts`, `/audience_stats`.
- `bot/knowledge_commands.py` — 11 команд Knowledge Core.
- `bot/cluster_callbacks.py` — 3 кластерных колбэка.
- `bot/reactions.py` — учёт реакций (добавлен позже, 2026-07-15).

`bot/bot.py` после разбора — 93 строки: только `dp`, `get_bot`,
`ADMIN_ID`, `is_admin`, `html_escape`, `CallbackLoggingMiddleware`,
`start_bot`, плюс импорты модулей в конце файла (порядок важен — сначала
должны быть определены `dp`/`is_admin`/`html_escape`/`get_bot`).

`scheduler/scheduler.py` делал `from bot.bot import send_draft_for_editor`
как внешний потребитель — после переноса функции в `bot/publishing.py`
понадобился явный реэкспорт обратно в `bot/bot.py`
(`from bot.publishing import send_draft_for_editor`), иначе импорт в
scheduler ломался.

## Урок для тестов

`unittest.mock.patch.object(<module>, "name", ...)` перехватывает вызов
только если функция, которая делает этот вызов, **физически определена**
в этом модуле — поиск имени идёт по `__globals__` вызывающей функции, не
вызываемой. После переноса обработчика в новый файл все патчи в тестах,
целившие на `bot.bot`, нужно перецелить на модуль, где обработчик теперь
живёт. `tests/test_bot.py` использует алиасы `b/kb/pub/cb_mod/cmd_mod` —
по одному на модуль — вместо единого патча на `bot.bot`.

Тот же урок повторно всплыл 2026-07-15 в `tests/test_cluster_callbacks.py`
— в другом виде: `on_cluster_confirm` рано возвращался из-за
`is_admin(...)`, потому что `ADMIN_ID` (читается из окружения при импорте
`bot/bot.py`) не был явно запатчен в тесте — тест полагался на переменную
окружения, а не патчил `b.ADMIN_ID` напрямую, как это сделано во всех
остальных тестах бота.

## Последствия

- Перенос не затронул ни один существующий тест в `test_bot.py` — все
  вынесенные функции физически не были покрыты тестами через `bot.bot`
  до переноса.
- `bot/bot.py` теперь стабильное ядро, новые обработчики добавляются
  отдельными модулями, а не растят один файл дальше.
