import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Получение переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_MODE_ENABLED = os.getenv("GROUP_MODE_ENABLED", "false").lower() == "true"
TOPICS_MODE_ENABLED = os.getenv("TOPICS_MODE_ENABLED", "false").lower() == "true"

# Настройка логирования
logger = logging.getLogger(__name__)

# Импорт базовых системных модулей
from services.youtube import force_cleanup_downloads_folder

async def set_commands(bot):
    """Установка команд бота для меню"""
    from aiogram.types import BotCommand
    
    # Команды для приватных чатов
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь по боту"),
        BotCommand(command="search", description="Поиск на YouTube"),
    ])
    
    logger.info("Команды бота установлены")

async def process_youtube_link(update, bot):
    """Обработка YouTube ссылки"""
    chat_id = update.chat.id
    message_id = update.message_id
    from_user_id = update.from_user.id
    from_user_name = update.from_user.full_name
    
    # Получение ссылки из сообщения
    text = update.text
    
    # Простая проверка на YouTube ссылку
    if "youtube.com" in text or "youtu.be" in text:
        logger.info(f"Обнаружена YouTube ссылка от пользователя {from_user_id} ({from_user_name}): {text}")
        
        # Отправка сообщения о начале обработки
        await bot.send_message(
            chat_id=chat_id, 
            text=f"Начинаю загрузку аудио из YouTube...",
            reply_to_message_id=message_id
        )
        
        # Имитация загрузки аудио
        await asyncio.sleep(2)
        
        # Отправка сообщения об успешной загрузке
        await bot.send_message(
            chat_id=chat_id,
            text="Аудио успешно загружено! В реальной версии бота здесь будет отправлен аудиофайл.",
            reply_to_message_id=message_id
        )

async def main():
    """
    Основная функция запуска бота.
    Инициализирует бота, диспетчер и регистрирует все обработчики.
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
        
    if TOPICS_MODE_ENABLED:
        logger.info("Режим топиков ВКЛЮЧЕН")
    else:
        logger.info("Режим топиков ОТКЛЮЧЕН")

    # Принудительная очистка папки загрузок при запуске
    try:
        force_cleanup_downloads_folder()
        logger.info("Директория загрузок полностью очищена")
    except Exception as e:
        logger.error(f"Ошибка при очистке директории загрузок: {e}")

    # Создание экземпляра бота
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создаем хранилище для FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Обработка команды /start
    @dp.message()
    async def message_handler(message, bot):
        if message.text == "/start":
            await bot.send_message(
                chat_id=message.chat.id,
                text=f"Привет, {message.from_user.first_name}! Я бот для скачивания аудио с YouTube. "
                     f"Просто отправь мне ссылку на видео, и я конвертирую его в аудиофайл."
            )
        elif message.text and ("youtube.com" in message.text or "youtu.be" in message.text):
            await process_youtube_link(message, bot)
    
    # Установка команд бота
    await set_commands(bot)
    
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