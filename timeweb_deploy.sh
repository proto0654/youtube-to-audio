#!/bin/bash

# Этот скрипт необходимо выполнить на сервере Timeweb

# Установка необходимых пакетов
apt-get update
apt-get install -y python3 python3-pip git ffmpeg

# Создание директории для проекта
mkdir -p /var/www/youtube-to-audio
cd /var/www/youtube-to-audio

# Здесь нужно заменить URL_ВАШЕГО_РЕПОЗИТОРИЯ на реальный URL вашего GitHub репозитория
# Например: https://github.com/username/youtube-to-audio.git
echo "Введите URL вашего GitHub репозитория:"
read REPO_URL

if [ -z "$REPO_URL" ]; then
  echo "URL репозитория не указан. Используем создание ручное копирование файлов."
  
  # Создаем директории
  mkdir -p downloads services handlers keyboards data
  chmod 777 downloads
  
  # Создаем .env файл
  cat > .env << 'EOF'
BOT_TOKEN=7973435952:AAEfPzVc5iFnPh1Ovt_bromjUGqi6MHkd1w

# Настройки для групповых чатов
GROUP_MODE_ENABLED=true
DIRECT_PROCESS_YOUTUBE_LINKS=true
MAX_REQUESTS_PER_USER=50

# Настройки для работы с комнатами (топиками)
TOPICS_MODE_ENABLED=true
# Список разрешенных тем через запятую (пустой = все темы)
ALLOWED_TOPIC_IDS=2
# Список разрешенных групп через запятую (пустой = все группы)
ALLOWED_GROUP_IDS=
EOF

  # Создаем requirements.txt
  cat > requirements.txt << 'EOF'
aiogram==3.20.0.post0
yt-dlp==2025.4.30
imageio-ffmpeg==0.6.0
ytmusicapi==1.10.3
python-dotenv==1.1.0
requests==2.31.0
typing-extensions>=4.8.0
cachetools>=5.3.1
EOF

  # Создаем yt-dlp.conf
  cat > yt-dlp.conf << 'EOF'
# Общие настройки
--no-playlist
--geo-bypass
--prefer-ffmpeg
--no-check-certificate

# Настройки аудио
--extract-audio
--audio-format mp3
--audio-quality 0

# Настройка имени выходного файла
--output "downloads/audio_%(id)s.%(ext)s"
EOF

else
  # Клонирование репозитория
  git clone "$REPO_URL" .
  
  # Проверка наличия директории downloads
  if [ ! -d "downloads" ]; then
    mkdir -p downloads
  fi
  
  # Установка прав на директорию загрузок
  chmod 777 downloads
fi

# Установка зависимостей Python
pip3 install -r requirements.txt

# Создание systemd сервиса для автозапуска бота
cat > /etc/systemd/system/youtube-to-audio-bot.service << 'EOF'
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
echo "Проверить статус бота можно командой: systemctl status youtube-to-audio-bot.service" 