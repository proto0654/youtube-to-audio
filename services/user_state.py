import logging
import time
from collections import defaultdict
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class UserStateManager:
    """
    Класс для управления состояниями пользователей в групповом чате.
    Хранит информацию о текущих активных поисках, запросах и ограничениях на запросы.
    Поддерживает работу с топиками (комнатами) в больших группах.
    """
    
    def __init__(self):
        # Словарь для хранения состояний пользователей: (user_id, chat_id, topic_id) -> состояние
        self._user_states: Dict[Tuple[int, int, Optional[int]], Dict[str, Any]] = defaultdict(dict)
        
        # Счетчики запросов пользователей: user_id -> [(timestamp, count), ...]
        self._request_counters: Dict[int, list] = defaultdict(list)
        
        # Время в секундах для отслеживания запросов (1 час)
        self._request_window = 3600
    
    def _get_state_key(self, user_id: int, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> Tuple[int, Optional[int], Optional[int]]:
        """
        Формирует ключ для доступа к состоянию пользователя с учетом чата и топика
        
        Args:
            user_id: ID пользователя
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
            
        Returns:
            Кортеж (user_id, chat_id, topic_id)
        """
        return (user_id, chat_id, topic_id)
    
    def set_user_state(self, user_id: int, state_name: str, value: Any, 
                       chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
        """
        Устанавливает значение определенного состояния для пользователя
        
        Args:
            user_id: ID пользователя
            state_name: Название состояния
            value: Значение состояния
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
        """
        key = self._get_state_key(user_id, chat_id, topic_id)
        self._user_states[key][state_name] = value
        logger.debug(f"Установлено состояние {state_name}={value} для пользователя {user_id} в чате {chat_id} (тема {topic_id})")
    
    def get_user_state(self, user_id: int, state_name: str, default=None,
                       chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> Any:
        """
        Получает значение определенного состояния для пользователя
        
        Args:
            user_id: ID пользователя
            state_name: Название состояния
            default: Значение по умолчанию, если состояние не найдено
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
            
        Returns:
            Значение состояния или default, если состояние не найдено
        """
        key = self._get_state_key(user_id, chat_id, topic_id)
        return self._user_states.get(key, {}).get(state_name, default)
    
    def clear_user_state(self, user_id: int, state_name: Optional[str] = None,
                         chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
        """
        Очищает состояние пользователя.
        
        Args:
            user_id: ID пользователя
            state_name: Название состояния для очистки. Если None, очищаются все состояния.
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
        """
        key = self._get_state_key(user_id, chat_id, topic_id)
        if state_name is None:
            if key in self._user_states:
                del self._user_states[key]
                logger.debug(f"Очищены все состояния для пользователя {user_id} в чате {chat_id} (тема {topic_id})")
        else:
            if key in self._user_states and state_name in self._user_states[key]:
                del self._user_states[key][state_name]
                logger.debug(f"Очищено состояние {state_name} для пользователя {user_id} в чате {chat_id} (тема {topic_id})")
    
    def is_user_waiting_for_query(self, user_id: int, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> bool:
        """
        Проверяет, ожидает ли пользователь ввода поискового запроса
        
        Args:
            user_id: ID пользователя
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
            
        Returns:
            True, если пользователь ожидает ввода запроса, иначе False
        """
        return self.get_user_state(user_id, "waiting_for_query", False, chat_id, topic_id)
    
    def set_user_waiting_for_query(self, user_id: int, waiting: bool = True, 
                                  chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
        """
        Устанавливает флаг ожидания ввода поискового запроса для пользователя
        
        Args:
            user_id: ID пользователя
            waiting: Флаг ожидания
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
        """
        self.set_user_state(user_id, "waiting_for_query", waiting, chat_id, topic_id)
    
    def is_user_browsing_results(self, user_id: int, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> bool:
        """
        Проверяет, просматривает ли пользователь результаты поиска
        
        Args:
            user_id: ID пользователя
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
            
        Returns:
            True, если пользователь просматривает результаты, иначе False
        """
        return self.get_user_state(user_id, "browsing_results", False, chat_id, topic_id)
    
    def set_user_browsing_results(self, user_id: int, browsing: bool = True, results=None, 
                                 chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
        """
        Устанавливает флаг просмотра результатов поиска для пользователя
        
        Args:
            user_id: ID пользователя
            browsing: Флаг просмотра
            results: Результаты поиска (опционально)
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
        """
        self.set_user_state(user_id, "browsing_results", browsing, chat_id, topic_id)
        if results is not None:
            self.set_user_state(user_id, "search_results", results, chat_id, topic_id)
    
    def get_user_search_results(self, user_id: int, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> dict:
        """
        Получает результаты поиска для пользователя
        
        Args:
            user_id: ID пользователя
            chat_id: ID чата/группы (None для личных чатов)
            topic_id: ID темы/топика (None, если сообщение не в теме)
            
        Returns:
            Словарь с результатами поиска или пустой словарь
        """
        return self.get_user_state(user_id, "search_results", {}, chat_id, topic_id)
    
    def increment_user_requests(self, user_id: int) -> int:
        """
        Увеличивает счетчик запросов пользователя и удаляет старые записи
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Текущее количество запросов пользователя за последний час
        """
        current_time = time.time()
        
        # Очищаем старые записи
        self._request_counters[user_id] = [
            (ts, count) for ts, count in self._request_counters[user_id] 
            if current_time - ts < self._request_window
        ]
        
        # Добавляем новую запись
        self._request_counters[user_id].append((current_time, 1))
        
        # Возвращаем текущее общее количество
        return sum(count for _, count in self._request_counters[user_id])
    
    def get_user_requests_count(self, user_id: int) -> int:
        """
        Получает количество запросов пользователя за последний час
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество запросов за последний час
        """
        current_time = time.time()
        
        # Очищаем старые записи и считаем оставшиеся
        count = sum(
            count for ts, count in self._request_counters[user_id] 
            if current_time - ts < self._request_window
        )
        
        return count

# Создаем глобальный экземпляр менеджера состояний
user_state_manager = UserStateManager() 