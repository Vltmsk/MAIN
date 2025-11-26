# PowerShell script for automatic code synchronization and service restart
# This script checks for Git updates and restarts Windows services when changes are detected

# Settings
$RepoPath = "C:\onlyWS"
$ServiceNames = @("CryptoSpikesAPI", "CryptoSpikesWeb")
$LogFile = "C:\onlyWS\deploy.log"

# Logging function
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    
    # Безопасная запись в лог с обработкой блокировки файла
    $maxRetries = 3
    $retryDelay = 100  # миллисекунды
    $retryCount = 0
    $success = $false
    
    # Убеждаемся, что директория для лога существует
    $logDir = Split-Path -Path $LogFile -Parent
    if ($logDir -and -not (Test-Path $logDir)) {
        try {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        } catch {
            # Если не удалось создать директорию, просто пропускаем запись в файл
        }
    }
    
    while (-not $success -and $retryCount -lt $maxRetries) {
        try {
            # Используем FileStream с FileShare для избежания блокировок
            # FileMode.Append создаст файл, если его нет
            $fileStream = [System.IO.File]::Open($LogFile, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
            $writer = New-Object System.IO.StreamWriter($fileStream)
            $writer.WriteLine($logMessage)
            $writer.Flush()
            $writer.Close()
            $fileStream.Close()
            $success = $true
        } catch {
            $retryCount++
            if ($retryCount -lt $maxRetries) {
                Start-Sleep -Milliseconds $retryDelay
                $retryDelay *= 2  # Экспоненциальная задержка
            } else {
                # Если не удалось записать после всех попыток, просто выводим предупреждение
                Write-Host "WARNING: Failed to write to log file after $maxRetries attempts: $_" -ForegroundColor Yellow
            }
        }
    }
}

# Check if repository exists
if (-not (Test-Path $RepoPath)) {
    Write-Log "ERROR: Repository not found at path $RepoPath"
    exit 1
}

# Change to repository directory
Set-Location $RepoPath

# Save current branch and state
$currentBranch = git rev-parse --abbrev-ref HEAD
$remoteHash = $null
$localHash = $null

