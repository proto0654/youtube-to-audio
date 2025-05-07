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
from aiogram.filters import Command, CommandObject
from typing import List, Dict, Optional, Union, Tuple
import asyncio

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

# Словарь для отслеживания активных задач обработки скачивания
active_download_tasks = {}

# Функция для обработки скачивания и отправки аудио
async def process_and_send_audio_download(callback, url, loading_message, is_group_chat, user_name, video_id):
    """
    Асинхронная функция для скачивания и отправки аудио пользователю.
    Запускается как отдельная задача, чтобы не блокировать основной поток обработки сообщений.
    
    Args:
        callback: Исходный callback запроса на скачивание
        url: URL для скачивания
        loading_message: Сообщение-индикатор загрузки
        is_group_chat: Флаг группового чата
        user_name: Имя пользователя для сообщений
        video_id: ID видео YouTube
    """
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    file_path = None
    thumb_path = None
    
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
            reply_to_message_id=None if is_group_chat else callback.message.message_id,
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
    finally:
        # Удаляем задачу из словаря активных задач
        task_key = f"{chat_id}_{user_id}_{video_id}"
        if task_key in active_download_tasks:
            active_download_tasks.pop(task_key, None)

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
        video_id = result.get('videoId', '')
        
        # Номер результата на глобальном уровне (с учетом страницы)
        result_num = i + pagination.page * pagination.per_page
        
        # Добавляем иконку в зависимости от типа результата
        icon = "🎵" if result_type == "song" else "🎬"
        
        # Полное название для отображения в сообщении
        text += f"{result_num}. {icon} <b>{title}</b> - {artist} ({duration})\n"
        
        # Формируем текст кнопки с исполнителем
        if artist and artist != 'Unknown' and artist != 'Unknown Artist':
            download_text = f"⬇️ {result_num}. {artist} - {title}"
        else:
            download_text = f"⬇️ {result_num}. {title}"
        
        keyboards.append([
            InlineKeyboardButton(
                text=download_text,
                callback_data=f"download:{video_id}"
            )
        ])
    
    # Добавляем кнопки навигации с message_id для возможности навигации другими пользователями
    navigation_buttons = []
    
    # Формируем message_id для callback_data
    message_id = ""
    
    # Если это CallbackQuery, мы редактируем существующее сообщение
    if isinstance(message_or_callback, CallbackQuery):
        message_id = str(message_or_callback.message.message_id)
    
    if pagination.has_prev_page():
        navigation_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"search_prev_page:{message_id}"
            )
        )
    
    if pagination.has_next_page():
        navigation_buttons.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"search_next_page:{message_id}"
            )
        )
    
    # Добавляем кнопки навигации, если они есть
    if navigation_buttons:
        keyboards.append(navigation_buttons)
    
    # Добавляем кнопку для перехода на произвольную страницу, если страниц больше 3
    if pagination.total_pages() > 3:
        keyboards.append([
            InlineKeyboardButton(
                text=f"📄 Страницы... ({pagination.page + 1}/{pagination.total_pages()})",
                callback_data=f"search_goto_page:{message_id}"
            )
        ])
    
    # Добавляем кнопки для нового поиска и возврата в меню
    keyboards.append([
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search"),
        InlineKeyboardButton(text="↩️ К меню", callback_data="back_to_main")
    ])
    
    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboards)
    
    # Отправляем или редактируем сообщение и сохраняем результаты
    result_message = None
    chat_id = None
    
    if isinstance(message_or_callback, CallbackQuery):
        # Для CallbackQuery
        chat_id = message_or_callback.message.chat.id
        user_id = message_or_callback.from_user.id
        topic_id = message_or_callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
        
        if edit_message:
            # Редактируем существующее сообщение
            await message_or_callback.message.edit_text(text, reply_markup=keyboard)
            result_message = message_or_callback.message
        else:
            # Отправляем новое сообщение
            result_message = await message_or_callback.message.answer(text, reply_markup=keyboard)
        
        await message_or_callback.answer()
        
        # Сбрасываем состояние просмотра результатов для пользователя только в приватном чате
        if message_or_callback.message.chat.type == ChatType.PRIVATE:
            state = Dispatcher.get_current().fsm_storage
            if state:
                await state.set_state(user=user_id, chat=chat_id, state=None)
    else:
        # Для Message
        chat_id = message_or_callback.chat.id
        user_id = message_or_callback.from_user.id
        topic_id = message_or_callback.message_thread_id if TOPICS_MODE_ENABLED else None
        
        if is_reply:
            # Отправляем сообщение как ответ (для группового чата)
            result_message = await message_or_callback.reply(text, reply_markup=keyboard)
        else:
            # Обычная отправка сообщения
            result_message = await message_or_callback.answer(text, reply_markup=keyboard)
        
        # Сбрасываем состояние просмотра результатов для пользователя только в приватном чате
        if message_or_callback.chat.type == ChatType.PRIVATE:
            state = Dispatcher.get_current().fsm_storage
            if state:
                await state.set_state(user=user_id, chat=chat_id, state=None)
    
    # Сохраняем результаты поиска в хранилище по ID сообщения для возможности навигации
    if result_message and chat_id:
        # Используем хранилище, связанное с сообщением
        user_state_manager.store_search_results_by_message(
            chat_id, 
            result_message.message_id, 
            pagination.__dict__
        )
        
        # При первой отправке message_id еще не известен, поэтому обновляем callback_data
        if not message_id and result_message:
            # Создаем новую клавиатуру с актуальным message_id
            updated_keyboards = []
            for row in keyboards:
                updated_row = []
                for button in row:
                    callback_data = button.callback_data
                    if callback_data.startswith("search_prev_page:") or callback_data.startswith("search_next_page:") or callback_data.startswith("search_goto_page:"):
                        # Добавляем message_id к callback_data
                        callback_data = f"{callback_data.split(':')[0]}:{result_message.message_id}"
                    updated_row.append(InlineKeyboardButton(
                        text=button.text,
                        callback_data=callback_data
                    ))
                updated_keyboards.append(updated_row)
            
            updated_keyboard = InlineKeyboardMarkup(inline_keyboard=updated_keyboards)
            await result_message.edit_reply_markup(reply_markup=updated_keyboard)

