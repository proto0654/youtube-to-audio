import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, GROUP_MODE_ENABLED
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
    
    if GROUP_MODE_ENABLED:
        logger.info("Режим групповых чатов ВКЛЮЧЕН")
    else:
        logger.info("Режим групповых чатов ОТКЛЮЧЕН")

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
    
    # Получаем информацию о боте и выводим в лог
    bot_info = await bot.get_me()
    logger.info(f"Бот запущен как @{bot_info.username} (ID: {bot_info.id})")
    
    # Пропуск накопившихся апдейтов и запуск поллинга
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот успешно запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True) 