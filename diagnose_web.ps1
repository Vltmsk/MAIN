# Скрипт диагностики проблем с веб-сервером
# Проверяет состояние Next.js приложения и возможные причины 502 Bad Gateway

Write-Host "=== Диагностика веб-сервера ===" -ForegroundColor Cyan
Write-Host ""

# 1. Проверка службы CryptoSpikesWeb
Write-Host "1. Проверка службы CryptoSpikesWeb..." -ForegroundColor Yellow
$webService = Get-Service -Name "CryptoSpikesWeb" -ErrorAction SilentlyContinue
if ($webService) {
    Write-Host "   Статус службы: $($webService.Status)" -ForegroundColor $(if ($webService.Status -eq "Running") { "Green" } else { "Red" })
    
    # Получение информации о процессе
    $process = Get-WmiObject Win32_Service | Where-Object { $_.Name -eq "CryptoSpikesWeb" }
    if ($process) {
        Write-Host "   Путь к исполняемому файлу: $($process.PathName)" -ForegroundColor Gray
        Write-Host "   Рабочая директория: $($process.PathNameExecutable)" -ForegroundColor Gray
    }
} else {
    Write-Host "   ОШИБКА: Служба CryptoSpikesWeb не найдена!" -ForegroundColor Red
}

Write-Host ""

# 2. Проверка процессов Node.js
Write-Host "2. Проверка процессов Node.js..." -ForegroundColor Yellow
$nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue
if ($nodeProcesses) {
    Write-Host "   Найдено процессов Node.js: $($nodeProcesses.Count)" -ForegroundColor Green
    foreach ($proc in $nodeProcesses) {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        Write-Host "   PID: $($proc.Id) | Команда: $cmdLine" -ForegroundColor Gray
    }
} else {
    Write-Host "   ПРЕДУПРЕЖДЕНИЕ: Процессы Node.js не найдены!" -ForegroundColor Red
}

Write-Host ""

# 3. Проверка портов
Write-Host "3. Проверка открытых портов..." -ForegroundColor Yellow
$commonPorts = @(3000, 3001, 8000, 8001, 8080)
foreach ($port in $commonPorts) {
    $connection = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connection) {
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        Write-Host "   Порт $port открыт процессом: $($process.Name) (PID: $($process.Id))" -ForegroundColor Green
    } else {
        Write-Host "   Порт $port не используется" -ForegroundColor Gray
    }
}

Write-Host ""

# 4. Проверка существования собранного Next.js приложения
Write-Host "4. Проверка собранного Next.js приложения..." -ForegroundColor Yellow
$standalonePath = "C:\onlyWS\WEB\.next\standalone\server.js"
if (Test-Path $standalonePath) {
    Write-Host "   ✓ Файл server.js найден: $standalonePath" -ForegroundColor Green
    $fileInfo = Get-Item $standalonePath
    Write-Host "   Размер: $([math]::Round($fileInfo.Length / 1MB, 2)) MB" -ForegroundColor Gray
    Write-Host "   Дата изменения: $($fileInfo.LastWriteTime)" -ForegroundColor Gray
} else {
    Write-Host "   ✗ ОШИБКА: Файл server.js не найден!" -ForegroundColor Red
    Write-Host "   Необходимо собрать Next.js приложение: cd WEB && npm run build" -ForegroundColor Yellow
}

Write-Host ""

# 5. Проверка переменных окружения службы
Write-Host "5. Проверка переменных окружения службы..." -ForegroundColor Yellow
$service = Get-WmiObject Win32_Service | Where-Object { $_.Name -eq "CryptoSpikesWeb" }
if ($service) {
    $envVars = $service | Select-Object -ExpandProperty Environment
    if ($envVars) {
        Write-Host "   Переменные окружения:" -ForegroundColor Gray
        $envVars -split "`n" | ForEach-Object {
            if ($_ -match "PORT|BACKEND_URL|NODE_ENV") {
                Write-Host "   $_" -ForegroundColor Cyan
            }
        }
    } else {
        Write-Host "   Переменные окружения не заданы" -ForegroundColor Gray
    }
}

Write-Host ""

# 6. Проверка доступности локальных портов
Write-Host "6. Проверка доступности локальных портов..." -ForegroundColor Yellow
$testPorts = @(
    @{Port=3000; Name="Next.js (по умолчанию)"},
    @{Port=8001; Name="FastAPI API"}
)

foreach ($testPort in $testPorts) {
    try {
        $connection = Test-NetConnection -ComputerName localhost -Port $testPort.Port -WarningAction SilentlyContinue -InformationLevel Quiet
        if ($connection) {
            Write-Host "   ✓ Порт $($testPort.Port) ($($testPort.Name)) доступен" -ForegroundColor Green
        } else {
            Write-Host "   ✗ Порт $($testPort.Port) ($($testPort.Name)) недоступен" -ForegroundColor Red
        }
    } catch {
        Write-Host "   ✗ Порт $($testPort.Port) ($($testPort.Name)) недоступен: $_" -ForegroundColor Red
    }
}

Write-Host ""

# 7. Проверка логов службы (если доступны)
Write-Host "7. Рекомендации по проверке логов..." -ForegroundColor Yellow
Write-Host "   Проверьте логи службы CryptoSpikesWeb через Event Viewer:" -ForegroundColor Gray
Write-Host "   - Откройте Event Viewer (eventvwr.msc)" -ForegroundColor Gray
Write-Host "   - Перейдите в: Windows Logs > Application" -ForegroundColor Gray
Write-Host "   - Найдите записи от службы CryptoSpikesWeb" -ForegroundColor Gray

Write-Host ""

# 8. Рекомендации
Write-Host "=== Рекомендации ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Если служба запущена, но сайт не работает:" -ForegroundColor Yellow
Write-Host "1. Проверьте конфигурацию nginx - должен указывать на правильный порт Next.js" -ForegroundColor White
Write-Host "2. Убедитесь, что Next.js приложение собрано: cd WEB && npm run build" -ForegroundColor White
Write-Host "3. Проверьте, что Next.js слушает на порту, который указан в nginx (обычно 3000)" -ForegroundColor White
Write-Host "4. Проверьте файрвол Windows - порт должен быть открыт" -ForegroundColor White
Write-Host "5. Перезапустите службу: Restart-Service CryptoSpikesWeb" -ForegroundColor White
Write-Host ""
Write-Host "Для проверки конфигурации nginx на сервере:" -ForegroundColor Yellow
Write-Host "- Обычно конфигурация находится в: /etc/nginx/sites-available/ или /etc/nginx/conf.d/" -ForegroundColor White
Write-Host "- Проверьте upstream или proxy_pass - должен указывать на localhost:3000 (или другой порт Next.js)" -ForegroundColor White

