import logging
import os
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType

from keyboards.inline import get_main_keyboard
from services.youtube import search_youtube_music, download_audio_from_youtube, MAX_TELEGRAM_FILE_SIZE
from services.user_state import user_state_manager
from config import GROUP_MODE_ENABLED, TOPICS_MODE_ENABLED, is_allowed_chat

logger = logging.getLogger(__name__)
router = Router()

# В начале файла, добавить класс для хранения состояния пагинации
class SearchPagination:
    """Класс для хранения состояния пагинации результатов поиска"""
    def __init__(self, results=None, query="", page=0, per_page=10):
        self.results = results or []
        self.query = query
        self.page = page
        self.per_page = per_page
        
    def get_page_results(self):
        """Возвращает результаты для текущей страницы"""
        start = self.page * self.per_page
        end = start + self.per_page
        return self.results[start:end]
    
    def has_next_page(self):
        """Проверяет, есть ли следующая страница"""
        return (self.page + 1) * self.per_page < len(self.results)
    
    def has_prev_page(self):
        """Проверяет, есть ли предыдущая страница"""
        return self.page > 0
    
    def total_pages(self):
        """Возвращает общее количество страниц"""
        return (len(self.results) + self.per_page - 1) // self.per_page
    
    def total_results(self):
        """Возвращает общее количество результатов"""
        return len(self.results)

# Машина состояний для поиска
class SearchStates(StatesGroup):
    waiting_for_query = State()
    browsing_results = State()  # Новое состояние для просмотра результатов

@router.message(SearchStates.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    """
    Обработчик поискового запроса.
    Выполняет поиск и отображает результаты.
    """
    query = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} отправил поисковый запрос: {query}")
    
    # Минимальная длина запроса
    if len(query) < 3:
        await message.answer(
            "Пожалуйста, введите запрос длиной не менее 3 символов.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        return
    
    # Отправка сообщения о начале поиска
    loading_message = await message.answer("🔍 Ищу музыку, пожалуйста, подождите...")
    
    try:
        # Выполнение поиска в YouTube Music без ограничения количества результатов
        results = await search_youtube_music(query, limit=0)
        
        # Удаление сообщения о загрузке
        await loading_message.delete()
        
        if not results:
            # Предлагаем альтернативные варианты поиска
            suggestions = []
            # Добавляем варианты для русскоязычных запросов
            if not any(char.isascii() for char in query):
                # Полностью русскоязычный запрос - предлагаем добавить "музыка" или "песня"
                if "музыка" not in query.lower() and "песня" not in query.lower():
                    suggestions.append(f"{query} музыка")
                    suggestions.append(f"{query} песня")
            else:
                # Добавляем 'music' для поиска на английском
                if "music" not in query.lower():
                    suggestions.append(f"{query} music")
            
            suggestion_buttons = []
            for suggestion in suggestions:
                suggestion_buttons.append([
                    InlineKeyboardButton(
                        text=f"🔍 {suggestion}",
                        callback_data=f"search_query:{suggestion}"
                    )
                ])
            
            # Добавляем кнопку возврата в меню
            suggestion_buttons.append([
                InlineKeyboardButton(text="↩️ К меню", callback_data="back_to_main")
            ])
            
            suggestion_markup = InlineKeyboardMarkup(inline_keyboard=suggestion_buttons) if suggestion_buttons else get_main_keyboard()
            
            await message.answer(
                f"🔍 По запросу <b>{query}</b> музыка не найдена.\n\n"
                f"Рекомендации:\n"
                f"✓ Попробуйте более точный запрос\n"
                f"✓ Укажите имя исполнителя и название трека\n"
                f"✓ Используйте английские ключевые слова\n"
                f"✓ Проверьте правильность написания",
                reply_markup=suggestion_markup
            )
            await state.clear()
            return
        
        # Создаем объект пагинации и сохраняем его в состоянии
        pagination = SearchPagination(results=results, query=query, page=0)
        await state.update_data(pagination=pagination.__dict__)
        await state.set_state(SearchStates.browsing_results)
        
        # Отображаем первую страницу результатов
        await display_search_results_page(message, pagination)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке поискового запроса: {e}")
        await loading_message.delete()
        await message.answer(
            f"Произошла ошибка при поиске музыки. Пожалуйста, попробуйте позже или используйте прямую ссылку на YouTube.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()

# Обновляем функцию для отображения страницы результатов
async def display_search_results_page(message_or_callback, pagination, edit_message=False, is_reply=False):
    """
    Отображает страницу результатов поиска.
    
    Args:
        message_or_callback: Объект Message или CallbackQuery
        pagination: Объект пагинации
        edit_message: Редактировать ли существующее сообщение (для CallbackQuery)
        is_reply: Отправлять ли результаты как ответ на сообщение (для групповых чатов)
    """
    # Получаем результаты для текущей страницы
    page_results = pagination.get_page_results()
    
    # Формируем текст сообщения
    text = f"🎵 Музыка по запросу <b>{pagination.query}</b> "
    text += f"(страница {pagination.page + 1}/{pagination.total_pages() or 1}, "
    text += f"всего найдено: {pagination.total_results()}):\n\n"
    
    # Добавляем результаты
    keyboards = []
    for i, result in enumerate(page_results, 1):
        title = result['title']
        artist = result['artist']
        duration = result['duration']
        result_type = result.get('type', 'song')
        
        # Номер результата на глобальном уровне (с учетом страницы)
        result_num = i + pagination.page * pagination.per_page
        
        # Добавляем иконку в зависимости от типа результата
        icon = "🎵" if result_type == "song" else "🎬"
        
        # Полное название для отображения в сообщении
        text += f"{result_num}. {icon} <b>{title}</b> - {artist} ({duration})\n"
        
        # Создаем кнопку для скачивания с тем же номером, что и в списке
        download_text = f"⬇️ {result_num}. {title}"
        keyboards.append([
            InlineKeyboardButton(
                text=download_text,
                callback_data=f"download:{result['videoId']}"
            )
        ])
    
    # Добавляем кнопки навигации
    navigation_buttons = []
    
    if pagination.has_prev_page():
        navigation_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="search_prev_page"
            )
        )
    
    if pagination.has_next_page():
        navigation_buttons.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data="search_next_page"
            )
        )
    
    # Добавляем кнопки навигации, если они есть
    if navigation_buttons:
        keyboards.append(navigation_buttons)
    
    # Добавляем кнопки для нового поиска и возврата в меню
    keyboards.append([
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search"),
        InlineKeyboardButton(text="↩️ К меню", callback_data="back_to_main")
    ])
    
    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboards)
    
    # Отправляем результаты
    if isinstance(message_or_callback, CallbackQuery):
        # Для CallbackQuery
        if edit_message:
            await message_or_callback.message.edit_text(text, reply_markup=keyboard)
        else:
            await message_or_callback.message.answer(text, reply_markup=keyboard)
        await message_or_callback.answer()
    else:
        # Для Message
        if is_reply:
            # Отправляем сообщение как ответ (для группового чата)
            await message_or_callback.reply(text, reply_markup=keyboard)
        else:
            # Обычная отправка сообщения
            await message_or_callback.answer(text, reply_markup=keyboard)

