# YouTube to Audio Telegram Bot

Телеграм-бот для конвертации YouTube видео в аудиофайлы.

## Особенности

- Конвертирует YouTube видео в MP3 аудио
- Поддерживает работу в личных чатах и группах
- Автоматически определяет YouTube-ссылки в сообщениях
- Отправляет аудиофайлы с обложкой и метаданными

## Установка

### Требования
- Python 3.9+
- ffmpeg
- Токен Telegram-бота от @BotFather

### Установка на сервер

1. Клонируйте репозиторий:
```bash
git clone https://github.com/proto0654/youtube-to-audio.git
cd youtube-to-audio
```

2. Создайте виртуальное окружение и установите зависимости:
```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Создайте файл .env с настройками:
```env
BOT_TOKEN=ваш_токен_бота
GROUP_MODE_ENABLED=true
DIRECT_PROCESS_YOUTUBE_LINKS=true
MAX_REQUESTS_PER_USER=50
TOPICS_MODE_ENABLED=true
ALLOWED_TOPIC_IDS=
ALLOWED_GROUP_IDS=
```

4. Запустите бота:
```bash
python main.py
```

### Установка на Timeweb

1. Скопируйте скрипт `github_deploy.sh` на сервер
2. Запустите скрипт:
```bash
chmod +x github_deploy.sh
./github_deploy.sh
```

## Использование

1. Добавьте бота в Telegram
2. Отправьте боту ссылку на YouTube видео
3. Бот конвертирует видео и отправит аудиофайл

## Настройка

### Переменные окружения

- `BOT_TOKEN` - Токен вашего Telegram-бота
- `GROUP_MODE_ENABLED` - Включить/выключить работу в группах (true/false)
- `DIRECT_PROCESS_YOUTUBE_LINKS` - Автоматическая обработка ссылок (true/false)
- `MAX_REQUESTS_PER_USER` - Ограничение запросов на пользователя
- `TOPICS_MODE_ENABLED` - Поддержка тем в группах (true/false)
- `ALLOWED_TOPIC_IDS` - Список разрешенных ID тем, разделенных запятой
- `ALLOWED_GROUP_IDS` - Список разрешенных ID групп, разделенных запятой

## Управление ботом на сервере

- Проверка статуса: `systemctl status youtube-to-audio-bot.service`
- Просмотр логов: `journalctl -u youtube-to-audio-bot.service -f`
- Перезапуск: `systemctl restart youtube-to-audio-bot.service`
- Остановка: `systemctl stop youtube-to-audio-bot.service`

## Лицензия

MIT 