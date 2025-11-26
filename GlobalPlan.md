# Глобальный план развития проекта

## 1. Обновление торговых пар Binance Spot

### 1.1. Добавление USD в SPOT_QUOTE_ASSETS
- [ ] Добавить **USD** в список `SPOT_QUOTE_ASSETS` в `exchanges/binance/symbol_fetcher.py`
- [ ] Это автоматически включит все пары с USD в качестве котируемого актива (например, BTC/USD, ETH/USD и т.д.)
- [ ] Проверить доступность пар с USD через API Binance
- [ ] Протестировать загрузку символов с USD

### 1.2. Удаление SPOT_QUOTE_ASSETS
- [ ] Удалить из списка `SPOT_QUOTE_ASSETS` следующие котируемые активы:
  - **AUD** (австралийский доллар) - автоматически исключит все AUD-пары
  - **GBP** (британский фунт) - автоматически исключит все GBP-пары
  - **BIDR** (индонезийская рупия) - автоматически исключит все BIDR-пары
  - **AEUR** (EUR стейблкоин) - автоматически исключит все AEUR-пары
- [ ] Обновить константу `SPOT_QUOTE_ASSETS` в `exchanges/binance/symbol_fetcher.py`
- [ ] Проверить, что пары с этими активами больше не загружаются
- [ ] Обновить документацию по поддерживаемым котируемым активам

### 1.3. Обновление интерфейса после изменений SPOT_QUOTE_ASSETS
- [ ] Обновить список `SPOT_QUOTE_ASSETS` в `WEB/app/(dashboard)/components/SettingsTab/utils/pairUtils.ts`:
  - Добавить **USD** в список для Binance Spot
  - Удалить **AUD**, **GBP**, **BIDR**, **AEUR** из списка для Binance Spot
- [ ] Проверить компонент `ChartSettings.tsx`:
  - Убедиться, что кнопки для USD отображаются корректно
  - Проверить, что кнопки для AUD, GBP, BIDR, AEUR исчезли
  - Протестировать включение/выключение графиков для USD-пар
- [ ] Проверить компонент `SpikesSettings.tsx`:
  - Убедиться, что таблица настроек детектирования корректно отображает USD
  - Проверить, что строки для AUD, GBP, BIDR, AEUR исчезли из таблицы
  - Протестировать редактирование параметров для USD-пар
- [ ] Проверить компонент `PairSettingsEditor.tsx`:
  - Убедиться, что настройки для USD-пар работают корректно
- [ ] Проверить статистику и мониторинг:
  - Убедиться, что в `StatisticsTab.tsx` корректно отображаются данные для USD
  - Проверить `MonitoringTab.tsx` на корректность отображения активных символов
- [ ] Провести полное тестирование интерфейса:
  - Сохранение настроек графиков для USD
  - Сохранение настроек детектирования для USD
  - Проверка отображения в реальном времени
  - Проверка работы фильтров по биржам и рынкам

### 1.4. Миграция данных в базе данных (на сервере)
**Важно:** База данных находится на сервере, миграция будет выполнена автоматически при деплое через GitHub.

- [ ] Реализовать автоматическую миграцию в `BD/database.py`:
  - Добавить функцию `_migrate_remove_deprecated_quote_assets()` в метод `_init_database()`
  - Функция должна удалить из `options_json` всех пользователей настройки для AUD, GBP, BIDR, AEUR (ключи вида `binance_spot_AUD` и т.д.)
  - Логировать результат миграции
- [ ] Протестировать миграцию локально на тестовой БД с данными для удаляемых активов
- [ ] Создать резервную копию `BD/detected_alerts.db` на сервере перед деплоем
- [ ] Выполнить деплой: закоммитить изменения, запушить в GitHub, на сервере выполнить `git pull` и перезапустить приложение
- [ ] Проверить логи приложения на сервере и убедиться, что миграция выполнена успешно

