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