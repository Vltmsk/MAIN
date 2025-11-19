# Решение проблемы 502 Bad Gateway

## Описание проблемы

Ошибка **502 Bad Gateway** означает, что nginx не может связаться с Next.js приложением. Службы могут быть запущены, но приложение не отвечает на запросы.

## Быстрая диагностика

Запустите скрипт диагностики на сервере:

```powershell
.\diagnose_web.ps1
```

Скрипт проверит:
- Статус службы CryptoSpikesWeb
- Запущенные процессы Node.js
- Открытые порты
- Существование собранного приложения
- Доступность портов

## Основные причины и решения

### 1. Next.js приложение не собрано

**Проблема:** Отсутствует папка `.next/standalone/server.js`

**Решение:**
```powershell
cd C:\onlyWS\WEB
npm install
npm run build
```

Проверьте, что файл существует:
```powershell
Test-Path C:\onlyWS\WEB\.next\standalone\server.js
```

### 2. Next.js слушает на неправильном порту

**Проблема:** nginx настроен на один порт, а Next.js слушает на другом

**Решение:**

1. Проверьте, на каком порту работает Next.js:
```powershell
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
```

2. Убедитесь, что служба использует правильный скрипт запуска:
   - Команда службы должна быть: `node C:\onlyWS\WEB\start-server.js`
   - Или с явным указанием порта: `$env:PORT=3000; node C:\onlyWS\WEB\.next\standalone\server.js`

3. Проверьте конфигурацию nginx на сервере:
   - Обычно находится в `/etc/nginx/sites-available/` или `/etc/nginx/conf.d/`
   - Убедитесь, что `proxy_pass` указывает на `http://localhost:3000` (или другой порт Next.js)

### 3. Next.js приложение упало после запуска

**Проблема:** Служба запущена, но процесс Node.js завершился

**Решение:**

1. Проверьте логи службы через Event Viewer:
   - Откройте `eventvwr.msc`
   - Перейдите в: `Windows Logs > Application`
   - Найдите записи от службы CryptoSpikesWeb

2. Проверьте логи приложения (если есть):
```powershell
Get-Content C:\onlyWS\logs\app.log -Tail 50
```

3. Попробуйте запустить вручную для проверки ошибок:
```powershell
cd C:\onlyWS\WEB
node start-server.js
```

### 4. Проблемы с файрволом

**Проблема:** Файрвол Windows блокирует порт

**Решение:**

1. Проверьте правила файрвола:
```powershell
Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*Node*" -or $_.DisplayName -like "*3000*"}
```

2. Откройте порт в файрволе (если нужно):
```powershell
New-NetFirewallRule -DisplayName "Next.js Port 3000" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
```

### 5. Неправильная конфигурация службы Windows

**Проблема:** Служба запускается с неправильными параметрами

**Решение:**

1. Проверьте конфигурацию службы:
```powershell
$service = Get-WmiObject Win32_Service | Where-Object { $_.Name -eq "CryptoSpikesWeb" }
$service.PathName
$service.StartName
```

2. Убедитесь, что:
   - Рабочая директория: `C:\onlyWS\WEB`
   - Команда запуска: `node start-server.js` или `node .next/standalone/server.js`
   - Переменная окружения PORT (если нужна): `3000`

3. Пересоздайте службу при необходимости:
```powershell
# Остановите и удалите службу
Stop-Service CryptoSpikesWeb
sc.exe delete CryptoSpikesWeb

# Создайте заново с правильными параметрами
# (используйте ваш скрипт создания службы)
```

## Проверка конфигурации nginx

На сервере проверьте конфигурацию nginx. Обычно она выглядит так:

```nginx
server {
    listen 80;
    server_name monitoringcrypto.ru;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Важно:** Убедитесь, что `proxy_pass` указывает на правильный порт (обычно 3000).

## Пошаговая проверка

1. **Проверьте статус службы:**
```powershell
Get-Service CryptoSpikesWeb
```

2. **Проверьте процессы Node.js:**
```powershell
Get-Process node -ErrorAction SilentlyContinue
```

3. **Проверьте открытые порты:**
```powershell
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
```

4. **Проверьте доступность локально:**
```powershell
Test-NetConnection -ComputerName localhost -Port 3000
```

5. **Проверьте логи:**
```powershell
# Логи службы через Event Viewer
eventvwr.msc

# Логи приложения (если есть)
Get-Content C:\onlyWS\logs\app.log -Tail 50
```

## Перезапуск службы

Если ничего не помогло, попробуйте перезапустить службу:

```powershell
Restart-Service CryptoSpikesWeb
Start-Sleep -Seconds 5
Get-Service CryptoSpikesWeb
```

## Контакты и дополнительная помощь

Если проблема не решена:
1. Запустите `diagnose_web.ps1` и сохраните вывод
2. Проверьте логи службы в Event Viewer
3. Попробуйте запустить Next.js вручную и проверьте ошибки