**Файлы для изменения:**
- `BD/database.py` (добавить миграцию в `_init_database()`)
- `exchanges/binance/symbol_fetcher.py` (бэкенд)
- `WEB/app/(dashboard)/components/SettingsTab/utils/pairUtils.ts` (фронтенд)
- `WEB/app/(dashboard)/components/SettingsTab/ChartSettings.tsx` (проверка)
- `WEB/app/(dashboard)/components/SettingsTab/SpikesSettings.tsx` (проверка)

**Файлы для проверки:**
- `WEB/app/(dashboard)/components/SettingsTab/PairSettingsEditor.tsx`
- `WEB/app/(dashboard)/components/StatisticsTab.tsx`
- `WEB/app/(dashboard)/components/MonitoringTab.tsx`
- `exchanges/binance/ws_handler.py`
- `core/symbol_utils.py` (если есть нормализация)

---

## 2. Настройка отдельных Telegram-чатов для каждой биржи

### 2.1. Расширение структуры настроек пользователя
- [ ] Добавить в `options_json` поле `exchange_chat_mapping`:
  ```json
  {
    "exchange_chat_mapping": {
      "binance": {
        "enabled": true,
        "chat_id": "123456789"
      },
      "bybit": {
        "enabled": true,
        "chat_id": "987654321"
      },
      "bitget": {
        "enabled": false,
        "chat_id": ""
      },
      "gate": {
        "enabled": true,
        "chat_id": "111222333"
      },
      "hyperliquid": {
        "enabled": true,
        "chat_id": "444555666"
      }
    }
  }
  ```

### 2.2. Обновление логики отправки уведомлений
- [ ] Модифицировать `core/telegram_notifier.py`:
  - Добавить функцию `get_chat_id_for_exchange(user_id, exchange)`
  - Обновить `send_message()` для поддержки множественных чатов
- [ ] Обновить `core/spike_detector.py`:
  - При детекте стрелы проверять настройки чата для конкретной биржи
  - Отправлять уведомление в соответствующий чат

### 2.3. Веб-интерфейс для настройки
- [ ] Создать компонент `WEB/app/(dashboard)/components/SettingsTab/ExchangeChatSettings.tsx`
- [ ] Добавить UI для настройки чатов:
  - Выбор биржи
  - Ввод Chat ID
  - Переключатель включения/выключения
- [ ] Добавить валидацию Chat ID
- [ ] Сохранять настройки через API

### 2.4. API эндпоинты
- [ ] Добавить в `api_server.py`:
  - `GET /api/users/{user}/settings/exchange-chats` - получить настройки
  - `PUT /api/users/{user}/settings/exchange-chats` - обновить настройки
  - `POST /api/users/{user}/settings/exchange-chats/test` - тест отправки в чат

**Файлы для изменения:**
- `core/telegram_notifier.py`
- `core/spike_detector.py`
- `api_server.py`
- `BD/database.py` (если нужно хранить отдельно)
- `WEB/app/(dashboard)/components/SettingsTab/ExchangeChatSettings.tsx` (создать)
- `WEB/app/api/users/[user]/settings/exchange-chats/route.ts` (создать)

---

## 3. Добавление биржи Huobi (HTX)

### 3.1. Создание структуры биржи
- [ ] Создать директорию `exchanges/htx/`
- [ ] Создать файлы:
  - `__init__.py`
  - `symbol_fetcher.py` - загрузка списка символов
  - `ws_handler.py` - обработка WebSocket соединений
  - `README_htx.md` - документация по API

### 3.2. Реализация symbol_fetcher.py
- [ ] Реализовать загрузку спотовых пар через API:
  - `https://api.huobi.pro/v1/common/symbols`
  - Фильтрация по USDT парам
- [ ] Реализовать загрузку фьючерсных пар (если поддерживается)
- [ ] Добавить нормализацию символов (формат: `BTCUSDT`)

### 3.3. Реализация ws_handler.py
- [ ] Реализовать WebSocket подключение:
  - Endpoint: `wss://api.huobi.pro/ws`
  - Подписка на тикеры: `market.{symbol}.ticker`
  - Подписка на свечи: `market.{symbol}.kline.{period}`
