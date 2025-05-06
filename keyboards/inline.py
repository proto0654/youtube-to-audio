from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Основная инлайн-клавиатура для выбора действия
def get_main_keyboard() -> InlineKeyboardMarkup:
    """
    Возвращает основную инлайн-клавиатуру с кнопками для ссылки и поиска
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔗 Ссылка", callback_data="link"),
            InlineKeyboardButton(text="🔎 Поиск", callback_data="search")
        ]
    ])
    return keyboard 