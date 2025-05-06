import os
import logging
from typing import List, Optional
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота из .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("Не указан BOT_TOKEN в .env файле")
    exit(1)

# Создание директории для загрузок, если она не существует
DOWNLOADS_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Настройки для группового чата
GROUP_MODE_ENABLED = os.getenv("GROUP_MODE_ENABLED", "true").lower() == "true"
DIRECT_PROCESS_YOUTUBE_LINKS = os.getenv("DIRECT_PROCESS_YOUTUBE_LINKS", "true").lower() == "true"
MAX_REQUESTS_PER_USER = int(os.getenv("MAX_REQUESTS_PER_USER", "5"))

# Настройки для работы с комнатами (топиками)
TOPICS_MODE_ENABLED = os.getenv("TOPICS_MODE_ENABLED", "true").lower() == "true"

# Функция для парсинга списка ID из строки с запятыми
def parse_ids_list(env_var: str) -> List[int]:
    """Парсит строку с ID, разделенными запятыми, в список целых чисел"""
    value = os.getenv(env_var, "")
    if not value:
        return []
    try:
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError:
        logger.warning(f"Неверный формат ID в {env_var}. Используется пустой список.")
        return []

# Списки разрешенных групп и тем
ALLOWED_TOPIC_IDS = parse_ids_list("ALLOWED_TOPIC_IDS")
ALLOWED_GROUP_IDS = parse_ids_list("ALLOWED_GROUP_IDS")

# ID администраторов бота (если нужно)
ADMIN_USER_IDS = parse_ids_list("ADMIN_USER_IDS")

# Функция для проверки, разрешена ли обработка в данной группе и теме
def is_allowed_chat(chat_id: int, topic_id: Optional[int] = None) -> bool:
    """
    Проверяет, разрешена ли обработка в данной группе и теме
    
    Args:
        chat_id: ID чата/группы
        topic_id: ID темы/топика (None, если сообщение не в теме)
        
    Returns:
        True, если обработка разрешена, иначе False
    """
    # Если списки пусты, разрешены все группы/темы
    if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        return False
    
    if TOPICS_MODE_ENABLED and topic_id is not None:
        if ALLOWED_TOPIC_IDS and topic_id not in ALLOWED_TOPIC_IDS:
            return False
    
    return True 