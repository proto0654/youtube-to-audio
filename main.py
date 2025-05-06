import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import routers
from services.youtube import force_cleanup_downloads_folder

# Настройка логирования
logger = logging.getLogger(__name__)

async def main():
    """
    Основная функция запуска бота.
    Инициализирует бота, диспетчер и регистрирует все роутеры.
    """
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    logger.info("Запуск бота...")

    # Принудительная очистка папки загрузок при запуске
    force_cleanup_downloads_folder()
    logger.info("Директория загрузок полностью очищена")

    # Создание экземпляров бота и диспетчера с использованием нового синтаксиса для DefaultBotProperties
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создаем хранилище для FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрация всех роутеров
    for router in routers:
        dp.include_router(router)
    
    # Пропуск накопившихся апдейтов и запуск поллинга
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот успешно запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True) 