#!/bin/bash

# Скрипт для ручной установки YouTube to Audio бота на сервер

# Проверка наличия токена бота
if [ -z "$1" ]; then
    echo "Использование: $0 <BOT_TOKEN>"
    echo "Пример: $0 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    exit 1
fi

BOT_TOKEN="$1"

# Установка зависимостей
echo "Установка зависимостей..."
apt-get update
apt-get install -y python3-pip python3-venv ffmpeg git

# Создание директории для проекта
echo "Создание директории для проекта..."
mkdir -p /root/youtube-to-audio
cd /root/youtube-to-audio

# Создание основных файлов проекта
echo "Создание файлов проекта..."

# Создаем requirements.txt
cat > requirements.txt << EOL
aiogram==3.20.0.post0
yt-dlp==2025.4.30
imageio-ffmpeg==0.6.0
ytmusicapi==1.10.3
python-dotenv==1.1.0
requests==2.31.0
typing-extensions>=4.8.0
cachetools>=5.3.1
EOL

# Создаем структуру директорий
mkdir -p handlers keyboards services downloads data

# Создаем .env файл
cat > .env << EOL
BOT_TOKEN=$BOT_TOKEN
GROUP_MODE_ENABLED=true
DIRECT_PROCESS_YOUTUBE_LINKS=true
MAX_REQUESTS_PER_USER=50
TOPICS_MODE_ENABLED=true
ALLOWED_TOPIC_IDS=
ALLOWED_GROUP_IDS=
EOL

# Создаем основные файлы
# Создаем yt-dlp.conf
cat > yt-dlp.conf << EOL
# Конфигурация yt-dlp
# Формат аудио
--extract-audio
--audio-format mp3
--audio-quality 0
# Именование файлов
--output "downloads/audio_%(id)s.%(ext)s"
# Настройки миниатюры
--write-thumbnail
--convert-thumbnails jpg
EOL

# Создание виртуального окружения
echo "Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
echo "Установка Python зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt

# Создание systemd сервиса
echo "Создание systemd сервиса..."
cat > /etc/systemd/system/youtube-to-audio-bot.service << EOL
[Unit]
Description=YouTube to Audio Telegram Bot
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/youtube-to-audio
ExecStart=/root/youtube-to-audio/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOL

# Сообщение о необходимости загрузить файлы
echo "======================================================================================"
echo "Скрипт установил базовые зависимости и создал структуру проекта."
echo "Теперь вам необходимо загрузить файлы проекта из репозитория:"
echo "https://github.com/proto0654/youtube-to-audio"
echo ""
echo "Или выполнить команду:"
echo "git clone https://github.com/proto0654/youtube-to-audio.git /tmp/youtube-to-audio && cp -R /tmp/youtube-to-audio/* /root/youtube-to-audio/"
echo ""
echo "После загрузки файлов запустите бота командой:"
echo "systemctl daemon-reload && systemctl enable youtube-to-audio-bot.service && systemctl start youtube-to-audio-bot.service"
echo "======================================================================================" 