# Инструкция по деплою на Windows Vultr сервер

## Подготовка

### 1. Подключение к серверу через RDP

1. Откройте **Remote Desktop Connection** (Подключение к удаленному рабочему столу) на вашем ПК
2. Введите IP-адрес вашего Vultr сервера
3. Введите логин и пароль администратора Windows
4. Подключитесь к серверу

### 2. Установка необходимого ПО на сервере

#### Python 3.8+
1. Скачайте Python с официального сайта: https://www.python.org/downloads/
2. При установке **обязательно** отметьте галочку "Add Python to PATH"
3. Установите Python

#### Node.js 18+
1. Скачайте Node.js с официального сайта: https://nodejs.org/
2. Установите Node.js (LTS версия рекомендуется)

#### Git для Windows
1. Скачайте Git с официального сайта: https://git-scm.com/download/win
2. Установите Git с настройками по умолчанию

#### Проверка установки
Откройте PowerShell или командную строку и выполните:
```powershell
python --version
node --version
npm --version
git --version
```

Все команды должны выводить версии установленных программ.

### 3. Настройка GitHub репозитория

#### На локальном ПК (ваш компьютер):

1. **Создайте репозиторий на GitHub**
   - Зайдите на https://github.com
   - Создайте новый репозиторий (например, `crypto-spikes-detector`)
   - **НЕ** создавайте README, .gitignore или лицензию (они уже есть)

2. **Инициализируйте Git в вашем проекте:**
```bash
cd C:\Users\Vlad\onlyWS
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

Замените `YOUR_USERNAME` и `YOUR_REPO_NAME` на ваши данные.

### 4. Клонирование репозитория на сервер

На сервере Vultr откройте PowerShell и выполните:

```powershell
cd C:\
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git onlyWS
```

Замените `YOUR_USERNAME` и `YOUR_REPO_NAME` на ваши данные.

### 5. Установка зависимостей на сервере

```powershell
cd C:\onlyWS

# Установка Python зависимостей
pip install -r requirements.txt

