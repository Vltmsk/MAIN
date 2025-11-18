# PowerShell скрипт для автоматической синхронизации кода и перезапуска служб
# Этот скрипт проверяет обновления в Git и перезапускает только те службы, где были изменения

# Настройки
$RepoPath = "C:\onlyWS"  # Путь к репозиторию на сервере
$ServiceMap = @{
    "CryptoSpikesMain" = "Main"
    "CryptoSpikesAPI" = "API"
    "CryptoSpikesWeb" = "Web"
}
$LogFile = "C:\onlyWS\deploy.log"
$LastDeployFile = "C:\onlyWS\.last_deploy_hash"  # Файл для отслеживания последнего развернутого коммита

# Функция для логирования
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    Add-Content -Path $LogFile -Value $logMessage
}

# Функция для определения измененных файлов
function Get-ChangedFiles {
    param([string]$LocalHash, [string]$RemoteHash)
    
    $changedFiles = @()
    try {
        $diffOutput = git diff --name-only $LocalHash $RemoteHash 2>&1
        if ($LASTEXITCODE -eq 0) {
            $changedFiles = $diffOutput -split "`n" | Where-Object { $_ -ne "" }
        }
    } catch {
        Write-Log "Предупреждение: Не удалось получить список измененных файлов: $_"
    }
    return $changedFiles
}

