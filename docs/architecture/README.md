# Noerra — архитектура

Telegram-бот: собирает научные источники (мозг/психология), оценивает,
готовит редакционные черновики, публикует одобренные посты в канал через
Telegraph. Полностью rule-based — никакого LLM/внешнего AI API в тексте
(regex, шаблонные банки, эвристики). Причина и история решения — см.
[decisions/0001-rule-based-no-llm.md](decisions/0001-rule-based-no-llm.md).

## Поток данных

```
parsers/*        → RawArticle (сырая статья: title/url/abstract/source)
scoring/scorer    → числовая оценка релевантности
classifier        → тема (topic)
adaptation/       → Editorial Engine: analyze → build_structure → generate_text → critic
database/db.py    → SQLite (articles, drafts, publications, summaries, ...)
bot/              → модерация в Telegram (одобрить/отклонить/редактировать)
publisher/        → публикация: Telegraph-страница + пост в канал
scheduler/        → APScheduler: периодический pipeline, дайджест, аудиты
```

`scheduler/scheduler.py:run_pipeline` — точка входа живого прогона: парсеры
→ scoring → classifier → `adaptation/pipeline.py:Pipeline.run_for_article`
(analyze/build_structure/generate_text/critic) → черновик в очередь на
модерацию (`drafts`, статус `pending`) → администратор одобряет/отклоняет
через кнопки в Telegram (`bot/callbacks.py`, `bot/cluster_callbacks.py`) →
`publisher/publisher.py` создаёт Telegraph-страницу и постит в канал.

## Editorial Engine (`adaptation/`)

Основная логика генерации текста статьи — не единый модуль, а
последовательность этапов, вызываемых `EditorialEngine` (`editorial_engine.py`):

1. **analyze()** — перевод и очистка абстракта, декомпозиция на роли
   (finding/method/practical), определение сценария (discovery/practical/
   discussion/debunk), заголовок, лид.
2. **build_structure()** — собирает список текстовых блоков: заголовок → лид
   → reader question (`reader_question.py`) → ритмический переход
   (`transitions.py`) → тело → переход → аналогия (`analogy_bank.py`) →
   контекст/доказательность/ограничения → переход → "почему важно" →
   caveat → источники.
3. **generate_text()** — рендер блоков в текст, финальный проход
   `simplifier.py` (убирает канцеляризмы).
4. **EditorialCritic** (`critic.py`) — хард/софт-проверки перед публикацией:
   язык (латиница вне акронимов — hard), аналогия обязательна (hard),
   источники обязательны (hard), стиль/ритм/canцеляризмы (soft).

Известный, осознанно принятый потолок этого подхода (не баги, не будет
починено без LLM — см. [[project-noerra-editorial-engine]] в memory):
тяжёлые академические предложения 30-50 слов, шаблонный блок
«Ограничения», смысловая Idea Extraction, «момент понимания», субъективный
Human Check.

## Качество и вычитка

Юнит-тесты (`tests/`, 393 теста на 2026-07-15) проверяют логику стадий по
отдельности, но исторически **не ловили** структурные дефекты, видимые
только в собранном тексте на реальных данных (title/body mismatch, обрыв
текста, утечка служебных меток источника). Основной способ их находить —
ручная вычитка сгенерированных статей на живых данных БД. Часть этой
вычитки автоматизирована: `adaptation/content_audit.py` + ежедневный job
`scheduler.run_content_audit` сканируют последние посты на уже встречавшиеся
классы дефектов и шлют отчёт админу — это не замена ручной вычитке
(смысловые дефекты по-прежнему ловит только человек), а страховка от
регрессии уже починенных багов.

## Метрики аудитории

Business Model MVP — порядок «Качество → Доверие → Аудитория →
Монетизация» (монетизация прямо не цель текущего этапа). Для проверки
шага «Аудитория» есть `/audience_stats`: реакции на посты
(`bot/reactions.py`, Telegram-событие `message_reaction_count` —
агрегированно, анонимно для каналов) и рост подписчиков
(`scheduler.snapshot_channel_stats`, ежедневный `get_chat_member_count`).
Просмотры и репосты Bot API постфактум не отдаёт — без MTProto-клиента
(Telethon и т.п.) это не измерить, эти метрики сознательно не реализованы,
а не забыты.

## Модульная структура `bot/`

`bot/bot.py` — только диспетчер (`dp`), ленивая инициализация `Bot`,
`is_admin`, `html_escape`. Обработчики разнесены по файлам — см.
[migration/decisions/0001-split-bot-module.md](migration/decisions/0001-split-bot-module.md)
за причиной и результатом разбиения:

- `keyboards.py` — inline-клавиатуры.
- `publishing.py` — публикация статьи, дайджест-кандидаты.
- `callbacks.py` — модерация одиночных черновиков (approve/reject/draft_*).
- `cluster_callbacks.py` — модерация кластерных постов (дайджест по теме).
- `commands.py` — команды (`/start`, `/stats`, `/audience_stats`, `/digest`,
  `/invalidate_cache`, `/help`, `/drafts`).
- `knowledge_commands.py` — команды Knowledge Core (`/knowledge`, `/claims`,
  `/myths`, `/graph`, ...).
- `reactions.py` — учёт реакций на посты.

## Тесты

`ADMIN_ID` читается из окружения при импорте `bot/bot.py` — тесты обязаны
патчить его явно (`patch.object(b, "ADMIN_ID", ADMIN)`), а не полагаться на
переменную окружения (локально/в CI она разная). `patch.object(<module>,
"name", ...)` перехватывает вызов только если функция физически определена
в этом модуле — при переносе обработчика в новый файл нужно перепатчить
тест на новый модуль. Оба урока подробно задокументированы в
`tests/test_bot.py` (docstring класса) и `tests/test_cluster_callbacks.py`.
