import logging
from typing import List, Dict, Optional
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats, BotCommandScopeDefault
from config import GROUP_MODE_ENABLED

logger = logging.getLogger(__name__)

async def set_commands(bot: Bot) -> None:
    """
    Регистрирует команды бота в меню Telegram Bot Commands.
    
    Args:
        bot: Экземпляр бота
    """
    # Команды для приватных чатов
    private_commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Показать справку"),
        BotCommand(command="search", description="Поиск музыки на YouTube"),
        BotCommand(command="link", description="Отправить YouTube ссылку")
    ]
    
    # Команды для групповых чатов
    group_commands = [
        BotCommand(command="start", description="Запустить бота в группе"),
        BotCommand(command="help", description="Показать справку по командам"),
        BotCommand(command="search", description="Поиск музыки на YouTube"),
        BotCommand(command="mystate", description="Проверить ваше состояние"),
        BotCommand(command="clearstate", description="Сбросить ваше состояние")
    ]
    
    # Регистрация команд для приватных чатов
    await bot.set_my_commands(
        commands=private_commands,
        scope=BotCommandScopeAllPrivateChats()
    )
    logger.info("Команды для приватных чатов установлены")
    
    # Регистрация команд для групповых чатов, если включен групповой режим
    if GROUP_MODE_ENABLED:
        await bot.set_my_commands(
            commands=group_commands,
            scope=BotCommandScopeAllGroupChats()
        )
        logger.info("Команды для групповых чатов установлены")
    
    # Устанавливаем команды по умолчанию для всех чатов
    default_commands = private_commands if not GROUP_MODE_ENABLED else [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Показать справку"),
        BotCommand(command="search", description="Поиск музыки на YouTube")
    ]
    
    await bot.set_my_commands(
        commands=default_commands,
        scope=BotCommandScopeDefault()
    )
    logger.info("Команды по умолчанию установлены") 