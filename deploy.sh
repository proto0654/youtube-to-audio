#!/bin/bash

# Установка необходимых пакетов
apt-get update
apt-get install -y python3 python3-pip git ffmpeg

# Клонирование репозитория (замените на свой репозиторий, если есть)
cd /var/www
mkdir -p youtube-to-audio
cd youtube-to-audio

# Копирование файлов проекта (если вы не используете Git)
# Если у вас есть Git репозиторий, используйте команду ниже вместо копирования файлов
# git clone YOUR_REPOSITORY_URL .

# Установка зависимостей Python
pip3 install -r requirements.txt

# Создание systemd сервиса для автозапуска бота
cat > /etc/systemd/system/youtube-to-audio-bot.service << EOF
[Unit]
Description=YouTube to Audio Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/youtube-to-audio
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка systemd
systemctl daemon-reload

# Запуск сервиса
systemctl enable youtube-to-audio-bot.service
systemctl start youtube-to-audio-bot.service

echo "Деплой завершен. Бот запущен как системный сервис." 