#!/bin/bash

# Остановка существующего бота
systemctl stop youtube-to-audio-bot.service

# Резервное копирование .env файла (если существует)
if [ -f "/var/www/youtube-to-audio/.env" ]; then
    cp /var/www/youtube-to-audio/.env /var/www/.env.backup
    echo "Резервная копия .env создана в /var/www/.env.backup"
fi

# Удаление существующей директории проекта
cd /var/www
rm -rf youtube-to-audio

# Клонирование репозитория с GitHub
git clone https://github.com/proto0654/youtube-to-audio.git

# Переход в директорию проекта
cd youtube-to-audio

# Восстановление .env файла из резервной копии (если существует)
if [ -f "/var/www/.env.backup" ]; then
    cp /var/www/.env.backup .env
    echo "Файл .env восстановлен из резервной копии"
else
    # Создаем .env файл, если резервной копии нет
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
    echo "Создан новый файл .env"
fi

# Создание директорий, если они не существуют
mkdir -p downloads services handlers keyboards data
chmod 777 downloads

# Создание виртуального окружения Python
apt-get update
apt-get install -y python3-full python3-venv ffmpeg
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Обновление службы systemd
cat > /etc/systemd/system/youtube-to-audio-bot.service << 'EOF'
[Unit]
Description=YouTube to Audio Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/youtube-to-audio
ExecStart=/var/www/youtube-to-audio/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка systemd и запуск бота
systemctl daemon-reload
systemctl enable youtube-to-audio-bot.service
systemctl start youtube-to-audio-bot.service

echo "Деплой из GitHub успешно завершен."
echo "Проверить статус бота можно командой: systemctl status youtube-to-audio-bot.service" 