- [ ] Обработка формата данных Huobi
- [ ] Обработка переподключений и ошибок

### 3.4. Интеграция в основной проект
- [ ] Добавить HTX в `config.py` (список бирж)
- [ ] Обновить `main.py` для инициализации HTX
- [ ] Добавить в `core/chart_generator.py` (если нужно)
- [ ] Обновить веб-интерфейс для отображения HTX

### 3.5. Тестирование
- [ ] Протестировать загрузку символов
- [ ] Протестировать WebSocket соединение
- [ ] Протестировать обработку данных
- [ ] Проверить детект стрел для HTX

**Файлы для создания:**
- `exchanges/htx/__init__.py`
- `exchanges/htx/symbol_fetcher.py`
- `exchanges/htx/ws_handler.py`
- `exchanges/htx/README_htx.md`

**Файлы для изменения:**
- `config.py`
- `main.py`
- `core/chart_generator.py` (если нужно)

---

## 4. Архитектура для работы разных программ в одном проекте

### 4.1. Анализ текущей архитектуры
- [ ] Провести аудит текущей структуры проекта
- [ ] Определить общие компоненты:
  - База данных
  - Логирование
  - Конфигурация
  - WebSocket менеджеры
  - Telegram уведомления

### 4.2. Модульная архитектура

#### 4.2.1. Модуль "Spike Detection" (ловля стрел)
- [ ] Выделить в отдельный модуль `modules/spike_detection/`
- [ ] Структура:
  ```
  modules/spike_detection/
    __init__.py
    detector.py          # Основная логика детекта
    config.py            # Конфигурация модуля
    handlers.py          # Обработчики событий
  ```
- [ ] Интеграция через события/коллбеки
- [ ] Независимая конфигурация через `options_json`

#### 4.2.2. Модуль "Cross-Exchange Arbitrage" (арбитраж между биржами)
- [ ] Создать модуль `modules/arbitrage/`
- [ ] Структура:
  ```
  modules/arbitrage/
    __init__.py
    detector.py          # Детектор арбитража
    price_collector.py   # Сбор цен с бирж
    calculator.py        # Расчет арбитражных возможностей
    config.py
  ```
- [ ] Использовать общие WebSocket соединения
- [ ] Отдельная таблица в БД для арбитражных алертов

#### 4.2.3. Модуль "Stablecoin Monitoring" (отслеживание стейблов)
- [ ] Создать модуль `modules/stablecoin/`
- [ ] Структура:
  ```
  modules/stablecoin/
    __init__.py
    monitor.py           # Мониторинг стейблкоинов
    config.py            # Конфигурация из Stable.md
    detector.py          # Детектор отклонений
  ```
- [ ] Использовать `core/stablecoin_config.py` (из STABLE_IMPLEMENTATION.md)
- [ ] Интеграция с общим детектором арбитража

#### 4.2.4. Модуль "Price Bot" (выдача цен по запросу)
- [ ] Создать модуль `modules/price_bot/`
- [ ] Структура:
  ```
  modules/price_bot/
    __init__.py
    bot.py               # Telegram бот
    price_fetcher.py     # Получение цен
    formatter.py         # Форматирование ответов
  ```
- [ ] Интеграция с `newproject/Price.py`
- [ ] Использовать общие WebSocket соединения для получения цен

### 4.3. Общий менеджер модулей
- [ ] Создать `core/module_manager.py`:
  ```python
  class ModuleManager:
      def register_module(name, module_instance)
      def enable_module(name, user_id)
      def disable_module(name, user_id)
      def get_module(name)
  ```
- [ ] Управление жизненным циклом модулей
- [ ] Распределение ресурсов (WebSocket соединения)

### 4.4. Общие сервисы
- [ ] `core/services/websocket_manager.py` - единый менеджер WebSocket
- [ ] `core/services/price_cache.py` - кэш цен для всех модулей
- [ ] `core/services/notification_service.py` - единый сервис уведомлений

