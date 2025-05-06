import logging
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandObject, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import ChatMemberUpdated
from aiogram.filters.chat_member_updated import JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.enums import ChatType

from config import GROUP_MODE_ENABLED, DIRECT_PROCESS_YOUTUBE_LINKS, MAX_REQUESTS_PER_USER
from config import TOPICS_MODE_ENABLED, is_allowed_chat
from keyboards.inline import get_main_keyboard
from services.user_state import user_state_manager
from services.youtube import download_audio_from_youtube, search_youtube_music
from handlers.link_handler import process_youtube_link
from handlers.search import SearchPagination, display_search_results_page

logger = logging.getLogger(__name__)
router = Router()

# Регулярное выражение для проверки YouTube ссылок
YOUTUBE_REGEX = r"(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=)?([^\s&]+)"

@router.message(Command("start"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_start_group(message: Message):
    """
    Обработчик команды /start для групповых чатов.
    """
    if not GROUP_MODE_ENABLED:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    chat_name = message.chat.title
    topic_id = message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if not is_allowed_chat(chat_id, topic_id):
        logger.info(f"Команда /start отклонена в группе {chat_name} (ID: {chat_id}, топик: {topic_id}) от пользователя {user_id}")
        return
    
    logger.info(f"Команда /start в группе {chat_name} (ID: {chat_id}, топик: {topic_id}) от пользователя {user_id} ({user_name})")
    
    topic_info = f" в топике {topic_id}" if topic_id is not None else ""
    text = (
        f"👋 Привет! Я бот для скачивания аудио из YouTube.\n\n"
        f"В групповом чате{topic_info} я работаю так:\n"
        f"• Пришлите мне ссылку на YouTube видео, и я скачаю из него аудио\n"
        f"• Используйте команду /search для поиска музыки\n"
        f"• Используйте команду /help для получения справки"
    )
    
    await message.answer(text)

@router.message(Command("help"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_help_group(message: Message):
    """
    Обработчик команды /help для групповых чатов.
    """
    if not GROUP_MODE_ENABLED:
        return
    
    chat_id = message.chat.id
    topic_id = message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if not is_allowed_chat(chat_id, topic_id):
        return
    
    topic_info = f" в топике {topic_id}" if topic_id is not None else ""
    text = (
        f"📚 <b>Справка по командам бота{topic_info}:</b>\n\n"
        f"• <b>/start</b> - Начать работу с ботом\n"
        f"• <b>/help</b> - Показать эту справку\n"
        f"• <b>/search [запрос]</b> - Поиск музыки по запросу\n"
        f"• <b>/mystate</b> - Проверить ваше текущее состояние\n"
        f"• <b>/clearstate</b> - Сбросить ваше состояние\n\n"
        f"Также вы можете просто отправить ссылку на YouTube видео, и я автоматически скачаю из него аудио."
    )
    
    await message.answer(text)

@router.message(Command("search"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_search_group(message: Message, command: CommandObject):
    """
    Обработчик команды /search для групповых чатов.
    Принимает поисковый запрос как аргумент или устанавливает ожидание запроса.
    """
    if not GROUP_MODE_ENABLED:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    topic_id = message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if not is_allowed_chat(chat_id, topic_id):
        return
    
    # Проверяем, не превышено ли ограничение на запросы
    if user_state_manager.get_user_requests_count(user_id) >= MAX_REQUESTS_PER_USER:
        await message.reply(
            f"⚠️ Превышено ограничение на количество запросов (максимум {MAX_REQUESTS_PER_USER} запросов в час).\n"
            f"Пожалуйста, попробуйте позже."
        )
        return
    
    # Сбрасываем предыдущее состояние просмотра результатов для этого пользователя
    # Это позволит начать новый поиск даже если предыдущий не был завершен выбором трека
    user_state_manager.set_user_browsing_results(user_id, False, None, chat_id, topic_id)
    
    # Если есть аргумент, используем его как запрос
    if command.args:
        query = command.args.strip()
        logger.info(f"Пользователь {user_id} ({user_name}) отправил поисковый запрос в группе {chat_id} (топик: {topic_id}): {query}")
        
        # Минимальная длина запроса
        if len(query) < 3:
            await message.reply("Пожалуйста, введите запрос длиной не менее 3 символов.")
            return
        
        # Увеличиваем счетчик запросов пользователя
        user_state_manager.increment_user_requests(user_id)
        
        # Отправка сообщения о начале поиска
        loading_message = await message.reply("🔍 Ищу музыку, пожалуйста, подождите...")
        
        try:
            # Выполнение поиска в YouTube Music
            results = await search_youtube_music(query, limit=0)
            
            # Удаление сообщения о загрузке
            await loading_message.delete()
            
            if not results:
                await message.reply(
                    f"🔍 По запросу <b>{query}</b> музыка не найдена.\n\n"
                    f"Рекомендации:\n"
                    f"✓ Попробуйте более точный запрос\n"
                    f"✓ Укажите имя исполнителя и название трека\n"
                    f"✓ Используйте английские ключевые слова\n"
                    f"✓ Проверьте правильность написания"
                )
                return
            
            # Создаем объект пагинации и сохраняем его в состоянии
            pagination = SearchPagination(results=results, query=query, page=0)
            user_state_manager.set_user_browsing_results(user_id, True, pagination.__dict__, chat_id, topic_id)
            
            # Отображаем первую страницу результатов
            await display_search_results_page(message, pagination, is_reply=True)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке поискового запроса в группе: {e}")
            await loading_message.delete()
            await message.reply(
                f"Произошла ошибка при поиске музыки. Пожалуйста, попробуйте позже или используйте прямую ссылку на YouTube."
            )
    else:
        # Если аргумента нет, устанавливаем состояние ожидания запроса
        user_state_manager.set_user_waiting_for_query(user_id, True, chat_id, topic_id)
        await message.reply(
            f"{user_name}, введите запрос для поиска музыки в YouTube Music:"
        )

@router.message(Command("mystate"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_mystate_group(message: Message):
    """
    Показывает текущее состояние пользователя.
    """
    if not GROUP_MODE_ENABLED:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    topic_id = message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if not is_allowed_chat(chat_id, topic_id):
        return
    
    waiting_for_query = user_state_manager.is_user_waiting_for_query(user_id, chat_id, topic_id)
    browsing_results = user_state_manager.is_user_browsing_results(user_id, chat_id, topic_id)
    requests_count = user_state_manager.get_user_requests_count(user_id)
    
    topic_info = f" в топике {topic_id}" if topic_id is not None else ""
    status_text = (
        f"🔄 <b>Текущее состояние для {user_name}{topic_info}:</b>\n\n"
        f"• Ожидание поискового запроса: {'✅' if waiting_for_query else '❌'}\n"
        f"• Просмотр результатов поиска: {'✅' if browsing_results else '❌'}\n"
        f"• Использовано запросов: {requests_count}/{MAX_REQUESTS_PER_USER} за последний час"
    )
    
    await message.reply(status_text)

@router.message(Command("clearstate"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_clearstate_group(message: Message):
    """
    Сбрасывает текущее состояние пользователя.
    """
    if not GROUP_MODE_ENABLED:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    topic_id = message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if not is_allowed_chat(chat_id, topic_id):
        return
    
    user_state_manager.clear_user_state(user_id, None, chat_id, topic_id)
    logger.info(f"Сброшено состояние пользователя {user_id} ({user_name}) в чате {chat_id} (топик: {topic_id})")
    
    topic_info = f" в топике {topic_id}" if topic_id is not None else ""
    await message.reply(f"✅ {user_name}, ваши состояния{topic_info} сброшены.")

@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_group_message(message: Message):
    """
    Общий обработчик сообщений в групповом чате.
    Проверяет различные условия и перенаправляет обработку соответствующим функциям.
    """
    if not GROUP_MODE_ENABLED:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    topic_id = message.message_thread_id if TOPICS_MODE_ENABLED else None
    text = message.text or message.caption or ""
    
    # Проверяем, разрешен ли этот чат/топик
    if not is_allowed_chat(chat_id, topic_id):
        return
    
    # Если пользователь ожидает ввода поискового запроса
    if user_state_manager.is_user_waiting_for_query(user_id, chat_id, topic_id):
        query = text.strip()
        logger.info(f"Пользователь {user_id} ({user_name}) отправил поисковый запрос в группе {chat_id} (топик: {topic_id}): {query}")
        
        # Сбрасываем состояние ожидания
        user_state_manager.set_user_waiting_for_query(user_id, False, chat_id, topic_id)
        
        # Сбрасываем предыдущее состояние просмотра результатов
        user_state_manager.set_user_browsing_results(user_id, False, None, chat_id, topic_id)
        
        # Минимальная длина запроса
        if len(query) < 3:
            await message.reply("Пожалуйста, введите запрос длиной не менее 3 символов.")
            return
        
        # Увеличиваем счетчик запросов пользователя
        user_state_manager.increment_user_requests(user_id)
        
        # Отправка сообщения о начале поиска
        loading_message = await message.reply("🔍 Ищу музыку, пожалуйста, подождите...")
        
        try:
            # Выполнение поиска в YouTube Music
            results = await search_youtube_music(query, limit=0)
            
            # Удаление сообщения о загрузке
            await loading_message.delete()
            
            if not results:
                await message.reply(
                    f"🔍 По запросу <b>{query}</b> музыка не найдена.\n\n"
                    f"Рекомендации:\n"
                    f"✓ Попробуйте более точный запрос\n"
                    f"✓ Укажите имя исполнителя и название трека\n"
                    f"✓ Используйте английские ключевые слова\n"
                    f"✓ Проверьте правильность написания"
                )
                return
            
            # Создаем объект пагинации и сохраняем его в состоянии
            pagination = SearchPagination(results=results, query=query, page=0)
            user_state_manager.set_user_browsing_results(user_id, True, pagination.__dict__, chat_id, topic_id)
            
            # Отображаем первую страницу результатов
            await display_search_results_page(message, pagination, is_reply=True)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке поискового запроса в группе: {e}")
            await loading_message.delete()
            await message.reply(
                f"Произошла ошибка при поиске музыки. Пожалуйста, попробуйте позже или используйте прямую ссылку на YouTube."
            )
        return
    
    # Проверяем наличие YouTube ссылки в тексте сообщения
    youtube_match = re.search(YOUTUBE_REGEX, text)
    if youtube_match and DIRECT_PROCESS_YOUTUBE_LINKS:
        # Проверяем, не превышено ли ограничение на запросы
        if user_state_manager.get_user_requests_count(user_id) >= MAX_REQUESTS_PER_USER:
            await message.reply(
                f"⚠️ Превышено ограничение на количество запросов (максимум {MAX_REQUESTS_PER_USER} запросов в час).\n"
                f"Пожалуйста, попробуйте позже."
            )
            return
        
        # Увеличиваем счетчик запросов пользователя
        user_state_manager.increment_user_requests(user_id)
        
        # Обработка YouTube ссылки
        url = youtube_match.group(0)
        logger.info(f"Обнаружена YouTube ссылка в группе {chat_id} (топик: {topic_id}) от пользователя {user_id} ({user_name}): {url}")
        
        # Используем существующую функцию для обработки YouTube ссылки
        # Передаем дополнительные параметры
        await process_youtube_link(message, is_group_chat=True, topic_id=topic_id)
        
        return

# Обработчик присоединения бота к группе
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added_to_group(event: ChatMemberUpdated):
    """
    Обрабатывает событие добавления бота в группу.
    """
    if not GROUP_MODE_ENABLED:
        return
    
    if event.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        chat_id = event.chat.id
        chat_name = event.chat.title
        added_by = event.from_user.full_name
        
        # Проверяем, разрешена ли эта группа
        if not is_allowed_chat(chat_id):
            logger.info(f"Бот добавлен в неразрешенную группу {chat_name} (ID: {chat_id}) пользователем {added_by}. Доступ ограничен.")
            return
        
        logger.info(f"Бот добавлен в группу {chat_name} (ID: {chat_id}) пользователем {added_by}")
        
        # Определяем, поддерживает ли группа топики
        supports_topics = hasattr(event.chat, 'is_forum') and event.chat.is_forum
        topic_info = ""
        if supports_topics and TOPICS_MODE_ENABLED:
            topic_info = "\n\nЭта группа поддерживает топики. Вы можете использовать меня в разных топиках!"
        
        await event.chat.send_message(
            f"👋 Привет всем в группе <b>{chat_name}</b>!\n\n"
            f"Я бот для скачивания аудио из YouTube. Теперь я буду работать в этой группе.\n\n"
            f"Вы можете:\n"
            f"• Прислать мне ссылку на YouTube видео, и я скачаю из него аудио\n"
            f"• Использовать команду /search для поиска музыки\n"
            f"• Использовать команду /help для получения справки{topic_info}\n\n"
            f"Рад быть полезным! 🎵"
        )

# Обработчик удаления бота из группы
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def bot_removed_from_group(event: ChatMemberUpdated):
    """
    Обрабатывает событие удаления бота из группы.
    """
    if event.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        chat_id = event.chat.id
        chat_name = event.chat.title
        removed_by = event.from_user.full_name
        logger.info(f"Бот удален из группы {chat_name} (ID: {chat_id}) пользователем {removed_by}")
        
        # Здесь можно добавить логику очистки данных, связанных с этой группой 