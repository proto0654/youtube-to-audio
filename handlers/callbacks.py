import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatType
from keyboards.inline import get_main_keyboard
from handlers.search import SearchStates
from services.user_state import user_state_manager
from config import GROUP_MODE_ENABLED, TOPICS_MODE_ENABLED, is_allowed_chat

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "link")
async def process_link_callback(callback: CallbackQuery):
    """
    Обработчик callback_data="link".
    Просит пользователя прислать ссылку на YouTube видео.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    logger.info(f"Пользователь {user_id} выбрал опцию 'Ссылка' в чате {chat_id} (топик: {topic_id})")
    
    await callback.answer()
    await callback.message.answer(
        "Пришлите ссылку на YouTube видео, и я скачаю из него аудио."
    )

@router.callback_query(F.data == "search")
async def process_search_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик callback_data="search".
    Предлагает пользователю ввести поисковый запрос для поиска музыки.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    logger.info(f"Пользователь {user_id} выбрал опцию 'Поиск' в чате {chat_id} (топик: {topic_id})")
    
    # Проверяем тип чата
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # В групповом чате используем локальный менеджер состояний
        user_state_manager.set_user_waiting_for_query(user_id, True, chat_id, topic_id)
        await callback.answer()
        await callback.message.answer(
            f"{callback.from_user.first_name}, введите запрос для поиска музыки в YouTube Music:"
        )
    else:
        # В приватном чате используем FSM
        await callback.answer()
        await callback.message.answer(
            "Введите запрос для поиска музыки в YouTube Music:"
        )
        # Устанавливаем состояние ожидания поискового запроса
        await state.set_state(SearchStates.waiting_for_query)

@router.callback_query(F.data == "back_to_main")
async def process_back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик callback_data="back_to_main".
    Возвращает пользователя в главное меню и очищает состояние.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    logger.info(f"Пользователь {user_id} вернулся в главное меню в чате {chat_id} (топик: {topic_id})")
    
    # Проверяем тип чата
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # Очищаем состояние в локальном менеджере
        user_state_manager.clear_user_state(user_id, None, chat_id, topic_id)
    else:
        # Очищаем состояние FSM
        await state.clear()
    
    await callback.answer()
    
    # Редактируем текущее сообщение
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    ) 