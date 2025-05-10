#!/bin/bash

# Этот скрипт нужно запустить на сервере Timeweb после загрузки архива

# Установка необходимых пакетов
apt-get update
apt-get install -y python3 python3-pip ffmpeg

# Создание директории для проекта
mkdir -p /var/www/youtube-to-audio

# Перемещение и распаковка архива (предположим, что он уже загружен в /var/www)
if [ -f /var/www/youtube-to-audio.zip ]; then
    unzip -o /var/www/youtube-to-audio.zip -d /var/www/youtube-to-audio
    echo "Архив распакован"
else
    echo "Ошибка: архив не найден в /var/www/youtube-to-audio.zip"
    echo "Пожалуйста, загрузите архив через веб-интерфейс Timeweb"
    exit 1
fi

# Переход в директорию проекта
cd /var/www/youtube-to-audio

# Создание директории для загрузок, если не существует
mkdir -p downloads
chmod 777 downloads

# Установка зависимостей Python
pip3 install -r requirements.txt

# Создание и настройка systemd-сервиса для автозапуска бота
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

# Перезагрузка systemd и запуск сервиса
systemctl daemon-reload
systemctl enable youtube-to-audio-bot.service
systemctl start youtube-to-audio-bot.service

echo "Бот успешно установлен и запущен как системный сервис"
echo "Проверить статус бота можно командой: systemctl status youtube-to-audio-bot.service" 