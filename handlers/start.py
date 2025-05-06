import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ChatType
from keyboards.inline import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение с инлайн-клавиатурой.
    """
    user_name = message.from_user.first_name
    logger.info(f"Пользователь {message.from_user.id} ({user_name}) запустил бота")
    
    text = (
        f"👋 Привет, {user_name}!\n\n"
        f"Я бот для скачивания аудио из YouTube.\n"
        f"Выберите действие:"
    )
    
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("help"), ~F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_help(message: Message):
    """
    Обработчик команды /help для приватных чатов.
    Отправляет справку по командам и функциям бота.
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    logger.info(f"Пользователь {user_id} ({user_name}) запросил справку")
    
    text = (
        f"📚 <b>Справка по командам бота:</b>\n\n"
        f"• <b>/start</b> - Начать работу с ботом\n"
        f"• <b>/help</b> - Показать эту справку\n"
        f"• <b>/search</b> - Поиск музыки по запросу\n"
        f"• <b>/link</b> - Отправить ссылку на YouTube видео\n\n"
        f"Вы также можете использовать интерактивное меню или просто отправить боту ссылку на YouTube видео, и я автоматически скачаю из него аудио.\n\n"
        f"💡 <b>Как использовать бота:</b>\n"
        f"1. Отправьте боту ссылку на видео YouTube\n"
        f"2. Дождитесь загрузки и конвертации (обычно 10-30 секунд)\n"
        f"3. Получите готовый аудиофайл с метаданными\n\n"
        f"🔍 Для поиска музыки используйте команду /search или нажмите кнопку 'Поиск' в меню."
    )
    
    await message.answer(text, reply_markup=get_main_keyboard()) 