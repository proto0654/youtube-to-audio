import logging
import os
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards.inline import get_main_keyboard
from services.youtube import search_youtube_music, download_audio_from_youtube, MAX_TELEGRAM_FILE_SIZE

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

# Новая функция для отображения страницы результатов
async def display_search_results_page(message_or_callback, pagination, edit_message=False):
    """
    Отображает страницу результатов поиска.
    
    Args:
        message_or_callback: Объект Message или CallbackQuery
        pagination: Объект пагинации
        edit_message: Редактировать ли существующее сообщение (для CallbackQuery)
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
        
        # Обрезаем слишком длинные названия
        if len(title) > 40:
            title = title[:40] + "..."
        
        # Добавляем иконку в зависимости от типа результата
        icon = "🎵" if result_type == "song" else "🎬"
        
        # Номер результата на странице
        result_num = i + pagination.page * pagination.per_page
        
        text += f"{result_num}. {icon} <b>{title}</b> - {artist} ({duration})\n"
        
        # Создаем кнопку для скачивания
        download_text = f"⬇️ {i}. {title[:20]}{'...' if len(title) > 20 else ''}"
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
    
    if navigation_buttons:
        keyboards.append(navigation_buttons)
    
    # Добавляем кнопку поиска с другими параметрами
    keyboards.append([
        InlineKeyboardButton(
            text="🔎 Искать еще",
            callback_data=f"new_search"
        )
    ])
    
    # Добавляем кнопку возврата
    keyboards.append([
        InlineKeyboardButton(text="↩️ К меню", callback_data="back_to_main")
    ])
    
    # Отправляем или редактируем сообщение
    markup = InlineKeyboardMarkup(inline_keyboard=keyboards)
    
    if edit_message and isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(text, reply_markup=markup)
        await message_or_callback.answer()
    else:
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer(text, reply_markup=markup)
            await message_or_callback.answer()
        else:
            await message_or_callback.answer(text, reply_markup=markup)

# Обработчики для навигации по страницам
@router.callback_query(F.data == "search_next_page", SearchStates.browsing_results)
async def process_next_page(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия кнопки "Вперед" при просмотре результатов"""
    # Получаем текущее состояние пагинации
    data = await state.get_data()
    pagination_dict = data.get('pagination', {})
    pagination = SearchPagination(**pagination_dict)
    
    # Переходим на следующую страницу, если она есть
    if pagination.has_next_page():
        pagination.page += 1
        await state.update_data(pagination=pagination.__dict__)
        await display_search_results_page(callback, pagination, edit_message=True)
    else:
        await callback.answer("Это последняя страница")

@router.callback_query(F.data == "search_prev_page", SearchStates.browsing_results)
async def process_prev_page(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия кнопки "Назад" при просмотре результатов"""
    # Получаем текущее состояние пагинации
    data = await state.get_data()
    pagination_dict = data.get('pagination', {})
    pagination = SearchPagination(**pagination_dict)
    
    # Переходим на предыдущую страницу, если она есть
    if pagination.has_prev_page():
        pagination.page -= 1
        await state.update_data(pagination=pagination.__dict__)
        await display_search_results_page(callback, pagination, edit_message=True)
    else:
        await callback.answer("Это первая страница")

@router.callback_query(F.data == "new_search")
async def process_new_search_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Искать еще".
    """
    await callback.answer()
    await callback.message.answer(
        "Введите новый запрос для поиска музыки:",
    )
    
    # Устанавливаем состояние ожидания поискового запроса
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
    Обработчик выбора песни для скачивания.
    """
    video_id = callback.data.split(":")[1]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал песню для скачивания: {url}")
    
    # Отправляем уведомление о начале загрузки
    await callback.answer("Начинаю загрузку...", show_alert=False)
    
    # Сообщение с индикатором загрузки и информативным текстом
    loading_message = await callback.message.answer(
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
            await callback.message.answer(
                f"❌ <b>Ошибка при загрузке аудио</b>\n\n"
                f"Причина: {str(download_error)}\n\n"
                f"Пожалуйста, попробуйте еще раз или выберите другую песню.",
                reply_markup=get_main_keyboard()
            )
            return
        
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
            
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # Более информативное сообщение при большом размере файла
        if file_size > MAX_TELEGRAM_FILE_SIZE:
            await loading_message.delete()
            await callback.message.answer(
                f"⚠️ <b>Файл слишком большой для отправки</b>\n\n"
                f"Размер файла: <b>{file_size / 1024 / 1024:.1f} МБ</b>\n"
                f"Лимит Telegram: <b>50 МБ</b>\n\n"
                f"Пожалуйста, выберите другую песню, желательно короче по длительности.",
                reply_markup=get_main_keyboard()
            )
            os.remove(file_path)
            return
        
        # Создаем FSInputFile вместо открытия файла напрямую
        audio_file = FSInputFile(file_path)
        
        # Подготавливаем обложку для Telegram, если она есть
        thumbnail = None
        if thumb_path and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            thumbnail = FSInputFile(thumb_path)
            logger.info(f"Подготовлена обложка для Telegram: {thumb_path}")
        
        # Подготавливаем метаданные для отправки
        title = metadata.get('title', 'Unknown Title')
        artist = metadata.get('artist', 'Unknown Artist')
        album = metadata.get('album', 'YouTube Audio')
        duration = metadata.get('duration', None)
        
        # Генерируем понятное название аудиофайла
        display_title = f"{artist} - {title}" if artist and artist != 'Unknown Artist' else title
        
        # Информативное сообщение о готовности аудио
        await loading_message.edit_text(
            f"✅ <b>Аудио готово к отправке!</b>\n\n"
            f"<b>Трек:</b> {title}\n"
            f"<b>Исполнитель:</b> {artist}\n"
            f"<b>Размер файла:</b> <b>{file_size / 1024 / 1024:.1f} МБ</b>\n\n"
            "<i>Отправляю файл...</i>"
        )
        
        # Отправка аудио с метаданными
        await callback.message.answer_audio(
            audio=audio_file,
            title=title,
            performer=artist,
            caption=f"✅ <b>Аудио успешно загружено!</b>\n\n"
                   f"<b>{display_title}</b>\n"
                   f"{duration if duration else ''}",
            thumbnail=thumbnail,
            reply_markup=get_main_keyboard()
        )
        
        # Удаляем сообщение с индикатором загрузки
        await loading_message.delete()
        
        # Удаляем файлы после отправки
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
        logger.error(f"Ошибка при скачивании аудио: {e}")
        await loading_message.delete()
        await callback.message.answer(
            f"❌ <b>Ошибка при загрузке аудио</b>\n\n"
            f"Причина: {str(e)}\n\n"
            f"Пожалуйста, попробуйте еще раз или выберите другую песню.",
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