# PowerShell скрипт для автоматической синхронизации кода и перезапуска служб
# Этот скрипт проверяет обновления в Git и перезапускает службы Windows при обнаружении изменений

# Настройки
$RepoPath = "C:\onlyWS"  # Путь к репозиторию на сервере
$ServiceNames = @("CryptoSpikesMain", "CryptoSpikesAPI", "CryptoSpikesWeb")  # Имена служб Windows
$LogFile = "C:\onlyWS\deploy.log"

# Функция для логирования
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    Add-Content -Path $LogFile -Value $logMessage
}

# Проверка существования репозитория
if (-not (Test-Path $RepoPath)) {
    Write-Log "ОШИБКА: Репозиторий не найден по пути $RepoPath"
    exit 1
}

# Переход в директорию репозитория
Set-Location $RepoPath

# Сохранение текущей ветки и состояния
$currentBranch = git rev-parse --abbrev-ref HEAD
$remoteHash = $null
$localHash = $null

try {
    # Получение информации об удаленном репозитории
    git fetch origin 2>&1 | Out-Null
    
    # Получение хешей коммитов
    $remoteHash = git rev-parse origin/$currentBranch 2>&1
    $localHash = git rev-parse HEAD 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ОШИБКА: Не удалось получить информацию о коммитах"
        exit 1
    }
    
    # Сравнение хешей
    if ($remoteHash -eq $localHash) {
        Write-Log "Изменений не обнаружено. Локальный коммит: $localHash"
        exit 0
    }
    
    Write-Log "Обнаружены изменения! Удаленный: $remoteHash, Локальный: $localHash"
    Write-Log "Начинаем обновление..."
    
    # Остановка служб
    Write-Log "Останавливаем службы..."
    foreach ($serviceName in $ServiceNames) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            if ($service.Status -eq "Running") {
                Stop-Service -Name $serviceName -Force
                Write-Log "Служба $serviceName остановлена"
            }
        } else {
            Write-Log "ПРЕДУПРЕЖДЕНИЕ: Служба $serviceName не найдена (возможно, еще не создана)"
        }
    }
    
    # Ожидание полной остановки служб
    Start-Sleep -Seconds 5
    
    # Обновление кода из Git
    Write-Log "Обновляем код из Git..."
    git pull origin $currentBranch 2>&1 | ForEach-Object {
        Write-Log $_
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ОШИБКА: Не удалось обновить код из Git"
        # Попытка перезапустить службы даже при ошибке
        foreach ($serviceName in $ServiceNames) {
            $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
            if ($service) {
                Start-Service -Name $serviceName
            }
        }
        exit 1
    }
    
    # Обновление Python зависимостей (опционально)
    Write-Log "Обновляем Python зависимости..."
    pip install -r requirements.txt --upgrade 2>&1 | Out-Null
    
    # Обновление Node.js зависимостей и сборка Next.js (если нужно)
    if (Test-Path "WEB\package.json") {
        Write-Log "Обновляем Node.js зависимости..."
        Set-Location "WEB"
        npm install 2>&1 | Out-Null
        npm run build 2>&1 | ForEach-Object {
            Write-Log $_
        }
        Set-Location $RepoPath
    }
    
    # Запуск служб
    Write-Log "Запускаем службы..."
    Start-Sleep -Seconds 2
    
    foreach ($serviceName in $ServiceNames) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            Start-Service -Name $serviceName
            Start-Sleep -Seconds 2
            $service = Get-Service -Name $serviceName
            if ($service.Status -eq "Running") {
                Write-Log "Служба $serviceName успешно запущена"
            } else {
                Write-Log "ОШИБКА: Служба $serviceName не запустилась. Статус: $($service.Status)"
            }
        } else {
            Write-Log "ПРЕДУПРЕЖДЕНИЕ: Служба $serviceName не найдена, пропускаем запуск"
        }
    }
    
    Write-Log "Обновление завершено успешно!"
    
} catch {
    Write-Log "КРИТИЧЕСКАЯ ОШИБКА: $($_.Exception.Message)"
    Write-Log $_.ScriptStackTrace
    exit 1
}

