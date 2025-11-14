# Быстрый старт: Деплой на Windows Vultr сервер

## Краткая инструкция (для тех, кто спешит)

### Шаг 1: Подготовка GitHub (на вашем ПК)

1. Создайте репозиторий на GitHub: https://github.com/new
2. Запустите `setup-git.bat` (Windows) или следуйте инструкции:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Шаг 2: Подключение к серверу Vultr

1. Откройте **Remote Desktop Connection** на вашем ПК
2. Введите IP-адрес Vultr сервера
3. Войдите с учетными данными администратора

### Шаг 3: Установка ПО на сервере

Откройте PowerShell на сервере и выполните:

#### Установка Python:
```powershell
# Скачайте и установите Python 3.8+ с https://www.python.org/downloads/
# При установке отметьте "Add Python to PATH"
```

#### Установка Node.js:
```powershell
# Скачайте и установите Node.js LTS с https://nodejs.org/
```

#### Установка Git:
```powershell
# Скачайте и установите Git с https://git-scm.com/download/win
```

#### Проверка установки:
```powershell
python --version  # Должно показать версию Python
node --version    # Должно показать версию Node.js
git --version     # Должно показать версию Git
```

### Шаг 4: Клонирование и настройка проекта

```powershell
# Перейти в корень диска C
cd C:\

# Клонировать репозиторий
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git onlyWS

# Перейти в папку проекта
cd onlyWS

# Установить Python зависимости
pip install -r requirements.txt

# Установить Node.js зависимости и собрать Next.js
cd WEB
npm install
npm run build
cd ..
```

### Шаг 5: Настройка переменных окружения

Создайте файл `C:\onlyWS\.env`:

```
DOMAIN=your-domain.com
```

**Важно:** Замените `your-domain.com` на ваш реальный домен!

### Шаг 6: Настройка DNS

1. Зайдите в панель управления вашего регистратора домена
2. Найдите раздел DNS настроек
3. Добавьте A-запись:
   - **Имя:** @
   - **Тип:** A
   - **Значение:** IP-адрес вашего Vultr сервера

### Шаг 7: Настройка файрвола

1. Откройте **Панель управления** → **Брандмауэр Защитника Windows** → **Дополнительные параметры**
2. Создайте правила для входящих подключений:
   - **Порт 80** (HTTP) - разрешить TCP
   - **Порт 443** (HTTPS) - разрешить TCP

### Шаг 8: Установка NSSM (для служб Windows)

```powershell
# Скачайте NSSM: https://nssm.cc/download
# Распакуйте в C:\nssm
cd C:\nssm\win64

# Найти путь к Python
where python
# Результат сохраните (например: C:\Python\python.exe)

# Найти путь к Node.js
where node
# Результат сохраните (например: C:\Program Files\nodejs\node.exe)
```

#### Создание служб:

**Служба для main.py:**
```powershell
.\nssm.exe install CryptoSpikesMain "C:\Python\python.exe" "C:\onlyWS\main.py"
.\nssm.exe set CryptoSpikesMain AppDirectory "C:\onlyWS"
.\nssm.exe set CryptoSpikesMain Start SERVICE_AUTO_START
.\nssm.exe set CryptoSpikesMain AppStdout "C:\onlyWS\logs\main_service.log"
.\nssm.exe set CryptoSpikesMain AppStderr "C:\onlyWS\logs\main_service_error.log"
```

**Служба для API:**
```powershell
.\nssm.exe install CryptoSpikesAPI "C:\Python\python.exe" "-m" "uvicorn" "api_server:app" "--host" "0.0.0.0" "--port" "8001"
.\nssm.exe set CryptoSpikesAPI AppDirectory "C:\onlyWS"
.\nssm.exe set CryptoSpikesAPI Start SERVICE_AUTO_START
.\nssm.exe set CryptoSpikesAPI AppStdout "C:\onlyWS\logs\api_service.log"
.\nssm.exe set CryptoSpikesAPI AppStderr "C:\onlyWS\logs\api_service_error.log"
```

**Служба для Next.js:**
```powershell
.\nssm.exe install CryptoSpikesWeb "C:\Program Files\nodejs\node.exe" "C:\onlyWS\WEB\node_modules\.bin\next" "start" "--port" "3000"
.\nssm.exe set CryptoSpikesWeb AppDirectory "C:\onlyWS\WEB"
.\nssm.exe set CryptoSpikesWeb Start SERVICE_AUTO_START
.\nssm.exe set CryptoSpikesWeb AppStdout "C:\onlyWS\logs\web_service.log"
.\nssm.exe set CryptoSpikesWeb AppStderr "C:\onlyWS\logs\web_service_error.log"
```

**Запуск служб:**
```powershell
Start-Service CryptoSpikesMain
Start-Service CryptoSpikesAPI
Start-Service CryptoSpikesWeb
```

**Проверка статуса:**
```powershell
Get-Service CryptoSpikes*
```

### Шаг 9: Установка Nginx (веб-сервер)

```powershell
# Скачайте Nginx для Windows: http://nginx.org/en/download.html
# Распакуйте в C:\nginx
```

Отредактируйте `C:\nginx\conf\nginx.conf`:

```nginx
http {
    upstream nextjs {
        server 127.0.0.1:3000;
    }

    upstream api {
        server 127.0.0.1:8001;
    }

    server {
        listen       80;
        server_name  your-domain.com www.your-domain.com;

        location / {
            proxy_pass http://nextjs;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }

        location /api {
            proxy_pass http://api;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }
    }
}
```

**Важно:** Замените `your-domain.com` на ваш домен!

Создайте службу для Nginx:
```powershell
cd C:\nssm\win64
.\nssm.exe install Nginx "C:\nginx\nginx.exe"
.\nssm.exe set Nginx AppDirectory "C:\nginx"
.\nssm.exe set Nginx Start SERVICE_AUTO_START
Start-Service Nginx
```

### Шаг 10: Настройка автоматической синхронизации

```powershell
# Откройте PowerShell от имени администратора
cd C:\onlyWS

# Создайте задачу в планировщике заданий
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\onlyWS\deploy.ps1"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Highest
Register-ScheduledTask -TaskName "AutoDeploySync" -Action $action -Trigger $trigger -Principal $principal -Description "Автоматическая синхронизация кода с GitHub"
```

### Шаг 11: Проверка работы

1. Откройте браузер и перейдите на ваш домен
2. Проверьте API: `http://your-domain.com/api/health`
3. Проверьте службы:
```powershell
Get-Service CryptoSpikes*
```

### Готово! 🎉

Теперь ваш сайт должен быть доступен по домену.

## Редактирование кода

1. Редактируйте код на вашем локальном ПК
2. Загрузите изменения в GitHub:
```bash
git add .
git commit -m "Описание изменений"
git push
```

3. Через 5 минут скрипт автоматически обновит код на сервере!

## Полезные команды

**Просмотр логов:**
```powershell
Get-Content C:\onlyWS\logs\main_service.log -Wait
Get-Content C:\onlyWS\deploy.log -Wait
```

**Перезапуск служб:**
```powershell
Restart-Service CryptoSpikesMain
Restart-Service CryptoSpikesAPI
Restart-Service CryptoSpikesWeb
```

**Ручное обновление:**
```powershell
cd C:\onlyWS
powershell.exe -ExecutionPolicy Bypass -File deploy.ps1
```

## Детальная документация

Подробные инструкции смотрите в файле **DEPLOY_WINDOWS.md**