### 4.5. Конфигурация модулей
- [ ] Расширить `options_json` для каждого модуля:
  ```json
  {
    "spikeDetection": { ... },
    "arbitrage": { ... },
    "stablecoin": { ... },
    "priceBot": { ... }
  }
  ```

**Файлы для создания:**
- `modules/__init__.py`
- `modules/spike_detection/` (директория)
- `modules/arbitrage/` (директория)
- `modules/stablecoin/` (директория)
- `modules/price_bot/` (директория)
- `core/module_manager.py`
- `core/services/websocket_manager.py`
- `core/services/price_cache.py`
- `core/services/notification_service.py`

**Файлы для рефакторинга:**
- `main.py` - разделить на модули
- `core/spike_detector.py` - перенести в модуль
- `core/telegram_notifier.py` - перенести в сервис

---

## 5. Отдельная часть проекта для отслеживания арбитража

### 5.1. Структура модуля арбитража

#### 5.1.1. Интеграция Price.py
- [ ] Адаптировать код из `newproject/Price.py`:
  - Функция получения цен с бирж
  - Форматирование таблиц
  - Telegram бот для запросов цен
- [ ] Создать `modules/price_bot/price_fetcher.py` на основе логики из Price.py
- [ ] Интегрировать с общим WebSocket менеджером

#### 5.1.2. Интеграция Arb_rab.py
- [ ] Адаптировать код из `newproject/Arb_rab.py`:
  - Детектор перекоса цен между биржами
  - Подтверждение детекта
  - Отправка алертов
- [ ] Создать `modules/arbitrage/cross_exchange_detector.py`
- [ ] Использовать общий сбор цен вместо отдельных запросов

#### 5.1.3. Интеграция Stable.md и STABLE_IMPLEMENTATION.md
- [ ] Создать `core/stablecoin_config.py` (из STABLE_IMPLEMENTATION.md)
- [ ] Создать `modules/stablecoin/stablecoin_detector.py`:
  - Использовать конфигурацию из Stable.md
  - Реализовать детектор из STABLE_IMPLEMENTATION.md
- [ ] Интегрировать с общим модулем арбитража

### 5.2. Веб-интерфейс для арбитража

#### 5.2.1. Создание страниц
- [ ] Создать `WEB/app/(dashboard)/arbitrage/page.tsx` - главная страница арбитража
- [ ] Создать вкладки:
  - `WEB/app/(dashboard)/arbitrage/components/CrossExchangeTab.tsx` - арбитраж между биржами
  - `WEB/app/(dashboard)/arbitrage/components/StablecoinTab.tsx` - арбитраж стейблкоинов
  - `WEB/app/(dashboard)/arbitrage/components/PriceComparisonTab.tsx` - сравнение цен (из Price.py)

#### 5.2.2. Компоненты для Cross-Exchange Arbitrage
- [ ] `components/ArbitrageAlertsTable.tsx` - таблица алертов
- [ ] `components/ArbitrageSettings.tsx` - настройки детектора
- [ ] `components/PriceDiffChart.tsx` - график разницы цен
- [ ] Использовать логику из `Arb_rab.py`

#### 5.2.3. Компоненты для Stablecoin Arbitrage
- [ ] `components/StablecoinAlertsTable.tsx` - таблица алертов стейблов
- [ ] `components/StablecoinSettings.tsx` - настройки (пороги, пары)
- [ ] `components/StablecoinPairsList.tsx` - список отслеживаемых пар
- [ ] Использовать конфигурацию из `Stable.md`

#### 5.2.4. Компоненты для Price Comparison
- [ ] `components/PriceTable.tsx` - таблица цен (из Price.py)
- [ ] `components/ExchangeSelector.tsx` - выбор бирж
- [ ] `components/PriceRequestForm.tsx` - форма запроса цены