try {
    # Get information about remote repository
    git fetch origin 2>&1 | Out-Null
    
    # Get commit hashes
    $remoteHash = git rev-parse origin/$currentBranch 2>&1
    $localHash = git rev-parse HEAD 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: Failed to get commit information"
        exit 1
    }
    
    # Compare hashes
    if ($remoteHash -eq $localHash) {
        Write-Log "No changes detected. Local commit: $localHash"
        exit 0
    }
    
    Write-Log "Changes detected! Remote: $remoteHash, Local: $localHash"
    Write-Log "Starting update..."
    
    # Stop services
    Write-Log "Stopping services..."
    foreach ($serviceName in $ServiceNames) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            if ($service.Status -eq "Running") {
                Stop-Service -Name $serviceName -Force
                Write-Log "Service $serviceName stopped"
            }
        } else {
            Write-Log "WARNING: Service $serviceName not found (may not be created yet)"
        }
    }
    
    # Wait for services to fully stop
    Start-Sleep -Seconds 5
    
    # Update code from Git
    Write-Log "Updating code from Git..."
    
    # First do hard reset for full synchronization
    Write-Log "Synchronizing working directory with remote repository..."
    git reset --hard origin/$currentBranch 2>&1 | ForEach-Object {
        Write-Log $_
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: Failed to synchronize working directory"
        # Try to restart services even on error
        foreach ($serviceName in $ServiceNames) {
            $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
            if ($service) {
                Start-Service -Name $serviceName
            }
        }
        exit 1
    }
    
    # Clean untracked files and directories
    Write-Log "Cleaning untracked files..."
    git clean -fd 2>&1 | ForEach-Object {
        Write-Log $_
    }
    
    # Use pull for additional check
    $pullOutput = git pull origin $currentBranch 2>&1 | ForEach-Object {
        Write-Log $_
        $_
    }
    
    if ($LASTEXITCODE -ne 0) {
        # Check if error is related to untracked files
        $pullOutputString = $pullOutput -join "`n"
        if ($pullOutputString -match "untracked working tree files would be overwritten by merge") {
            Write-Log "Conflicting untracked files detected. Processing..."
            
            # Extract file names from error message
            $conflictFiles = @()
            $lines = $pullOutputString -split "`n"
            $foundMarker = $false
            
            foreach ($line in $lines) {
                if ($line -match "would be overwritten by merge") {
                    $foundMarker = $true
                    if ($line -match "would be overwritten by merge[:\s]+(.+)") {
                        $conflictFiles += $matches[1].Trim()
                    }
                } elseif ($foundMarker -and $line.Trim() -and -not ($line -match "Please move or remove")) {
                    $fileName = $line.Trim()
                    if ($fileName -and -not ($fileName -match "^\s*$")) {
                        $conflictFiles += $fileName
                    }
                } elseif ($line -match "Please move or remove") {
                    $foundMarker = $false
                }
            }
            
            # Remove conflicting files
            foreach ($file in $conflictFiles) {
                if ($file -and (Test-Path $file)) {
                    Write-Log "Removing conflicting file: $file"
                    Remove-Item -Path $file -Force -ErrorAction SilentlyContinue
                    if (Test-Path $file) {
                        Write-Log "WARNING: Failed to delete $file, trying to move..."
                        $backupPath = "$file.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
                        Move-Item -Path $file -Destination $backupPath -Force -ErrorAction SilentlyContinue
                    }
                }
            }
            
            # Retry pull
            Write-Log "Retrying update from Git..."
            git pull origin $currentBranch 2>&1 | ForEach-Object {
                Write-Log $_
            }
            
            if ($LASTEXITCODE -ne 0) {
                Write-Log "ERROR: Failed to update code from Git after conflict resolution"
                # Try to restart services even on error
                foreach ($serviceName in $ServiceNames) {
                    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
                    if ($service) {
                        Start-Service -Name $serviceName
                    }
                }
                exit 1
            }
        } else {
            Write-Log "ERROR: Failed to update code from Git"
            # Try to restart services even on error
            foreach ($serviceName in $ServiceNames) {
                $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
                if ($service) {
                    Start-Service -Name $serviceName
                }
            }
            exit 1
        }
    }
    
    # Update Python dependencies
    Write-Log "Updating Python dependencies..."
    $pipOutput = pip install -r requirements.txt --upgrade 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "WARNING: Python dependencies update had issues (exit code: $LASTEXITCODE)"
        $pipOutput | ForEach-Object { Write-Log $_ }
    }
    
    # Update Node.js dependencies and build Next.js
    if (Test-Path "WEB\package.json") {
        Write-Log "Updating Node.js dependencies..."
        Set-Location "WEB"
        $npmInstallOutput = npm install 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "ERROR: npm install failed (exit code: $LASTEXITCODE)"
            $npmInstallOutput | ForEach-Object { Write-Log $_ }
            Set-Location $RepoPath
            # Продолжаем выполнение, но логируем ошибку
        } else {
            Write-Log "Node.js dependencies updated successfully"
            Write-Log "Building Next.js application..."
            $npmBuildOutput = npm run build 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Log "ERROR: npm build failed (exit code: $LASTEXITCODE)"
                $npmBuildOutput | ForEach-Object { Write-Log $_ }
                Set-Location $RepoPath
                # Продолжаем выполнение, но логируем ошибку
            } else {
                Write-Log "Next.js application built successfully"
                $npmBuildOutput | ForEach-Object { Write-Log $_ }
            }
        }
        Set-Location $RepoPath
    }
    
    # Start services
    Write-Log "Starting services..."
    Start-Sleep -Seconds 2
    
    foreach ($serviceName in $ServiceNames) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            Start-Service -Name $serviceName
            Start-Sleep -Seconds 2
            $service = Get-Service -Name $serviceName
            if ($service.Status -eq "Running") {
                Write-Log "Service $serviceName started successfully"
            } else {
                Write-Log "ERROR: Service $serviceName failed to start. Status: $($service.Status)"
            }
        } else {
            Write-Log "WARNING: Service $serviceName not found, skipping start"
        }
    }
    
    Write-Log "Update completed successfully!"
    
} catch {
    Write-Log "CRITICAL ERROR: $($_.Exception.Message)"
    Write-Log $_.ScriptStackTrace
    exit 1
}