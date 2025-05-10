from handlers.start import router as start_router
from handlers.callbacks import router as callbacks_router
from handlers.link_handler import router as link_router
from handlers.search import router as search_router
from handlers.group_handler import router as group_router

# Список всех роутеров из пакета handlers
routers = [start_router, callbacks_router, group_router, link_router, search_router]

# Пустой файл инициализации для модуля handlers 