# Установка Node.js зависимостей и сборка Next.js
cd WEB
npm install
npm run build
cd ..
```

### 6. Настройка DNS и домена

1. Зайдите в панель управления вашего регистратора домена
2. Найдите раздел DNS настроек
3. Добавьте A-запись:
   - **Имя:** @ (или ваш домен без www)
   - **Тип:** A
   - **Значение:** IP-адрес вашего Vultr сервера
   - **TTL:** 3600 (или автоматически)
4. Опционально добавьте CNAME для www:
   - **Имя:** www
   - **Тип:** CNAME
   - **Значение:** ваш домен (например, example.com)

### 7. Настройка файрвола Windows

1. Откройте **Панель управления** → **Система и безопасность** → **Брандмауэр Защитника Windows**
2. Нажмите **Дополнительные параметры**
3. Выберите **Правила для входящих подключений** → **Создать правило**
4. Создайте правила для портов:
   - **Порт 80 (HTTP):**
     - Тип: Для порта
     - Протокол: TCP
     - Порт: 80
     - Действие: Разрешить подключение
     - Профили: Все
     - Имя: HTTP (Port 80)
   
   - **Порт 443 (HTTPS):**
     - Тип: Для порта
     - Протокол: TCP
     - Порт: 443
     - Действие: Разрешить подключение
     - Профили: Все
     - Имя: HTTPS (Port 443)

### 8. Настройка переменных окружения

На сервере создайте файл `.env` в корне проекта `C:\onlyWS\.env`:

```
DOMAIN=your-domain.com
```

Замените `your-domain.com` на ваш домен.

### 9. Установка NSSM (Non-Sucking Service Manager)

1. Скачайте NSSM: https://nssm.cc/download
2. Распакуйте архив (например, в `C:\nssm`)
3. Откройте PowerShell от имени администратора
4. Перейдите в папку с nssm.exe (например, `cd C:\nssm\win64`)
5. Создайте службы:

#### Служба для main.py (сбор данных с бирж):
```powershell
.\nssm.exe install CryptoSpikesMain "C:\Python\python.exe" "C:\onlyWS\main.py"
.\nssm.exe set CryptoSpikesMain AppDirectory "C:\onlyWS"
.\nssm.exe set CryptoSpikesMain DisplayName "Crypto Spikes Main Service"
.\nssm.exe set CryptoSpikesMain Description "Сбор данных с криптобирж"
.\nssm.exe set CryptoSpikesMain Start SERVICE_AUTO_START
.\nssm.exe set CryptoSpikesMain AppStdout "C:\onlyWS\logs\main_service.log"
.\nssm.exe set CryptoSpikesMain AppStderr "C:\onlyWS\logs\main_service_error.log"
```

**Важно:** Замените `C:\Python\python.exe` на реальный путь к python.exe на вашем сервере. 
Найдите путь командой: `where python`

#### Служба для api_server.py (FastAPI backend):
```powershell
.\nssm.exe install CryptoSpikesAPI "C:\Python\python.exe" "-m" "uvicorn" "api_server:app" "--host" "0.0.0.0" "--port" "8001"
.\nssm.exe set CryptoSpikesAPI AppDirectory "C:\onlyWS"
.\nssm.exe set CryptoSpikesAPI DisplayName "Crypto Spikes API Service"
.\nssm.exe set CryptoSpikesAPI Description "FastAPI Backend"
.\nssm.exe set CryptoSpikesAPI Start SERVICE_AUTO_START
.\nssm.exe set CryptoSpikesAPI AppStdout "C:\onlyWS\logs\api_service.log"
.\nssm.exe set CryptoSpikesAPI AppStderr "C:\onlyWS\logs\api_service_error.log"
```

#### Служба для Next.js (веб-интерфейс):
```powershell
.\nssm.exe install CryptoSpikesWeb "C:\Program Files\nodejs\node.exe" "C:\onlyWS\WEB\node_modules\.bin\next" "start" "--port" "3000"
.\nssm.exe set CryptoSpikesWeb AppDirectory "C:\onlyWS\WEB"
.\nssm.exe set CryptoSpikesWeb DisplayName "Crypto Spikes Web Service"
.\nssm.exe set CryptoSpikesWeb Description "Next.js Frontend"
.\nssm.exe set CryptoSpikesWeb Start SERVICE_AUTO_START
.\nssm.exe set CryptoSpikesWeb AppStdout "C:\onlyWS\logs\web_service.log"
.\nssm.exe set CryptoSpikesWeb AppStderr "C:\onlyWS\logs\web_service_error.log"
```

**Важно:** Замените `C:\Program Files\nodejs\node.exe` на реальный путь к node.exe.
Найдите путь командой: `where node`

#### Запуск служб:
```powershell
Start-Service CryptoSpikesMain
Start-Service CryptoSpikesAPI
Start-Service CryptoSpikesWeb
```

Проверка статуса:
```powershell
Get-Service CryptoSpikes*
```

### 10. Установка и настройка Nginx для Windows

1. Скачайте Nginx для Windows: http://nginx.org/en/download.html
2. Распакуйте в `C:\nginx`
3. Отредактируйте файл `C:\nginx\conf\nginx.conf`:

```nginx
worker_processes  1;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile        on;
    keepalive_timeout  65;

    # Upstream для Next.js
    upstream nextjs {
        server 127.0.0.1:3000;
    }

    # Upstream для FastAPI
    upstream api {
        server 127.0.0.1:8001;
    }

    server {
        listen       80;
        server_name  your-domain.com www.your-domain.com;

        # Редирект на HTTPS (после настройки SSL)
        # return 301 https://$server_name$request_uri;

        # Для Next.js
        location / {
            proxy_pass http://nextjs;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
        }

        # Для API
        location /api {
            proxy_pass http://api;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

**Важно:** Замените `your-domain.com` на ваш домен.

4. Создайте службу Nginx через NSSM:
```powershell
cd C:\nssm\win64
.\nssm.exe install Nginx "C:\nginx\nginx.exe"
.\nssm.exe set Nginx AppDirectory "C:\nginx"
.\nssm.exe set Nginx DisplayName "Nginx Web Server"
.\nssm.exe set Nginx Start SERVICE_AUTO_START
.\nssm.exe set Nginx AppStopMethodSkip 1
Start-Service Nginx
```

### 11. Настройка SSL сертификата (HTTPS)

Для Windows можно использовать:
- **Win-ACME** (Let's Encrypt для Windows): https://www.win-acme.com/
- Или бесплатные SSL сертификаты от Cloudflare

После получения сертификата обновите nginx.conf для поддержки HTTPS.

### 12. Настройка автоматической синхронизации через Task Scheduler

1. Откройте **Планировщик заданий** (Task Scheduler)
2. Создайте **Базовую задачу**
3. Настройте задачу:
   - **Имя:** Auto Deploy Sync
   - **Триггер:** Повторять каждые 5 минут
   - **Действие:** Запустить программу
   - **Программа:** `powershell.exe`
   - **Аргументы:** `-ExecutionPolicy Bypass -File "C:\onlyWS\deploy.ps1"`
   - **Запуск:** От имени администратора (если нужно)

4. Или используйте команду в PowerShell (от имени администратора):
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\onlyWS\deploy.ps1"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Highest
Register-ScheduledTask -TaskName "AutoDeploySync" -Action $action -Trigger $trigger -Principal $principal -Description "Автоматическая синхронизация кода с GitHub"
```

### 13. Проверка работы

1. Проверьте статус служб:
```powershell
Get-Service CryptoSpikes*
```

2. Проверьте логи:
   - `C:\onlyWS\logs\main_service.log`
   - `C:\onlyWS\logs\api_service.log`
   - `C:\onlyWS\logs\web_service.log`
   - `C:\onlyWS\deploy.log`

3. Откройте браузер и перейдите на ваш домен

4. Проверьте API: `http://your-domain.com/api/health`

## Работа с кодом

### Редактирование на локальном ПК:

1. Редактируйте код на вашем ПК
2. Сохраните изменения
3. Загрузите в GitHub:
```bash
git add .
git commit -m "Описание изменений"
git push
```

### Автоматическое обновление на сервере:

Скрипт `deploy.ps1` автоматически:
- Проверяет обновления каждые 5 минут
- Обнаруживает изменения в Git
- Останавливает службы
- Обновляет код
- Обновляет зависимости (если нужно)
- Перезапускает службы

Логи автоматического деплоя в файле: `C:\onlyWS\deploy.log`

## Ручное обновление на сервере (если нужно):

```powershell
cd C:\onlyWS
powershell.exe -ExecutionPolicy Bypass -File deploy.ps1
```

## Полезные команды

### Управление службами:
```powershell
# Остановка
Stop-Service CryptoSpikesMain
Stop-Service CryptoSpikesAPI
Stop-Service CryptoSpikesWeb

# Запуск
Start-Service CryptoSpikesMain
Start-Service CryptoSpikesAPI
Start-Service CryptoSpikesWeb

# Перезапуск
Restart-Service CryptoSpikesMain
Restart-Service CryptoSpikesAPI
Restart-Service CryptoSpikesWeb

# Статус
Get-Service CryptoSpikes*
```

### Просмотр логов:
```powershell
# Реал-тайм просмотр логов
Get-Content C:\onlyWS\logs\main_service.log -Wait
Get-Content C:\onlyWS\logs\api_service.log -Wait
Get-Content C:\onlyWS\deploy.log -Wait
```

### Проверка портов:
```powershell
netstat -an | findstr "3000"
netstat -an | findstr "8001"
netstat -an | findstr "80"
```

## Решение проблем

### Служба не запускается:
1. Проверьте логи ошибок в `C:\onlyWS\logs\`
2. Проверьте пути к Python и Node.js в настройках службы (NSSM)
3. Убедитесь что все зависимости установлены

### Порт занят:
```powershell
# Найти процесс на порту
netstat -ano | findstr ":3000"
# Убить процесс (замените PID на реальный)
taskkill /PID <PID> /F
```

### DNS не работает:
1. Подождите до 24 часов для распространения DNS
2. Проверьте DNS записи на сайте https://dnschecker.org/
3. Убедитесь что A-запись указывает на правильный IP

### Git не работает:
```powershell
# Настроить Git (если первый раз)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## Поддержка

При возникновении проблем проверьте:
1. Логи служб в `C:\onlyWS\logs\`
2. Лог деплоя: `C:\onlyWS\deploy.log`
3. Статус служб: `Get-Service CryptoSpikes*`

