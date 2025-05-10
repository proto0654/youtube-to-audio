#!/bin/bash

# Скрипт для деплоя YouTube to Audio бота на Timeweb из репозитория GitHub

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

# Клонирование репозитория
echo "Клонирование репозитория..."
git clone https://github.com/proto0654/youtube-to-audio.git .

# Создание виртуального окружения
echo "Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
echo "Установка Python зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt

# Создание директории для загрузок
echo "Создание директории для загрузок..."
mkdir -p downloads
chmod 777 downloads

# Создание конфигурационного файла .env
echo "Создание конфигурационного файла .env..."
cat > .env << EOL
BOT_TOKEN=$BOT_TOKEN
GROUP_MODE_ENABLED=true
DIRECT_PROCESS_YOUTUBE_LINKS=true
MAX_REQUESTS_PER_USER=50
TOPICS_MODE_ENABLED=true
ALLOWED_TOPIC_IDS=
ALLOWED_GROUP_IDS=
EOL

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

# Запуск сервиса
echo "Запуск сервиса..."
systemctl daemon-reload
systemctl enable youtube-to-audio-bot.service
systemctl start youtube-to-audio-bot.service

echo "Деплой завершен!"
echo "Проверьте статус бота: systemctl status youtube-to-audio-bot.service"
echo "Просмотр логов: journalctl -u youtube-to-audio-bot.service -f" 