# Обработчики для навигации по страницам
@router.callback_query(F.data == "search_next_page")
async def process_next_page(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Следующая страница" результатов поиска.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Выбираем источник данных в зависимости от типа чата
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # Для группового чата используем локальный менеджер состояний
        if not user_state_manager.is_user_browsing_results(user_id, chat_id, topic_id):
            await callback.answer("Поиск не найден. Пожалуйста, начните новый поиск.")
            return
            
        pagination_data = user_state_manager.get_user_state(user_id, "search_results", {}, chat_id, topic_id)
        pagination = SearchPagination(**pagination_data)
        pagination.page += 1
        user_state_manager.set_user_state(user_id, "search_results", pagination.__dict__, chat_id, topic_id)
    else:
        # Для приватного чата используем FSM
        data = await state.get_data()
        if 'pagination' not in data:
            await callback.answer("Поиск не найден. Пожалуйста, начните новый поиск.")
            return
            
        pagination = SearchPagination(**data['pagination'])
        pagination.page += 1
        await state.update_data(pagination=pagination.__dict__)
    
    # Отображаем следующую страницу
    await display_search_results_page(callback, pagination, edit_message=True)

@router.callback_query(F.data == "search_prev_page")
async def process_prev_page(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Предыдущая страница" результатов поиска.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Выбираем источник данных в зависимости от типа чата
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # Для группового чата используем локальный менеджер состояний
        if not user_state_manager.is_user_browsing_results(user_id, chat_id, topic_id):
            await callback.answer("Поиск не найден. Пожалуйста, начните новый поиск.")
            return
            
        pagination_data = user_state_manager.get_user_state(user_id, "search_results", {}, chat_id, topic_id)
        pagination = SearchPagination(**pagination_data)
        pagination.page -= 1
        user_state_manager.set_user_state(user_id, "search_results", pagination.__dict__, chat_id, topic_id)
    else:
        # Для приватного чата используем FSM
        data = await state.get_data()
        if 'pagination' not in data:
            await callback.answer("Поиск не найден. Пожалуйста, начните новый поиск.")
            return
            
        pagination = SearchPagination(**data['pagination'])
        pagination.page -= 1
        await state.update_data(pagination=pagination.__dict__)
    
    # Отображаем предыдущую страницу
    await display_search_results_page(callback, pagination, edit_message=True)

@router.callback_query(F.data == "new_search")
async def process_new_search_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Новый поиск".
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Проверяем тип чата
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # В групповом чате используем локальный менеджер состояний
        user_state_manager.set_user_waiting_for_query(user_id, True, chat_id, topic_id)
        user_state_manager.set_user_browsing_results(user_id, False, None, chat_id, topic_id)
        
        await callback.answer()
        await callback.message.answer(
            f"{callback.from_user.first_name}, введите запрос для поиска музыки:"
        )
    else:
        # В приватном чате используем FSM
        await callback.answer()
        await callback.message.answer(
            "Введите запрос для поиска музыки:"
        )
        await state.set_state(SearchStates.waiting_for_query)

@router.callback_query(F.data.startswith("search_query:"))
async def process_search_suggestion(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик выбора предложенного поискового запроса.
    """
    query = callback.data.split(":")[1]
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал предложенный запрос: {query}")
    
    await callback.answer()
    
    # Отправка сообщения о начале поиска
    loading_message = await callback.message.answer("🔍 Ищу музыку, пожалуйста, подождите...")
    
    try:
        # Выполнение поиска в YouTube Music без ограничения количества результатов
        results = await search_youtube_music(query, limit=0)
        
        # Удаление сообщения о загрузке
        await loading_message.delete()
        
        if not results:
            await callback.message.answer(
                f"🔍 По запросу <b>{query}</b> музыка не найдена.\n\n"
                f"Попробуйте другой запрос или используйте прямую ссылку на YouTube.",
                reply_markup=get_main_keyboard()
            )
            await state.clear()
            return
        
        # Создаем объект пагинации и сохраняем его в состоянии
        pagination = SearchPagination(results=results, query=query, page=0)
        await state.update_data(pagination=pagination.__dict__)
        await state.set_state(SearchStates.browsing_results)
        
        # Отображаем первую страницу результатов
        await display_search_results_page(callback, pagination)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке поискового запроса: {e}")
        await loading_message.delete()
        await callback.message.answer(
            f"Произошла ошибка при поиске музыки. Пожалуйста, попробуйте позже или используйте прямую ссылку на YouTube.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()

@router.callback_query(F.data.startswith("download:"))
async def process_download_callback(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку скачивания трека из результатов поиска.
    """
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    chat_type = callback.message.chat.type
    is_group_chat = chat_type in {ChatType.GROUP, ChatType.SUPERGROUP}
    
    # Извлекаем ID видео из callback_data
    video_id = callback.data.split(":", 1)[1]
    logger.info(f"Пользователь {user_id} ({user_name}) выбрал для скачивания видео: {video_id}")
    
    # Формируем URL для скачивания
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    # Отправляем уведомление о начале загрузки
    await callback.answer("Начинаю загрузку аудио...")
    
    # Отправляем сообщение о начале загрузки
    loading_message = await (callback.message.reply if is_group_chat else callback.message.answer)(
        "⏳ <b>Загружаю аудио...</b>\n\n"
        "• Получение информации о треке\n"
        "• Выбор аудиопотока\n"
        "• Загрузка и конвертация\n\n"
        "<i>Пожалуйста, подождите. Это может занять 10-30 секунд...</i>"
    )
    
    try:
        # Скачивание аудио и получение метаданных
        try:
            download_result = await download_audio_from_youtube(url)
            # Убедимся, что у нас есть кортеж с тремя элементами
            if isinstance(download_result, tuple) and len(download_result) == 3:
                file_path, metadata, thumb_path = download_result
            else:
                # Если результат имеет неверный формат, используем значения по умолчанию
                file_path = download_result[0] if isinstance(download_result, tuple) and len(download_result) > 0 else None
                metadata = download_result[1] if isinstance(download_result, tuple) and len(download_result) > 1 else {}
                thumb_path = download_result[2] if isinstance(download_result, tuple) and len(download_result) > 2 else None
                logger.warning(f"Неожиданный формат результата download_audio_from_youtube: {download_result}")
        except Exception as download_error:
            logger.error(f"Ошибка при загрузке аудио: {download_error}")
            await loading_message.delete()
            await (callback.message.reply if is_group_chat else callback.message.answer)(
                f"❌ <b>Ошибка при загрузке аудио</b>\n\n"
                f"Причина: {str(download_error)}\n\n"
                f"Пожалуйста, попробуйте другой трек или используйте прямую ссылку на YouTube.",
                reply_markup=get_main_keyboard()
            )
            return
        
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
            
        file_size = os.path.getsize(file_path)
        
        # Подготавливаем метаданные для отправки
        title = metadata.get('title', 'Unknown Title')
        artist = metadata.get('artist', 'Unknown Artist')
        album = metadata.get('album', 'YouTube Audio')
        duration = metadata.get('duration', None)
        
        # Генерируем понятное название аудиофайла
        display_title = f"{artist} - {title}" if artist and artist != 'Unknown Artist' else title
        
        # Добавляем информацию об отправителе для группового чата
        sender_info = f"Запрос от: {user_name}\n" if is_group_chat else ""
        
        # Проверяем размер файла
        if file_size > MAX_TELEGRAM_FILE_SIZE:
            await loading_message.delete()
            await (callback.message.reply if is_group_chat else callback.message.answer)(
                f"⚠️ <b>Файл слишком большой для отправки</b>\n\n"
                f"{sender_info}"
                f"Размер файла: <b>{file_size / 1024 / 1024:.1f} МБ</b>\n"
                f"Лимит Telegram: <b>50 МБ</b>\n\n"
                f"Попробуйте трек с меньшей длительностью.",
                reply_markup=get_main_keyboard()
            )
            # Удаляем файл
            os.remove(file_path)
            return
        
        # Информативное сообщение о готовности аудио
        await loading_message.edit_text(
            f"✅ <b>Аудио готово к отправке!</b>\n\n"
            f"{sender_info}"
            f"<b>Трек:</b> {title}\n"
            f"<b>Исполнитель:</b> {artist}\n"
            f"<b>Размер файла:</b> <b>{file_size / 1024 / 1024:.1f} МБ</b>\n\n"
            "<i>Отправляю файл...</i>"
        )
        
        # Создаем FSInputFile вместо открытия файла напрямую
        audio_file = FSInputFile(file_path)
        
        # Подготавливаем обложку для Telegram, если она есть
        thumbnail = None
        if thumb_path and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            thumbnail = FSInputFile(thumb_path)
            logger.info(f"Подготовлена обложка для Telegram: {thumb_path}")
        
        # Отправляем аудио пользователю
        caption = (
            f"Аудио успешно загружено\n"
            f"Запрос от: Пользователь {user_name}"
        )
        
        await callback.message.reply_audio(
            audio=audio_file,
            caption=caption,
            title=metadata.get('title', 'Unknown Title'),
            performer=metadata.get('artist', 'Unknown Artist'),
            duration=int(metadata.get('duration_sec', 0)),
            thumbnail=thumbnail,
            reply_to_message_id=None if chat_type in ['group', 'supergroup'] else callback.message.message_id,
            parse_mode="HTML"
        )
        
        # Удаление сообщения о загрузке
        await loading_message.delete()
        
        # Удаление файла после отправки
        try:
            # Попытка удаления аудиофайла с повторными попытками
            file_deleted = False
            for attempt in range(5):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Файл {file_path} успешно отправлен и удален")
                        file_deleted = True
                        break
                    else:
                        logger.warning(f"Файл {file_path} не найден для удаления")
                        file_deleted = True
                        break
                except PermissionError:
                    # Если файл заблокирован, ждем немного и пробуем снова
                    logger.warning(f"Файл {file_path} заблокирован, попытка {attempt+1}/5")
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Не удалось удалить файл {file_path}: {e}")
                    break
            
            if not file_deleted:
                logger.warning(f"Не удалось удалить файл {file_path} после 5 попыток")
            
            # Удаляем обложку, если она существует
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                    logger.info(f"Файл обложки {thumb_path} удален")
                except Exception as e:
                    logger.warning(f"Не удалось удалить файл обложки {thumb_path}: {e}")
        except Exception as e:
            logger.warning(f"Ошибка при очистке файлов: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса на скачивание: {e}")
        await loading_message.delete()
        await (callback.message.reply if is_group_chat else callback.message.answer)(
            f"❌ <b>Ошибка при загрузке аудио</b>\n\n"
            f"Причина: {str(e)}\n\n"
            f"Пожалуйста, попробуйте другой трек или используйте прямую ссылку на YouTube.",
            reply_markup=get_main_keyboard()
        )

@router.callback_query(F.data == "back_to_main")
async def process_back_callback(callback: CallbackQuery):
    """
    Обработчик кнопки "Назад".
    """
    await callback.answer()
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    ) 