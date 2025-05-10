# PowerShell скрипт для создания архива проекта

# Путь к проекту
$projectPath = (Get-Location).Path

# Имя архива
$archiveName = "youtube-to-audio.zip"

# Временный путь для сохранения архива
$tempPath = Join-Path $projectPath $archiveName

# Создание архива проекта
$excludeItems = @(
    ".git", 
    "__pycache__", 
    "downloads", 
    "*.pyc", 
    "*.pyo", 
    ".git*"
)

# Проверка наличия архива и удаление, если существует
if (Test-Path $tempPath) {
    Remove-Item $tempPath -Force
}

# Сообщение перед архивацией
Write-Host "Создание архива проекта для загрузки на сервер..."

# Создание архива без исключенных файлов
Compress-Archive -Path "$projectPath\*" -DestinationPath $tempPath -Force

Write-Host "Архив создан: $tempPath"
Write-Host "Теперь вы можете загрузить его на сервер через веб-интерфейс Timeweb"
Write-Host "Рекомендуемый путь для загрузки на сервере: /var/www/youtube-to-audio.zip" 