### 5.3. API эндпоинты для арбитража
- [ ] `GET /api/arbitrage/cross-exchange/alerts` - алерты арбитража между биржами
- [ ] `GET /api/arbitrage/stablecoin/alerts` - алерты арбитража стейблов
- [ ] `GET /api/arbitrage/price-comparison` - сравнение цен (из Price.py)
- [ ] `POST /api/arbitrage/settings` - настройки детекторов
- [ ] `GET /api/arbitrage/stats` - статистика по арбитражу

### 5.4. База данных
- [ ] Создать таблицу `arbitrage_alerts`:
  ```sql
  CREATE TABLE arbitrage_alerts (
    id INTEGER PRIMARY KEY,
    type TEXT, -- 'cross_exchange' | 'stablecoin'
    exchange_from TEXT,
    exchange_to TEXT,
    symbol TEXT,
    price_from REAL,
    price_to REAL,
    diff_pct REAL,
    ts INTEGER,
    user_id INTEGER,
    ...
  )
  ```
- [ ] Создать таблицу `price_comparison_cache` для кэширования цен

### 5.5. Интеграция в main.py
- [ ] Добавить инициализацию модулей арбитража
- [ ] Подключить обработчики событий от WebSocket
- [ ] Настроить периодические проверки (для Arb_rab.py логики)

**Файлы для создания:**
- `modules/arbitrage/` (полная структура)
- `modules/stablecoin/` (полная структура)
- `modules/price_bot/` (полная структура)
- `WEB/app/(dashboard)/arbitrage/` (директория и страницы)
- `WEB/app/api/arbitrage/` (API эндпоинты)
- `BD/arbitrage_schema.sql` (схема БД)

**Файлы для изменения:**
- `main.py` - добавить инициализацию модулей
- `api_server.py` - добавить эндпоинты
- `BD/database.py` - добавить методы для арбитража

---

## 6. Общие задачи

### 6.1. Документация
- [ ] Обновить `README.md` с описанием новой архитектуры
- [ ] Создать `docs/ARCHITECTURE.md` - описание модульной архитектуры
- [ ] Создать `docs/ARBITRAGE.md` - документация по модулю арбитража
- [ ] Обновить документацию по API

### 6.2. Тестирование
- [ ] Написать unit-тесты для новых модулей
- [ ] Интеграционные тесты для арбитража
- [ ] Тесты WebSocket соединений для HTX
- [ ] Тесты Telegram уведомлений в разные чаты

### 6.3. Миграция данных
- [ ] Скрипт миграции для новых таблиц БД
- [ ] Миграция настроек пользователей (добавление exchange_chat_mapping)
- [ ] Резервное копирование перед миграцией

### 6.4. Производительность
- [ ] Оптимизация использования WebSocket соединений
- [ ] Кэширование цен для всех модулей
- [ ] Оптимизация запросов к БД
- [ ] Мониторинг использования ресурсов

---

## Приоритеты выполнения

### Высокий приоритет
1. Пункт 1 - Обновление торговых пар Binance Spot
2. Пункт 3 - Добавление биржи Huobi (HTX)
3. Пункт 4.1-4.2 - Архитектура модулей (базовая структура)

### Средний приоритет
4. Пункт 2 - Настройка отдельных чатов для бирж
5. Пункт 4.3-4.5 - Полная реализация модульной архитектуры
6. Пункт 5.1 - Интеграция кода арбитража

### Низкий приоритет
7. Пункт 5.2-5.5 - Веб-интерфейс и API для арбитража
8. Пункт 6 - Документация и тестирование

---

## Заметки

- При интеграции `Price.py` и `Arb_rab.py` необходимо адаптировать синхронный код под асинхронную архитектуру проекта
- WebSocket соединения должны быть общими для всех модулей для оптимизации ресурсов
- Настройки пользователей должны быть гибкими и позволять включать/выключать каждый модуль отдельно
- При добавлении HTX использовать существующий код из `Arb_rab.py` как референс (там уже есть HTX)

---

**Дата создания:** 2025-01-XX  
**Последнее обновление:** 2025-01-XX