# Обработчики для навигации по страницам
@router.callback_query(F.data.startswith("search_next_page"))
async def process_next_page(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Следующая страница" результатов поиска.
    Теперь использует message_id для обеспечения доступности всем пользователям.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    message_id = callback.message.message_id
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Получаем ID сообщения из callback_data, если он указан
    callback_parts = callback.data.split(":", 1)
    specified_message_id = None
    if len(callback_parts) > 1 and callback_parts[1]:
        try:
            specified_message_id = int(callback_parts[1])
        except ValueError:
            pass  # Игнорируем, если не удалось преобразовать к int
    
    # Используем указанный message_id, если он есть
    if specified_message_id:
        message_id = specified_message_id
    
    # Получаем данные пагинации из хранилища по message_id
    pagination_data = user_state_manager.get_search_results_by_message(chat_id, message_id)
    
    # Если данных нет по message_id, пробуем получить их из старого хранилища (для совместимости)
    if not pagination_data and chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # Пробуем найти в состоянии пользователя, который сделал поиск
        pagination_data = user_state_manager.get_user_state(user_id, "search_results", None, chat_id, topic_id)
        
        # Если нашли, сохраняем в новое хранилище для дальнейшего использования
        if pagination_data:
            user_state_manager.store_search_results_by_message(chat_id, message_id, pagination_data)
            logger.info(f"Перенесены данные поиска из старого хранилища в новое для сообщения {message_id}")
    
    # Если данных по message_id все еще нет, пробуем получить их из FSM (для личных чатов)
    if not pagination_data and chat_type == ChatType.PRIVATE:
        # Для приватного чата используем FSM
        data = await state.get_data()
        pagination_data = data.get('pagination')
        
        # Если нашли, сохраняем в новое хранилище
        if pagination_data:
            user_state_manager.store_search_results_by_message(chat_id, message_id, pagination_data)
    
    # Если данных все еще нет, сообщаем об ошибке
    if not pagination_data:
        await callback.answer("Информация о поиске не найдена. Попробуйте выполнить новый поиск.", show_alert=True)
        return
    
    # Создаем объект пагинации и переходим на следующую страницу
    pagination = SearchPagination(**pagination_data)
    pagination.page += 1
    
    # Сохраняем обновленные данные
    user_state_manager.update_search_results_by_message(chat_id, message_id, pagination.__dict__)
    
    # Для обратной совместимости также обновляем данные в старом хранилище
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        user_state_manager.set_user_state(user_id, "search_results", pagination.__dict__, chat_id, topic_id)
    elif chat_type == ChatType.PRIVATE:
        await state.update_data(pagination=pagination.__dict__)
    
    # Отображаем следующую страницу
    await display_search_results_page(callback, pagination, edit_message=True)

@router.callback_query(F.data.startswith("search_prev_page"))
async def process_prev_page(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Предыдущая страница" результатов поиска.
    Теперь использует message_id для обеспечения доступности всем пользователям.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    message_id = callback.message.message_id
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Получаем ID сообщения из callback_data, если он указан
    callback_parts = callback.data.split(":", 1)
    specified_message_id = None
    if len(callback_parts) > 1 and callback_parts[1]:
        try:
            specified_message_id = int(callback_parts[1])
        except ValueError:
            pass  # Игнорируем, если не удалось преобразовать к int
    
    # Используем указанный message_id, если он есть
    if specified_message_id:
        message_id = specified_message_id
    
    # Получаем данные пагинации из хранилища по message_id
    pagination_data = user_state_manager.get_search_results_by_message(chat_id, message_id)
    
    # Если данных нет по message_id, пробуем получить их из старого хранилища (для совместимости)
    if not pagination_data and chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # Пробуем найти в состоянии пользователя, который сделал поиск
        pagination_data = user_state_manager.get_user_state(user_id, "search_results", None, chat_id, topic_id)
        
        # Если нашли, сохраняем в новое хранилище для дальнейшего использования
        if pagination_data:
            user_state_manager.store_search_results_by_message(chat_id, message_id, pagination_data)
            logger.info(f"Перенесены данные поиска из старого хранилища в новое для сообщения {message_id}")
    
    # Если данных по message_id все еще нет, пробуем получить их из FSM (для личных чатов)
    if not pagination_data and chat_type == ChatType.PRIVATE:
        # Для приватного чата используем FSM
        data = await state.get_data()
        pagination_data = data.get('pagination')
        
        # Если нашли, сохраняем в новое хранилище
        if pagination_data:
            user_state_manager.store_search_results_by_message(chat_id, message_id, pagination_data)
    
    # Если данных все еще нет, сообщаем об ошибке
    if not pagination_data:
        await callback.answer("Информация о поиске не найдена. Попробуйте выполнить новый поиск.", show_alert=True)
        return
    
    # Создаем объект пагинации и переходим на предыдущую страницу
    pagination = SearchPagination(**pagination_data)
    pagination.page -= 1
    
    # Сохраняем обновленные данные
    user_state_manager.update_search_results_by_message(chat_id, message_id, pagination.__dict__)
    
    # Для обратной совместимости также обновляем данные в старом хранилище
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        user_state_manager.set_user_state(user_id, "search_results", pagination.__dict__, chat_id, topic_id)
    elif chat_type == ChatType.PRIVATE:
        await state.update_data(pagination=pagination.__dict__)
    
    # Отображаем предыдущую страницу
    await display_search_results_page(callback, pagination, edit_message=True)

@router.callback_query(F.data == "new_search")
async def process_new_search_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Новый поиск".
    Сбрасывает состояние просмотра результатов и запрашивает новый поисковый запрос.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Очищаем состояние просмотра результатов независимо от типа чата
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        # В групповом чате используем локальный менеджер состояний
        # Сбрасываем состояние просмотра результатов
        user_state_manager.set_user_browsing_results(user_id, False, None, chat_id, topic_id)
        # Устанавливаем ожидание нового запроса
        user_state_manager.set_user_waiting_for_query(user_id, True, chat_id, topic_id)
        
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
    Создает асинхронную задачу для скачивания аудио и отправки его пользователю.
    """
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
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
    
    # Создаем ключ для отслеживания задачи с учетом уникального видео ID
    task_key = f"{chat_id}_{user_id}_{video_id}"
    
    # Создаем асинхронную задачу обработки
    task = asyncio.create_task(
        process_and_send_audio_download(callback, url, loading_message, is_group_chat, user_name, video_id)
    )
    
    # Сохраняем задачу в словаре активных задач
    active_download_tasks[task_key] = task
    
    # Не ожидаем завершения задачи - она выполнится в фоне
    logger.info(f"Запущена асинхронная обработка запроса на скачивание для {user_id} в чате {chat_id}, видео {video_id}")

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

@router.message(Command("search"), ~F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_search(message: Message, state: FSMContext, command: CommandObject = None):
    """
    Обработчик команды /search для личных чатов.
    Принимает поисковый запрос как аргумент или устанавливает ожидание запроса.
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    logger.info(f"Пользователь {user_id} ({user_name}) использовал команду /search")
    
    # Если есть аргумент, используем его как запрос
    if command and command.args:
        query = command.args.strip()
        logger.info(f"Пользователь {user_id} ({user_name}) отправил поисковый запрос: {query}")
        
        # Минимальная длина запроса
        if len(query) < 3:
            await message.answer(
                "Пожалуйста, введите запрос длиной не менее 3 символов.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Отправка сообщения о начале поиска
        loading_message = await message.answer("🔍 Ищу музыку, пожалуйста, подождите...")
        
        try:
            # Выполнение поиска в YouTube Music
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
    else:
        # Если аргумента нет, устанавливаем состояние ожидания запроса
        await message.answer(
            f"{user_name}, введите запрос для поиска музыки в YouTube Music:"
        )
        await state.set_state(SearchStates.waiting_for_query)

@router.callback_query(F.data.startswith("search_goto_page:"))
async def process_goto_page(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Страницы...".
    Позволяет перейти на произвольную страницу результатов поиска.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    message_id = callback.message.message_id
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Получаем ID сообщения из callback_data
    callback_parts = callback.data.split(":", 1)
    specified_message_id = None
    if len(callback_parts) > 1 and callback_parts[1]:
        try:
            specified_message_id = int(callback_parts[1])
        except ValueError:
            pass
    
    if specified_message_id:
        message_id = specified_message_id
    
    # Получаем данные пагинации из хранилища
    pagination_data = user_state_manager.get_search_results_by_message(chat_id, message_id)
    
    # Если данных нет, пробуем получить их из старых источников
    if not pagination_data:
        if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
            pagination_data = user_state_manager.get_user_state(user_id, "search_results", None, chat_id, topic_id)
        elif chat_type == ChatType.PRIVATE:
            data = await state.get_data()
            pagination_data = data.get('pagination')
    
    if not pagination_data:
        await callback.answer("Информация о поиске не найдена", show_alert=True)
        return
    
    # Создаем объект пагинации
    pagination = SearchPagination(**pagination_data)
    total_pages = pagination.total_pages()
    current_page = pagination.page + 1  # +1 для отображения
    
    # Формируем клавиатуру для выбора страницы
    keyboard = []
    
    # Кнопки для первых страниц
    first_page_buttons = []
    for page in range(1, min(6, total_pages + 1)):
        button_text = f"[{page}]" if page == current_page else f"{page}"
        first_page_buttons.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"search_page:{message_id}:{page-1}"  # -1 так как в объекте страницы с 0
            )
        )
    
    if first_page_buttons:
        keyboard.append(first_page_buttons)
    
    # Если много страниц, добавляем кнопки для последних страниц
    if total_pages > 10:
        last_page_buttons = []
        for page in range(max(6, total_pages - 4), total_pages + 1):
            button_text = f"[{page}]" if page == current_page else f"{page}"
            last_page_buttons.append(
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"search_page:{message_id}:{page-1}"
                )
            )
        
        if last_page_buttons:
            keyboard.append(last_page_buttons)
    
    # Кнопка назад
    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Назад к результатам",
            callback_data=f"search_page:{message_id}:{pagination.page}"  # Текущая страница
        )
    ])
    
    # Отправляем клавиатуру
    await callback.message.edit_text(
        f"🔢 <b>Выберите страницу</b>\n\n"
        f"Всего доступно: {total_pages} страниц\n"
        f"Текущая страница: {current_page}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    
    await callback.answer()

@router.callback_query(F.data.startswith("search_page:"))
async def process_select_page(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик выбора конкретной страницы результатов поиска.
    """
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    topic_id = callback.message.message_thread_id if TOPICS_MODE_ENABLED else None
    
    # Проверяем, разрешен ли этот чат/топик
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and not is_allowed_chat(chat_id, topic_id):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    
    # Получаем параметры из callback_data
    callback_parts = callback.data.split(":", 2)
    
    if len(callback_parts) < 3:
        await callback.answer("Неверный формат данных", show_alert=True)
        return
    
    try:
        message_id = int(callback_parts[1])
        page = int(callback_parts[2])
    except ValueError:
        await callback.answer("Неверный формат страницы", show_alert=True)
        return
    
    # Получаем данные пагинации из хранилища
    pagination_data = user_state_manager.get_search_results_by_message(chat_id, message_id)
    
    # Если данных нет, пробуем получить их из старых источников
    if not pagination_data:
        if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
            pagination_data = user_state_manager.get_user_state(user_id, "search_results", None, chat_id, topic_id)
        elif chat_type == ChatType.PRIVATE:
            data = await state.get_data()
            pagination_data = data.get('pagination')
    
    if not pagination_data:
        await callback.answer("Информация о поиске не найдена", show_alert=True)
        return
    
    # Создаем объект пагинации и устанавливаем выбранную страницу
    pagination = SearchPagination(**pagination_data)
    
    # Проверяем, что страница в допустимом диапазоне
    if page < 0 or page >= pagination.total_pages():
        await callback.answer(f"Страница должна быть от 1 до {pagination.total_pages()}", show_alert=True)
        return
    
    # Устанавливаем выбранную страницу
    pagination.page = page
    
    # Сохраняем обновленные данные
    user_state_manager.update_search_results_by_message(chat_id, message_id, pagination.__dict__)
    
    # Для обратной совместимости также обновляем данные в старом хранилище
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and GROUP_MODE_ENABLED:
        user_state_manager.set_user_state(user_id, "search_results", pagination.__dict__, chat_id, topic_id)
    elif chat_type == ChatType.PRIVATE:
        await state.update_data(pagination=pagination.__dict__)
    
    # Отображаем выбранную страницу
    await display_search_results_page(callback, pagination, edit_message=True)

# Добавляем общий обработчик для любых текстовых сообщений в личных чатах
# Используем низкий приоритет, чтобы этот обработчик сработал только если сообщение не обработано другими обработчиками
@router.message(F.text, F.chat.type == ChatType.PRIVATE, flags={"low_priority": True})
async def process_any_text_as_search(message: Message, state: FSMContext):
    """
    Обработчик любых текстовых сообщений в личных чатах.
    Интерпретирует любой текст как поисковый запрос.
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    query = message.text.strip()
    
    logger.info(f"Пользователь {user_id} ({user_name}) отправил текст, который будет использован как поисковый запрос: {query}")
    
    # Минимальная длина запроса
    if len(query) < 3:
        await message.answer(
            "Пожалуйста, введите запрос длиной не менее 3 символов.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Отправка сообщения о начале поиска
    loading_message = await message.answer("🔍 Ищу музыку, пожалуйста, подождите...")
    
    try:
        # Выполнение поиска в YouTube Music
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

# Обработчик для групповых чатов, интерпретирует текстовые сообщения как поисковые запросы
@router.message(F.text, F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), flags={"low_priority": True})
async def process_group_text_as_search(message: Message):
    """
    Обработчик любых текстовых сообщений в групповых чатах.
    Интерпретирует любой текст как поисковый запрос.
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    chat_id = message.chat.id
    chat_type = message.chat.type
    topic_id = message.message_thread_id if TOPICS_MODE_ENABLED else None
    query = message.text.strip()
    
    # Проверяем, включен ли режим групповых чатов
    if not GROUP_MODE_ENABLED:
        return
    
    # Проверяем, разрешен ли этот чат/топик
    if not is_allowed_chat(chat_id, topic_id):
        logger.info(f"Запрос поиска отклонен в чате {chat_id} (топик: {topic_id}) от пользователя {user_id}")
        return
    
    logger.info(f"Пользователь {user_id} ({user_name}) отправил текст в групповой чат, который будет использован как поисковый запрос: {query}")
    
    # Минимальная длина запроса
    if len(query) < 3:
        # В групповых чатах не отвечаем на короткие запросы, чтобы не спамить
        return
    
    # Отправка сообщения о начале поиска
    loading_message = await message.reply("🔍 Ищу музыку, пожалуйста, подождите...")
    
    try:
        # Выполнение поиска в YouTube Music
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
            
            await message.reply(
                f"🔍 По запросу <b>{query}</b> музыка не найдена.\n\n"
                f"Рекомендации:\n"
                f"✓ Попробуйте более точный запрос\n"
                f"✓ Укажите имя исполнителя и название трека\n"
                f"✓ Используйте английские ключевые слова\n"
                f"✓ Проверьте правильность написания",
                reply_markup=suggestion_markup
            )
            return
        
        # Создаем объект пагинации
        pagination = SearchPagination(results=results, query=query, page=0)
        
        # Отображаем первую страницу результатов (с параметром is_reply=True для группового чата)
        await display_search_results_page(message, pagination, is_reply=True)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке поискового запроса в групповом чате: {e}")
        await loading_message.delete()
        await message.reply(
            f"Произошла ошибка при поиске музыки. Пожалуйста, попробуйте позже или используйте прямую ссылку на YouTube.",
            reply_markup=get_main_keyboard()
        ) 