import os
import logging
import yt_dlp
import imageio_ffmpeg
import glob
import subprocess
from config import DOWNLOADS_DIR
import uuid
import time
import datetime
import requests
import asyncio
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Максимальный размер файла для отправки в Telegram (в байтах)
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ

# Максимальный возраст файлов в папке загрузок (в часах)
MAX_FILE_AGE_HOURS = 1

def cleanup_downloads_folder(max_age_hours=MAX_FILE_AGE_HOURS):
    """
    Очищает папку загрузок от старых файлов.
    
    Args:
        max_age_hours: Максимальный возраст файлов в часах
    """
    try:
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # Проверяем наличие директории
        if not os.path.exists(DOWNLOADS_DIR):
            os.makedirs(DOWNLOADS_DIR)
            logger.info(f"Создана директория для загрузок: {DOWNLOADS_DIR}")
            return
        
        # Удаляем все файлы из директории, которые старше заданного возраста
        count = 0
        for filename in os.listdir(DOWNLOADS_DIR):
            file_path = os.path.join(DOWNLOADS_DIR, filename)
            if os.path.isfile(file_path):
                try:
                    file_age = now - os.path.getmtime(file_path)
                    if file_age > max_age_seconds:
                        # Попытка форсированного удаления с повторными попытками
                        for attempt in range(3):
                            try:
                                os.remove(file_path)
                                count += 1
                                logger.info(f"Удален старый файл: {filename} (возраст: {file_age/3600:.1f} ч.)")
                                break
                            except PermissionError:
                                # Если файл заблокирован, даем системе немного времени
                                logger.warning(f"Файл {filename} заблокирован, попытка {attempt+1}/3")
                                time.sleep(0.5)
                            except Exception as e:
                                logger.warning(f"Не удалось удалить файл {filename}: {e}")
                                break
                except Exception as e:
                    logger.warning(f"Ошибка при проверке файла {filename}: {e}")
        
        if count > 0:
            logger.info(f"Очищено {count} старых файлов из директории загрузок")
        else:
            logger.info("Старых файлов для очистки не найдено")
            
    except Exception as e:
        logger.error(f"Ошибка при очистке директории загрузок: {e}")

