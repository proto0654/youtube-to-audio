# Инструкция по деплою YouTube to Audio бота на Timeweb

## Шаг 1: Подключение к серверу

1. Войдите в консоль Timeweb
2. Перейдите к вашему серверу и нажмите на кнопку "Консоль"
3. Войдите под пользователем root с вашим паролем

## Шаг 2: Скачивание и запуск скрипта деплоя

Выполните следующие команды для скачивания и запуска скрипта деплоя:

```bash
# Создаем временную директорию
mkdir -p /tmp/deploy

# Переходим в неё
cd /tmp/deploy

# Скачиваем скрипт деплоя
curl -O https://raw.githubusercontent.com/proto0654/youtube-to-audio/master/timeweb_deploy.sh

# Делаем скрипт исполняемым
chmod +x timeweb_deploy.sh

# Запускаем скрипт
./timeweb_deploy.sh
```

## Шаг 3: Настройка переменных окружения

После установки отредактируйте файл `.env` и добавьте токен вашего бота:

```bash
# Открываем файл .env
nano /root/youtube-to-audio/.env
```

Измените значение `BOT_TOKEN` на токен вашего бота, полученный от @BotFather.

Сохраните файл, нажав Ctrl+O, затем Enter, и выйдите, нажав Ctrl+X.

## Шаг 4: Перезапуск сервиса бота

```bash
# Перезапускаем сервис
systemctl restart youtube-to-audio-bot.service

# Проверяем статус
systemctl status youtube-to-audio-bot.service
```

## Управление ботом

- **Проверка статуса**: `systemctl status youtube-to-audio-bot.service`
- **Просмотр логов**: `journalctl -u youtube-to-audio-bot.service -f`
- **Перезапуск**: `systemctl restart youtube-to-audio-bot.service`
- **Остановка**: `systemctl stop youtube-to-audio-bot.service`

## Примечание

Если в будущем вы обновите репозиторий на GitHub, вы можете обновить бота на сервере следующим образом:

```bash
cd /root/youtube-to-audio
git pull
systemctl restart youtube-to-audio-bot.service
``` 