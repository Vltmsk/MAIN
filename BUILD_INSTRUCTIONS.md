# Инструкция по исправлению ошибки сборки на сервере

## Проблема
TypeScript ошибка: `'sendChart' does not exist in type` на строке 1503

## Решение (выполните на сервере)

### Шаг 1: Синхронизация изменений

```powershell
cd C:\onlyWS

# Если есть незакоммиченные изменения, сохраните их
git stash

# Получите последние изменения из репозитория
git pull origin main

# Если были сохраненные изменения, верните их
git stash pop
```

### Шаг 2: Проверка, что файл обновлен

Проверьте строку 1505 в файле:
```powershell
Get-Content "WEB\app\(dashboard)\components\DashboardShell.tsx" | Select-Object -Skip 1504 -First 1
```

Должна быть строка с `const newSettings:` - это означает, что файл обновлен.

### Шаг 3: Очистка кэша и пересборка

```powershell
cd C:\onlyWS\WEB

# Удалить кэш Next.js
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue

# Пересобрать проект
npm run build
```

### Шаг 4: Перезапуск службы

Если сборка успешна:
```powershell
Restart-Service CryptoSpikesWeb
```

## Быстрая команда (все в одном)

```powershell
cd C:\onlyWS
git pull origin main
cd WEB
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
npm run build
if ($LASTEXITCODE -eq 0) { Restart-Service CryptoSpikesWeb }
```