def force_cleanup_downloads_folder():
    """Принудительная очистка папки загрузок"""
    downloads_dir = "downloads"
    
    # Проверяем наличие директории
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
        logger.info(f"Создана директория {downloads_dir}")
        return
    
    # Получаем список файлов
    files = os.listdir(downloads_dir)
    
    if not files:
        logger.info("Файлов для очистки не найдено")
        return
    
    # Удаляем все файлы
    for file in files:
        file_path = os.path.join(downloads_dir, file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            logger.error(f"Ошибка при удалении {file_path}: {e}")
    
    logger.info(f"Очищено {len(files)} файлов из директории {downloads_dir}")

def cleanup_old_downloads(max_age_minutes=30):
    """Очистка старых загрузок"""
    downloads_dir = "downloads"
    current_time = time.time()
    max_age_seconds = max_age_minutes * 60
    
    # Проверяем наличие директории
    if not os.path.exists(downloads_dir):
        return
    
    # Получаем список файлов
    files = os.listdir(downloads_dir)
    old_files = []
    
    for file in files:
        file_path = os.path.join(downloads_dir, file)
        if os.path.isfile(file_path):
            file_age = current_time - os.path.getmtime(file_path)
            if file_age > max_age_seconds:
                old_files.append(file_path)
    
    if not old_files:
        logger.info("Старых файлов для очистки не найдено")
        return
    
    # Удаляем старые файлы
    for file_path in old_files:
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.error(f"Ошибка при удалении {file_path}: {e}")
    
    logger.info(f"Очищено {len(old_files)} старых файлов из директории {downloads_dir}")

def enhance_metadata(metadata):
    """
    Улучшает метаданные трека, извлекая информацию из названия, если есть возможность.
    
    Args:
        metadata: Словарь с метаданными
        
    Returns:
        dict: Улучшенные метаданные
    """
    try:
        title = metadata.get('title', '')
        artist = metadata.get('artist', '')
        
        # Если у нас есть название и нет исполнителя, пробуем его извлечь из названия
        if title and (not artist or artist == 'Unknown Artist'):
            separators = [' - ', ' – ', ' — ', ' • ', ' | ', ' : ', ' _ ']
            for separator in separators:
                if separator in title:
                    parts = title.split(separator, 1)
                    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                        metadata['artist'] = parts[0].strip()
                        metadata['title'] = parts[1].strip()
                        break
        
        return metadata
    except Exception as e:
        logger.warning(f"Ошибка при улучшении метаданных: {e}")
        return metadata

async def download_audio_from_youtube(url: str) -> tuple:
    """
    Скачивает аудио из YouTube видео и сохраняет в формате MP3.
    Оптимизированная версия с быстрой загрузкой.
    
    Args:
        url: YouTube URL для скачивания
        
    Returns:
        tuple: (путь к файлу, метаданные трека, путь к обложке)
        
    Raises:
        Exception: Если произошла ошибка при скачивании
    """
    # Инициализируем переменные заранее, чтобы они были доступны в блоке except
    audio_file_path = None
    metadata = {
        'title': 'Unknown Title',
        'artist': 'Unknown Artist',
        'album': 'YouTube Audio',
        'thumbnail': None,
        'duration': None
    }
    telegram_thumb_path = None
    
    try:
        # Очищаем папку загрузок от старых файлов
        cleanup_downloads_folder()
        
        logger.info(f"Начинаю скачивание аудио из: {url}")
        
        # Путь к ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        
        # Временный файл для аудио с уникальным именем
        temp_filename = f"audio_{uuid.uuid4().hex[:8]}"
        output_path = os.path.join(DOWNLOADS_DIR, temp_filename)
        
        # Список файлов перед загрузкой
        before_files = set(os.listdir(DOWNLOADS_DIR))
        
        # Прямая оптимизированная загрузка аудио с получением метаданных
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',  # Предпочитаем m4a как более эффективный формат
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }, {
                # Добавляем постпроцессор для записи метаданных в файл
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }],
            'outtmpl': output_path + '.%(ext)s',
            'ffmpeg_location': ffmpeg_path,
            # Добавляем параметры FFmpeg через postprocessor_args
            'postprocessor_args': [
                '-threads', '4', 
                '-preset', 'fast'
            ],
            'quiet': True,  # Скрываем большинство выводов yt-dlp
            'no_warnings': True,  # Скрываем предупреждения
            'verbose': False,  # Отключаем подробные логи
            'progress': False,  # Отключаем индикатор прогресса
            'max_filesize': MAX_TELEGRAM_FILE_SIZE - 2*1024*1024,  # Запас 2 МБ
            'max_duration': 900,  # 15 минут
            'noplaylist': True,
            'extract_flat': False,
            'skip_download': False,
            'writethumbnail': True,  # Скачиваем миниатюру для обложки Telegram
            'writeinfojson': False,
            'writedescription': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'concurrent_fragment_downloads': 8,  # Увеличиваем параллельные загрузки фрагментов
            'fragment_retries': 3,
            'retries': 3,
            # Отключаем лишние проверки API
            'check_formats': False,
            'source_address': '0.0.0.0',  # Более быстрая инициализация сетевых запросов
            # Ускоряем загрузку
            'socket_timeout': 10,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            }
        }
        
        # Определяем функцию для скачивания в отдельном потоке
        def download_in_thread():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        
        logger.info("Запускаю загрузку аудио в отдельном потоке")
        # Запускаем скачивание в отдельном потоке с помощью asyncio.to_thread
        info = await asyncio.to_thread(download_in_thread)
        
        # Сохраняем метаданные после успешной загрузки
        if info:
            metadata['title'] = info.get('title', 'Unknown Title')
            # Не используем название канала в качестве артиста
            metadata['artist'] = info.get('artist', '') or ''
            metadata['album'] = info.get('album', 'YouTube Audio')
            metadata['thumbnail'] = info.get('thumbnail')
            metadata['channel'] = info.get('channel') or info.get('uploader', '')
            
            # Форматируем длительность
            duration_sec = info.get('duration')
            if duration_sec:
                minutes = int(duration_sec) // 60
                seconds = int(duration_sec) % 60
                metadata['duration'] = f"{minutes}:{seconds:02d}"
                metadata['duration_sec'] = duration_sec
            
            # Всегда очищаем метаданные
            metadata = enhance_metadata(metadata)
        
        # Ищем новые файлы после загрузки
        after_files = set(os.listdir(DOWNLOADS_DIR))
        new_files = list(after_files - before_files)
        logger.info(f"Новые файлы после загрузки: {new_files}")
        
        # Находим скачанный MP3 файл
        audio_file_path = None
        
        # Ищем MP3 файл, который мы только что скачали
        expected_mp3 = output_path + ".mp3"
        if os.path.exists(expected_mp3):
            logger.info(f"Найден скачанный файл: {expected_mp3}")
            audio_file_path = expected_mp3
        else:
            # Если точный путь не найден, ищем по шаблону
            mp3_files = [os.path.join(DOWNLOADS_DIR, f) for f in new_files if f.endswith('.mp3') or f.endswith('.mp3.mp3')]
            if mp3_files:
                audio_file_path = mp3_files[0]
                logger.info(f"Найден новый MP3 файл: {audio_file_path}")
            else:
                # Если ничего не найдено, ищем самый свежий MP3 в папке
                all_mp3_files = glob.glob(os.path.join(DOWNLOADS_DIR, "*.mp3"))
                if all_mp3_files:
                    recent_file = max(all_mp3_files, key=os.path.getmtime)
                    # Проверяем, что файл новый (создан не более 10 секунд назад)
                    if time.time() - os.path.getmtime(recent_file) < 10:
                        logger.info(f"Найден свежий MP3 файл: {recent_file}")
                        audio_file_path = recent_file
        
        if not audio_file_path:
            raise FileNotFoundError(f"Не удалось найти скачанный MP3 файл для {url}")
        
        # Поиск миниатюры только для Telegram
        thumbnail_files = [f for f in new_files if any(f.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp'])]
        
        # Обрабатываем обложку только для Telegram
        if thumbnail_files:
            source_thumbnail = os.path.join(DOWNLOADS_DIR, thumbnail_files[0])
            logger.info(f"Найдена миниатюра: {source_thumbnail}")
            
            # Получаем расширение файла
            thumbnail_ext = os.path.splitext(source_thumbnail)[1].lower()
            
            # WebP можно использовать напрямую в Telegram для обложек (экспериментально)
            # Создаем копию обложки для Telegram с тем же форматом
            telegram_thumb_name = f"tg_thumb_{uuid.uuid4().hex[:8]}{thumbnail_ext}"
            telegram_thumb_path = os.path.join(DOWNLOADS_DIR, telegram_thumb_name)
            
            # Копируем файл (независимо от формата)
            shutil.copy2(source_thumbnail, telegram_thumb_path)
            logger.info(f"Подготовлена обложка для Telegram: {telegram_thumb_path}")
        
        # Если не нашли миниатюру среди скачанных файлов, пробуем загрузить напрямую
        if not telegram_thumb_path and metadata.get('thumbnail'):
            try:
                thumbnail_url = metadata['thumbnail']
                # Определяем расширение из URL
                thumbnail_ext = os.path.splitext(thumbnail_url.split('?')[0])[1].lower()
                if not thumbnail_ext:
                    thumbnail_ext = '.jpg'  # По умолчанию jpg если расширение не определено
                
                telegram_thumb_path = os.path.join(DOWNLOADS_DIR, f"tg_thumb_{uuid.uuid4().hex[:8]}{thumbnail_ext}")
                logger.info(f"Загружаю миниатюру напрямую: {thumbnail_url}")
                
                response = requests.get(thumbnail_url, timeout=10)
                with open(telegram_thumb_path, 'wb') as f:
                    f.write(response.content)
                
                if os.path.exists(telegram_thumb_path) and os.path.getsize(telegram_thumb_path) > 0:
                    logger.info(f"Миниатюра успешно загружена напрямую: {telegram_thumb_path}")
                else:
                    logger.warning("Не удалось загрузить миниатюру напрямую")
                    telegram_thumb_path = None
            except Exception as e:
                logger.warning(f"Ошибка при загрузке миниатюры напрямую: {e}")
                telegram_thumb_path = None
        
        # Удаляем все временные файлы миниатюр, кроме той что для Telegram
        for thumb_file in [f for f in new_files if any(f.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp'])]:
            thumb_path = os.path.join(DOWNLOADS_DIR, thumb_file)
            try:
                # Не удаляем обложку для Telegram
                if thumb_path == telegram_thumb_path:
                    continue
                
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                    logger.info(f"Удален файл миниатюры: {thumb_path}")
            except Exception as e:
                logger.warning(f"Не удалось удалить файл миниатюры {thumb_path}: {e}")
                
        return audio_file_path, metadata, telegram_thumb_path
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании аудио: {e}", exc_info=True)
        raise Exception(f"Не удалось скачать аудио: {str(e)}")

async def search_youtube_music(query: str, limit: int = 0) -> list:
    """
    Выполняет поиск только в YouTube Music по запросу.
    Оптимизированная версия, использующая наиболее эффективные стратегии поиска.
    
    Args:
        query: Строка запроса
        limit: Максимальное количество результатов (0 = без ограничений)
        
    Returns:
        list: Список результатов поиска (песни из YouTube Music)
    """
    logger.info(f"Поиск музыки по запросу: {query}")
    
    try:
        from ytmusicapi import YTMusic
        
        # Инициализация API без авторизации
        ytmusic = YTMusic(language="ru")
        
        # Определяем лимит поиска
        search_limit = 50 if limit == 0 else limit * 2
        
        logger.info(f"Выполняем быстрый поиск '{query}' в YouTube Music")
        
        # Используем только основную стратегию поиска без множественных запросов
        results = []
        
        # Поиск песен
        songs_results = ytmusic.search(query, filter="songs", limit=search_limit)
        if songs_results:
            results.extend(songs_results)
            logger.info(f"Найдено песен: {len(songs_results)}")
        else:
            # Если песен не найдено, используем общий поиск как запасной вариант
            general_results = ytmusic.search(query, limit=search_limit)
            if general_results:
                results.extend(general_results)
            logger.info(f"Найдено общих результатов: {len(general_results)}")
        
        # Быстрое форматирование результатов
        formatted_results = []
        for result in results:
            # Обрабатываем только результаты с videoId
            video_id = result.get('videoId', '')
            if not video_id:
                continue
                
            # Получаем базовые данные
            title = result.get('title', 'Unknown Title')
            result_type = result.get('resultType', 'song')
            
            # Пропускаем использование названия артиста из результата поиска
            artist = ''
            
            # Получаем длительность
            duration = result.get('duration', 'Unknown')
            if not duration or duration == 'Unknown':
                duration = result.get('length', 'Unknown')
            
            # Проверяем длительность, исключаем файлы длиннее 15 минут
            try:
                if duration and duration != 'Unknown':
                    duration_parts = duration.split(':')
                    total_minutes = 0
                    if len(duration_parts) == 2:  # MM:SS
                        total_minutes = int(duration_parts[0])
                    elif len(duration_parts) == 3:  # H:MM:SS
                        total_minutes = int(duration_parts[0]) * 60 + int(duration_parts[1])
                    
                    # Исключаем файлы длиннее 15 минут
                    if total_minutes > 15:
                        continue
            except Exception:
                pass  # Игнорируем ошибки при обработке длительности для скорости
            
            # Добавляем результат
            formatted_results.append({
                'title': title,
                'artist': artist,
                'duration': duration,
                'videoId': video_id,
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'type': result_type or 'song'
            })
            
            # Если достигли лимита, останавливаемся
            if limit > 0 and len(formatted_results) >= limit:
                break
        
        logger.info(f"Найдено {len(formatted_results)} музыкальных результатов")
        
        # Если результатов нет или очень мало, используем резервный поиск
        if len(formatted_results) < 5:
            # Пробуем резервный поиск
            logger.info(f"Мало результатов, запускаем резервный поиск через yt-dlp")
            backup_results = await search_youtube_with_ytdlp(query, limit if limit > 0 else 30)
            if backup_results:
                # Комбинируем результаты, ставя YTMusic результаты вперед
                combined_results = formatted_results + [r for r in backup_results if r['videoId'] not in {item['videoId'] for item in formatted_results}]
                return combined_results[:limit] if limit > 0 else combined_results
        
        return formatted_results
    except Exception as e:
        logger.error(f"Ошибка при поиске в YouTube Music: {e}")
        
        # При ошибке YTMusic API используем резервный метод
        try:
            logger.info(f"Ошибка YTMusic API, используем резервный поиск через yt-dlp")
            return await search_youtube_with_ytdlp(query, limit if limit > 0 else 30)
        except Exception as backup_error:
            logger.error(f"Ошибка при резервном поиске: {backup_error}")
        return []

async def search_youtube_with_ytdlp(query: str, limit: int = 0) -> list:
    """
    Резервный метод поиска через yt-dlp.
    Оптимизированная версия с быстрой загрузкой минимума метаданных.
    
    Args:
        query: Строка поискового запроса
        limit: Максимальное количество результатов (0 = без ограничений)
        
    Returns:
        list: Список результатов поиска
    """
    logger.info(f"Выполняем быстрый поиск через yt-dlp: {query}")
    
    try:
        # Если лимит не задан, устанавливаем значение по умолчанию 30 результатов
        search_limit = 100 if limit == 0 else limit
        search_query = f"ytsearch{search_limit}:{query}"
        
        # Оптимизированные настройки для быстрого поиска
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',  # Только базовую информацию
            'skip_download': True,          # Не скачиваем видео
            'format': 'bestaudio',
            # Отключаем ненужные операции для ускорения поиска
            'ignoreerrors': True,
            'no_playlist_metainfo': True,
            'playlist_items': '1-30',
            'writethumbnail': False,
            'writeinfojson': False,
            'writedescription': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'noplaylist': False,
            'socket_timeout': 10,           # Снижаем таймаут ожидания
            'retries': 1,                   # Минимум повторов
        }
        
        results = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Устанавливаем таймаут для всей операции
                info = ydl.extract_info(search_query, download=False)
                if 'entries' in info:
                    for entry in info['entries']:
                        # Проверяем, что это видео, а не плейлист
                        if entry.get('_type') != 'playlist' and entry.get('id'):
                            title = entry.get('title', 'Unknown Title')
                            # Не используем название канала
                            artist = ''
                            duration_sec = entry.get('duration')
                            
                            # Форматируем длительность
                            if duration_sec:
                                # Преобразуем в целое число, если duration_sec - float
                                duration_sec = int(duration_sec)
                                
                                # Проверяем длительность - исключаем файлы длиннее 15 минут (900 секунд)
                                if duration_sec > 900:
                                    logger.info(f"Исключен трек длительностью {duration_sec} сек: {title}")
                                    continue
                                    
                                minutes = duration_sec // 60
                                seconds = duration_sec % 60
                                duration = f"{minutes}:{seconds:02d}"
                            else:
                                duration = "Unknown"
                            
                            # Форматируем для соответствия формату YTMusic API
                            results.append({
                                'title': title,
                                'artist': artist,
                                'duration': duration,
                                'videoId': entry.get('id'),
                                'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                                'type': 'song'
                            })
            except Exception as search_error:
                logger.warning(f"Ошибка при поиске: {search_error}")
        
        logger.info(f"Найдено {len(results)} результатов через быстрый поиск yt-dlp")
        return results
    except Exception as e:
        logger.error(f"Ошибка при поиске через yt-dlp: {e}", exc_info=True)
        return [] 