# Функция для определения, какие службы нужно перезагрузить
function Get-ServicesToReload {
    param([string[]]$ChangedFiles)
    
    $servicesToReload = @{}
    $needsMainReload = $false
    $needsAPIReload = $false
    $needsWebReload = $false
    $needsPythonDeps = $false
    $needsNodeDeps = $false
    
    foreach ($file in $ChangedFiles) {
        $file = $file.Replace('\', '/')
        
        # Main.py или файлы, влияющие на main.py
        if ($file -match "^main\.py$" -or 
            $file -match "^core/" -or 
            $file -match "^exchanges/" -or 
            $file -match "^BD/" -or 
            $file -match "^config\.py$" -or
            $file -match "^clear_alerts\.py$") {
            $needsMainReload = $true
            Write-Log "  - $file → требует перезагрузки CryptoSpikesMain"
        }
        
        # API сервер или API routes в Next.js
        if ($file -match "^api_server\.py$" -or 
            $file -match "^WEB/app/api/") {
            $needsAPIReload = $true
            Write-Log "  - $file → требует перезагрузки CryptoSpikesAPI"
        }
        
        # Next.js файлы (кроме API routes, которые обрабатываются выше)
        if ($file -match "^WEB/" -and 
            -not ($file -match "^WEB/app/api/")) {
            $needsWebReload = $true
            Write-Log "  - $file → требует перезагрузки CryptoSpikesWeb"
        }
        
        # Зависимости
        if ($file -match "^requirements\.txt$") {
            $needsPythonDeps = $true
            $needsMainReload = $true
            $needsAPIReload = $true
            Write-Log "  - $file → требует обновления Python зависимостей и перезагрузки Main/API"
        }
        
        if ($file -match "^WEB/package\.json$" -or 
            $file -match "^WEB/package-lock\.json$") {
            $needsNodeDeps = $true
            $needsWebReload = $true
            Write-Log "  - $file → требует обновления Node.js зависимостей и перезагрузки Web"
        }
    }
    
    # Формируем список служб для перезагрузки
    if ($needsMainReload) {
        $servicesToReload["CryptoSpikesMain"] = @{
            "needsPythonDeps" = $needsPythonDeps
        }
    }
    
    if ($needsAPIReload) {
        $servicesToReload["CryptoSpikesAPI"] = @{
            "needsPythonDeps" = $needsPythonDeps
        }
    }
    
    if ($needsWebReload) {
        $servicesToReload["CryptoSpikesWeb"] = @{
            "needsNodeDeps" = $needsNodeDeps
        }
    }
    
    return $servicesToReload
}

# Функция для перезагрузки службы
function Restart-Service {
    param([string]$ServiceName, [hashtable]$Options = @{})
    
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Log "ПРЕДУПРЕЖДЕНИЕ: Служба $ServiceName не найдена, пропускаем"
        return $false
    }
    
    if ($service.Status -eq "Running") {
        Stop-Service -Name $ServiceName -Force
        Write-Log "Служба $ServiceName остановлена"
        Start-Sleep -Seconds 2
    }
    
    Start-Service -Name $ServiceName
    Start-Sleep -Seconds 2
    
    $service = Get-Service -Name $ServiceName
    if ($service.Status -eq "Running") {
        Write-Log "Служба $ServiceName успешно запущена"
        return $true
    } else {
        Write-Log "ОШИБКА: Служба $ServiceName не запустилась. Статус: $($service.Status)"
        return $false
    }
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
    # Проверяем статус рабочей директории
    $workingTreeStatus = git status --porcelain 2>&1
    if ($workingTreeStatus -and $LASTEXITCODE -eq 0) {
        $modifiedFiles = ($workingTreeStatus -split "`n" | Where-Object { $_ -ne "" -and $_ -match "^[^?]" })
        if ($modifiedFiles.Count -gt 0) {
            Write-Log "ВНИМАНИЕ: Обнаружены незакоммиченные изменения в рабочей директории:"
            foreach ($file in $modifiedFiles) {
                Write-Log "  $file"
            }
        }
    }
    
    # Получение информации об удаленном репозитории
    $fetchOutput = git fetch origin 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ПРЕДУПРЕЖДЕНИЕ: Ошибка при git fetch: $fetchOutput"
    }
    
    # Получение хешей коммитов
    $remoteHash = git rev-parse origin/$currentBranch 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ОШИБКА: Не удалось получить удаленный хеш коммита для origin/$currentBranch"
        exit 1
    }
    
    $localHash = git rev-parse HEAD 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ОШИБКА: Не удалось получить локальный хеш коммита"
        exit 1
    }
    
    # Проверяем последний развернутый коммит (защита от повторных перезагрузок)
    $lastDeployedHash = $null
    if (Test-Path $LastDeployFile) {
        $lastDeployedHash = (Get-Content $LastDeployFile -ErrorAction SilentlyContinue).Trim()
        if ($lastDeployedHash -eq $remoteHash) {
            Write-Log "Удаленный коммит уже развернут. Хеш: $remoteHash. Перезагрузка не требуется."
            # Обновляем локальный репозиторий, если нужно
            if ($localHash -ne $remoteHash) {
                Write-Log "Локальный репозиторий отстает, синхронизируем..."
                git pull origin $currentBranch 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Log "Синхронизация завершена"
                }
            }
            exit 0
        }
    }
    
    # Сравнение хешей
    if ($remoteHash -eq $localHash) {
        Write-Log "Изменений не обнаружено. Локальный коммит: $localHash"
        # Обновляем метку последнего развернутого коммита
        $remoteHash | Set-Content -Path $LastDeployFile -ErrorAction SilentlyContinue
        exit 0
    }
    
    Write-Log "Обнаружены изменения! Удаленный: $remoteHash, Локальный: $localHash"
    
    # Определяем измененные файлы ДО обновления
    Write-Log "Анализируем измененные файлы..."
    $changedFiles = Get-ChangedFiles -LocalHash $localHash -RemoteHash $remoteHash
    
    # Если не удалось определить измененные файлы, проверяем через git diff еще раз
    if ($changedFiles.Count -eq 0) {
        Write-Log "Попытка альтернативного метода определения изменений..."
        try {
            $diffOutput = git diff --name-only HEAD origin/$currentBranch 2>&1
            if ($LASTEXITCODE -eq 0 -and $diffOutput) {
                $changedFiles = $diffOutput -split "`n" | Where-Object { $_ -ne "" }
                Write-Log "Альтернативный метод: обнаружено файлов: $($changedFiles.Count)"
            }
        } catch {
            Write-Log "Альтернативный метод также не дал результатов"
        }
    }
    
    # Если все еще не удалось определить файлы, просто синхронизируем код без перезагрузки
    if ($changedFiles.Count -eq 0) {
        Write-Log "Не удалось определить измененные файлы. Выполняем синхронизацию без перезагрузки служб"
        git pull origin $currentBranch 2>&1 | ForEach-Object {
            Write-Log $_
        }
        
        # Проверяем после pull, действительно ли были изменения
        $newLocalHash = git rev-parse HEAD 2>&1
        if ($newLocalHash -eq $remoteHash) {
            Write-Log "Код синхронизирован. Хеши совпадают: $newLocalHash"
        } else {
            Write-Log "ВНИМАНИЕ: После pull хеши все еще различаются. Локальный: $newLocalHash, Удаленный: $remoteHash"
        }
        exit 0
    }
    
    Write-Log "Обнаружено измененных файлов: $($changedFiles.Count)"
    foreach ($file in $changedFiles) {
        Write-Log "  Изменен: $file"
    }
    
    $servicesToReload = Get-ServicesToReload -ChangedFiles $changedFiles
    
    if ($servicesToReload.Count -eq 0) {
        Write-Log "Нет служб для перезагрузки (изменены только служебные файлы)"
        # Всё равно делаем pull, чтобы синхронизировать код
        git pull origin $currentBranch 2>&1 | ForEach-Object {
            Write-Log $_
        }
        
        # Проверяем после pull
        $newLocalHash = git rev-parse HEAD 2>&1
        if ($newLocalHash -eq $remoteHash) {
            Write-Log "Код синхронизирован, перезагрузка не требуется. Хеш: $newLocalHash"
        }
        exit 0
    }
    
    Write-Log "Службы для перезагрузки: $($servicesToReload.Keys -join ', ')"
    Write-Log "Начинаем обновление..."
    
    # Останавливаем только нужные службы
    Write-Log "Останавливаем службы..."
    foreach ($serviceName in $servicesToReload.Keys) {
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
    Start-Sleep -Seconds 3
    
    # Обновление кода из Git
    Write-Log "Обновляем код из Git..."
    git pull origin $currentBranch 2>&1 | ForEach-Object {
        Write-Log $_
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ОШИБКА: Не удалось обновить код из Git"
        # Попытка перезапустить службы даже при ошибке
        foreach ($serviceName in $servicesToReload.Keys) {
            $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
            if ($service) {
                Start-Service -Name $serviceName
            }
        }
        exit 1
    }
    
    # Проверяем после pull, что хеши совпадают
    $newLocalHash = git rev-parse HEAD 2>&1
    if ($newLocalHash -ne $remoteHash) {
        Write-Log "ПРЕДУПРЕЖДЕНИЕ: После pull хеши все еще различаются. Локальный: $newLocalHash, Ожидался: $remoteHash"
    } else {
        Write-Log "Подтверждение: Код успешно обновлен. Новый хеш: $newLocalHash"
    }
    
    # Определяем, нужны ли обновления зависимостей
    $needsPythonDeps = ($servicesToReload.Values | Where-Object { $_.needsPythonDeps }).Count -gt 0
    $needsNodeDeps = ($servicesToReload.Values | Where-Object { $_.needsNodeDeps }).Count -gt 0
    
    # Обновление Python зависимостей (если нужно)
    if ($needsPythonDeps) {
        Write-Log "Обновляем Python зависимости..."
        pip install -r requirements.txt --upgrade 2>&1 | Out-Null
        Write-Log "Python зависимости обновлены"
    }
    
    # Обновление Node.js зависимостей и сборка Next.js (если нужно)
    if ($needsNodeDeps -and (Test-Path "WEB\package.json")) {
        Write-Log "Обновляем Node.js зависимости..."
        Set-Location "WEB"
        npm install 2>&1 | Out-Null
        Write-Log "Собираем Next.js приложение..."
        npm run build 2>&1 | ForEach-Object {
            Write-Log $_
        }
        Set-Location $RepoPath
        Write-Log "Node.js зависимости обновлены и приложение собрано"
    }
    
    # Запуск служб
    Write-Log "Запускаем службы..."
    Start-Sleep -Seconds 2
    
    foreach ($serviceName in $servicesToReload.Keys) {
        Restart-Service -ServiceName $serviceName -Options $servicesToReload[$serviceName] | Out-Null
    }
    
    Write-Log "Обновление завершено успешно! Перезагружено служб: $($servicesToReload.Count)"
    
    # Сохраняем хеш развернутого коммита
    $finalHash = git rev-parse HEAD 2>&1
    if ($LASTEXITCODE -eq 0) {
        $finalHash | Set-Content -Path $LastDeployFile -ErrorAction SilentlyContinue
        Write-Log "Сохранен хеш развернутого коммита: $finalHash"
    }
    
} catch {
    Write-Log "КРИТИЧЕСКАЯ ОШИБКА: $($_.Exception.Message)"
    Write-Log $_.ScriptStackTrace
    exit 1
}

