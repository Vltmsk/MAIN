# Скрипт для исправления проблемы сборки Next.js
# Убеждается, что файл обновлен и пересобирает проект

Write-Host "=== Исправление проблемы сборки Next.js ===" -ForegroundColor Cyan
Write-Host ""

# Переход в директорию проекта
$webPath = "C:\onlyWS\WEB"
if (-not (Test-Path $webPath)) {
    Write-Host "ОШИБКА: Директория $webPath не найдена!" -ForegroundColor Red
    exit 1
}

Set-Location $webPath
Write-Host "Текущая директория: $(Get-Location)" -ForegroundColor Gray
Write-Host ""

# Проверка файла DashboardShell.tsx
$dashboardFile = "app\(dashboard)\components\DashboardShell.tsx"
Write-Host "Проверка файла $dashboardFile..." -ForegroundColor Yellow

if (Test-Path $dashboardFile) {
    $content = Get-Content $dashboardFile -Raw
    
    # Проверяем, есть ли старый код со spread оператором
    if ($content -match "pairSettingsWithCharts\[key\] = \{\s*\.\.\.pairSettings\[key\]") {
        Write-Host "ОШИБКА: Обнаружен старый код со spread оператором!" -ForegroundColor Red
        Write-Host "Файл не обновлен. Необходимо синхронизировать с репозиторием." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Выполните:" -ForegroundColor Yellow
        Write-Host "  git add ." -ForegroundColor White
        Write-Host "  git commit -m 'Fix TypeScript types'" -ForegroundColor White
        Write-Host "  git pull" -ForegroundColor White
        exit 1
    } else {
        Write-Host "✓ Файл содержит исправленный код" -ForegroundColor Green
    }
    
    # Проверяем наличие явных типов
    if ($content -match "const newSettings:.*sendChart\?\: boolean") {
        Write-Host "✓ Найдены явные типы с sendChart" -ForegroundColor Green
    } else {
        Write-Host "ПРЕДУПРЕЖДЕНИЕ: Явные типы не найдены" -ForegroundColor Yellow
    }
} else {
    Write-Host "ОШИБКА: Файл $dashboardFile не найден!" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Очистка кэша Next.js
Write-Host "Очистка кэша Next.js..." -ForegroundColor Yellow
if (Test-Path ".next") {
    Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
    Write-Host "✓ Кэш .next удален" -ForegroundColor Green
} else {
    Write-Host "Кэш .next не найден (это нормально)" -ForegroundColor Gray
}

# Очистка кэша node_modules/.cache если есть
if (Test-Path "node_modules\.cache") {
    Remove-Item -Recurse -Force "node_modules\.cache" -ErrorAction SilentlyContinue
    Write-Host "✓ Кэш node_modules/.cache удален" -ForegroundColor Green
}

Write-Host ""

# Пересборка проекта
Write-Host "Запуск сборки Next.js..." -ForegroundColor Yellow
Write-Host ""

$buildOutput = npm run build 2>&1

# Вывод результата
$buildOutput | ForEach-Object {
    if ($_ -match "Failed to compile|Type error|error TS") {
        Write-Host $_ -ForegroundColor Red
    } elseif ($_ -match "Compiled successfully|Build completed") {
        Write-Host $_ -ForegroundColor Green
    } else {
        Write-Host $_
    }
}

# Проверка результата
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== Сборка успешно завершена! ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Теперь перезапустите службу:" -ForegroundColor Yellow
    Write-Host "  Restart-Service CryptoSpikesWeb" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "=== Сборка завершилась с ошибками ===" -ForegroundColor Red
    Write-Host ""
    Write-Host "Проверьте вывод выше для деталей ошибки." -ForegroundColor Yellow
    exit 1
}

