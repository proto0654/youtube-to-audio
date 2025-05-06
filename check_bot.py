#!/usr/bin/env python
"""
Скрипт для диагностики YouTube to Audio бота
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bot_diagnostics")

def check_env_config():
    """Проверяет конфигурацию .env файла"""
    logger.info("Проверка конфигурации .env файла...")
    
    load_dotenv()
    
    # Проверяем основные настройки
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("❌ BOT_TOKEN не найден в .env файле")
    else:
        logger.info("✅ BOT_TOKEN найден")
    
    # Проверяем настройки для групп
    group_mode = os.getenv("GROUP_MODE_ENABLED", "").lower()
    if group_mode == "true":
        logger.info("✅ GROUP_MODE_ENABLED=true - Групповой режим включен")
    else:
        logger.warning("⚠️ GROUP_MODE_ENABLED не установлен в true - Групповой режим отключен")
    
    # Проверяем настройки для топиков
    topics_mode = os.getenv("TOPICS_MODE_ENABLED", "").lower()
    if topics_mode == "true":
        logger.info("✅ TOPICS_MODE_ENABLED=true - Поддержка топиков включена")
    else:
        logger.warning("⚠️ TOPICS_MODE_ENABLED не установлен в true - Поддержка топиков отключена")
    
    # Проверяем ограничения
    max_requests = os.getenv("MAX_REQUESTS_PER_USER", "")
    try:
        max_requests_int = int(max_requests)
        logger.info(f"✅ MAX_REQUESTS_PER_USER={max_requests_int} - Ограничение на количество запросов")
    except (ValueError, TypeError):
        logger.warning("⚠️ MAX_REQUESTS_PER_USER не установлен или имеет неверный формат")
    
    # Проверяем разрешенные группы и топики
    allowed_groups = os.getenv("ALLOWED_GROUP_IDS", "")
    if allowed_groups:
        try:
            group_ids = [int(x.strip()) for x in allowed_groups.split(",") if x.strip()]
            logger.info(f"✅ ALLOWED_GROUP_IDS={group_ids} - Список разрешенных групп")
        except ValueError:
            logger.error(f"❌ ALLOWED_GROUP_IDS имеет неверный формат: {allowed_groups}")
    else:
        logger.info("✅ ALLOWED_GROUP_IDS пуст - Все группы разрешены")
    
    allowed_topics = os.getenv("ALLOWED_TOPIC_IDS", "")
    if allowed_topics:
        try:
            topic_ids = [int(x.strip()) for x in allowed_topics.split(",") if x.strip()]
            logger.info(f"✅ ALLOWED_TOPIC_IDS={topic_ids} - Список разрешенных топиков")
        except ValueError:
            logger.error(f"❌ ALLOWED_TOPIC_IDS имеет неверный формат: {allowed_topics}")
    else:
        logger.info("✅ ALLOWED_TOPIC_IDS пуст - Все топики разрешены")

def check_downloads_folder():
    """Проверяет директорию загрузок"""
    logger.info("Проверка директории загрузок...")
    
    downloads_dir = os.path.join(os.getcwd(), "downloads")
    if not os.path.exists(downloads_dir):
        logger.warning(f"⚠️ Директория загрузок не существует: {downloads_dir}")
        try:
            os.makedirs(downloads_dir)
            logger.info(f"✅ Директория загрузок создана: {downloads_dir}")
        except Exception as e:
            logger.error(f"❌ Не удалось создать директорию загрузок: {e}")
    else:
        files = os.listdir(downloads_dir)
        logger.info(f"✅ Директория загрузок существует: {downloads_dir}")
        if files:
            logger.warning(f"⚠️ Директория загрузок содержит {len(files)} файлов")
        else:
            logger.info("✅ Директория загрузок пуста")

def check_python_requirements():
    """Проверяет установленные Python пакеты"""
    logger.info("Проверка Python зависимостей...")
    
    required_packages = ["aiogram", "yt-dlp", "python-dotenv"]
    for package in required_packages:
        try:
            __import__(package)
            logger.info(f"✅ Пакет {package} установлен")
        except ImportError:
            logger.error(f"❌ Пакет {package} не установлен")

def print_diagnostics_info():
    """Печатает информацию о системных модулях и переменных окружения"""
    logger.info("Информация о системе:")
    
    # Проверка версии Python
    python_version = sys.version
    logger.info(f"Python: {python_version}")
    
    # Проверка операционной системы
    os_info = f"{sys.platform}"
    logger.info(f"Операционная система: {os_info}")
    
    # Проверка текущей директории
    current_dir = os.getcwd()
    logger.info(f"Текущая директория: {current_dir}")
    
    # Список файлов в проекте
    files = [f for f in os.listdir() if os.path.isfile(f)]
    logger.info(f"Основные файлы проекта: {', '.join(files[:10])}")

def main():
    """Основная функция скрипта диагностики"""
    logger.info("===== Начало диагностики YouTube to Audio бота =====")
    
    print_diagnostics_info()
    check_env_config()
    check_downloads_folder()
    check_python_requirements()
    
    logger.info("===== Диагностика завершена =====")
    logger.info("Если вы видите ошибки выше, исправьте их перед запуском бота.")
    logger.info("Если все проверки прошли успешно, бот должен работать корректно.")

if __name__ == "__main__":
    main() 