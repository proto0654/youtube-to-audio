import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.inline import get_main_keyboard
from handlers.search import SearchStates

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "link")
async def process_link_callback(callback: CallbackQuery):
    """
    Обработчик callback_data="link".
    Просит пользователя прислать ссылку на YouTube видео.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал опцию 'Ссылка'")
    
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
    logger.info(f"Пользователь {user_id} выбрал опцию 'Поиск'")
    
    await callback.answer()
    await callback.message.answer(
        "Введите запрос для поиска музыки в YouTube Music:"
    )
    
    # Устанавливаем состояние ожидания поискового запроса
    await state.set_state(SearchStates.waiting_for_query) 