# ============================================================
#  main.py — точка входа в Noerra
# ============================================================

import asyncio
import logging
import sys

from database.db import init_db
from scheduler.scheduler import run_pipeline, create_scheduler
from bot.bot import dp, get_bot
from config.settings import LOG_LEVEL, LOG_FILE, PARSE_INTERVAL_MINUTES


def setup_logging():
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        handlers=handlers,
    )


async def main():
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("🚀 Noerra запускается...")

    # 1. Инициализация БД
    init_db()

    # 1.5 Очистка старых некорректных данных
    from database.db import cleanup_invalid_claims_and_questions
    cleanup_stats = cleanup_invalid_claims_and_questions()
    if any(cleanup_stats.values()):
        logger.info(f"🧹 Cleanup: {cleanup_stats}")

    # 2. Запускаем бота и пайплайн параллельно
    scheduler = create_scheduler()
    scheduler.start()
    logger.info(f"Планировщик запущен: каждые {PARSE_INTERVAL_MINUTES} мин")

    async def pipeline_task():
        # Первый запуск пайплайна (run_pipeline сам использует to_thread внутри)
        logger.info("Первый запуск пайплайна...")
        try:
            await run_pipeline()
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")

    # Запускаем пайплайн в фоне, бот стартует сразу
    asyncio.create_task(pipeline_task())

    # Бот слушает команды и кнопки (основной цикл)
    logger.info("Бот запущен, слушаю кнопки и команды...")
    try:
        await dp.start_polling(get_bot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка по команде пользователя...")
    except asyncio.CancelledError:
        # CancelledError НЕ наследуется от Exception (начиная с Python 3.8),
        # поэтому его нужно ловить отдельно — иначе он пролетает мимо except
        # Exception ниже и всплывает уже наверху, в asyncio.run(), пугающим
        # трейсбеком, хотя реальное завершение к этому моменту уже прошло штатно.
        logger.info("Опрос отменён (сетевой сбой или отмена задачи).")
    except Exception as e:
        # Раньше сюда попадали, например, сетевые обрывы (TelegramNetworkError) —
        # они не относятся к KeyboardInterrupt/SystemExit, поэтому проскакивали
        # мимо except выше прямо в finally, а там stop_polling() падал повторно
        # с "Polling is not started", и настоящая причина терялась в трейсбеке.
        logger.error(f"Бот остановлен из-за ошибки: {e}")
    finally:
        scheduler.shutdown()
        try:
            await dp.stop_polling()
        except RuntimeError:
            # polling уже остановлен сам (например, из-за сетевой ошибки выше) —
            # это ожидаемо и не является дополнительной проблемой
            pass
        await get_bot().session.close()
        logger.info("Noerra остановлена")


if __name__ == "__main__":
    asyncio.run(main())