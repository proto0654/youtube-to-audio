import logging
import os
import re
import time
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from keyboards.inline import get_main_keyboard
from services.youtube import download_audio_from_youtube, MAX_TELEGRAM_FILE_SIZE

logger = logging.getLogger(__name__)
router = Router()

# Регулярное выражение для проверки YouTube ссылок
YOUTUBE_REGEX = r"(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=)?([^\s&]+)"

@router.message(F.text.regexp(YOUTUBE_REGEX))
async def process_youtube_link(message: Message):
    """
    Обработчик сообщений с YouTube ссылками.
    Скачивает аудио и отправляет его пользователю.
    """
    user_id = message.from_user.id
    url = message.text.strip()
    logger.info(f"Пользователь {user_id} отправил YouTube ссылку: {url}")
    
    # Отправка сообщения о начале загрузки
    loading_message = await message.answer(
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
            await message.answer(
                f"❌ <b>Ошибка при загрузке аудио</b>\n\n"
                f"Причина: {str(download_error)}\n\n"
                f"Пожалуйста, проверьте ссылку и попробуйте еще раз.",
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
        
        # Проверяем размер файла
        if file_size > MAX_TELEGRAM_FILE_SIZE:
            await loading_message.delete()
            await message.answer(
                f"⚠️ <b>Файл слишком большой для отправки</b>\n\n"
                f"Размер файла: <b>{file_size / 1024 / 1024:.1f} МБ</b>\n"
                f"Лимит Telegram: <b>50 МБ</b>\n\n"
                f"Попробуйте видео с меньшей длительностью.",
                reply_markup=get_main_keyboard()
            )
            # Удаляем файл
            os.remove(file_path)
            return
        
        # Информативное сообщение о готовности аудио
        await loading_message.edit_text(
            f"✅ <b>Аудио готово к отправке!</b>\n\n"
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
        
        # Отправка аудио пользователю
        await message.answer_audio(
            audio=audio_file,
            title=title,
            performer=artist,
            caption=f"✅ <b>Аудио успешно загружено!</b>\n\n"
                   f"<b>{display_title}</b>\n"
                   f"{duration if duration else ''}",
            thumbnail=thumbnail,
            reply_markup=get_main_keyboard()
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
        logger.error(f"Ошибка при обработке YouTube ссылки: {e}")
        await loading_message.delete()
        await message.answer(
            f"❌ <b>Ошибка при загрузке аудио</b>\n\n"
            f"Причина: {str(e)}\n\n"
            f"Пожалуйста, проверьте ссылку и попробуйте еще раз.",
            reply_markup=get_main_keyboard()
        ) 