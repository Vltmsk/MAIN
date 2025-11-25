# План рефакторинга компонентов

Этот документ описывает план разбиения больших компонентов на более мелкие, переиспользуемые части.

## Общая стратегия

1. **Извлечение утилит** - функции форматирования, валидации, преобразования данных
2. **Извлечение хуков** - логика работы с состоянием, API запросы
3. **Извлечение подкомпонентов** - UI части, которые можно переиспользовать
4. **Извлечение типов** - общие типы в отдельные файлы

---

## Компоненты, которые остаются без изменений

Следующие компоненты **не будут разбиваться**, так как они имеют приемлемый размер и вряд ли будут значительно расширяться:

- ✅ **ChatIdHelp.tsx** (322 строки) - оставляем как есть
- ✅ **DashboardShell.tsx** (748 строк) - оставляем как есть
- ✅ **MetricsAdminTab.tsx** (200 строк) - оставляем как есть
- ✅ **StatisticsTab.tsx** (824 строки) - оставляем как есть
- ✅ **MonitoringTab.tsx** (192 строки) - оставляем как есть

---

## Компоненты для рефакторинга

## 1. AdminTab.tsx (1,278 строк)

### Текущая структура:
- Управление пользователями
- Настройки пользователей
- Логи ошибок
- Настройки бирж и пар

### Предлагаемое разбиение:

#### Файлы:
```
components/
  AdminTab/
    index.tsx                    # Главный компонент (150 строк)
    UserManagement.tsx            # Управление пользователями (300 строк)
    UserSettingsEditor.tsx        # Редактор настроек пользователя (400 строк)
    ErrorLogsPanel.tsx            # Панель логов ошибок (250 строк)
    ExchangeSettingsEditor.tsx    # Редактор настроек бирж (200 строк)
    hooks/
      useAdminUsers.ts            # Хук для работы с пользователями (100 строк)
      useErrorLogs.ts             # Хук для работы с логами (80 строк)
    utils/
      validators.ts               # Валидация (50 строк)
      userStatus.ts               # Логика статусов пользователей (50 строк)
    types.ts                      # Типы (50 строк)
```

#### Компоненты:
- `AdminTab` - главный компонент
- `UserManagement` - список пользователей, создание, удаление
- `UserSettingsEditor` - редактирование настроек пользователя
- `ErrorLogsPanel` - панель с логами ошибок
- `ExchangeSettingsEditor` - настройки бирж и пар

#### Хуки:
- `useAdminUsers` - CRUD операции с пользователями
- `useErrorLogs` - загрузка и фильтрация логов

#### Утилиты:
- `validateBotToken` - валидация Bot Token
- `validateChatId` - валидация Chat ID
- `getAdminUserStatus` - определение статуса пользователя

---

## 2. SettingsTab.tsx (3,988 строк) - САМЫЙ БОЛЬШОЙ

### Текущая структура:
- Настройки Telegram
- Формат сообщений
- Настройки прострелов (фильтры бирж, пары)
- Чёрный список
- Условные шаблоны/стратегии

### Предлагаемое разбиение:

#### Файлы:
```
components/
  SettingsTab/
    index.tsx                    # Главный компонент (200 строк)
    SettingsNavigation.tsx        # Навигация по подтемам (100 строк)
    TelegramSettings.tsx          # Настройки Telegram (300 строк)
    MessageFormatSettings.tsx     # Формат сообщений (400 строк)
    SpikesSettings.tsx            # Настройки прострелов (600 строк)
    BlacklistSettings.tsx          # Чёрный список (150 строк)
    StrategiesSettings.tsx        # Условные шаблоны (800 строк)
    components/
      ExchangeFilter.tsx          # Фильтр биржи (200 строк)
      PairSettingsEditor.tsx      # Редактор настроек пары (300 строк)
      StrategyEditor.tsx          # Редактор стратегии (400 строк)
      ConditionEditor.tsx        # Редактор условия (200 строк)
      MessageTemplateEditor.tsx   # Редактор шаблона сообщения (300 строк)
      # EmojiPickerButton.tsx - УДАЛЕНО: кнопка emoji picker уже удалена из проекта
    hooks/
      useSettings.ts              # Хук для загрузки/сохранения настроек (200 строк)
      useTelegramSettings.ts     # Хук для настроек Telegram (100 строк)
      useMessageTemplate.ts       # Хук для работы с шаблонами (150 строк)
      useStrategies.ts            # Хук для условных шаблонов (200 строк)
    utils/
      validators.ts               # Валидация (100 строк)
      formatters.ts               # Форматирование (50 строк)
      templateUtils.ts            # Утилиты для шаблонов (200 строк)
      placeholderMap.ts           # Маппинг плейсхолдеров (50 строк)
    types.ts                      # Типы (100 строк)
```

#### Компоненты:
- `SettingsTab` - главный компонент с подтемами
- `SettingsNavigation` - навигация по подтемам
- `TelegramSettings` - настройки Telegram (Chat ID, Bot Token)
- `MessageFormatSettings` - формат сообщения
- `SpikesSettings` - фильтры бирж, настройки пар
- `BlacklistSettings` - управление чёрным списком
- `StrategiesSettings` - условные шаблоны/стратегии

#### Подкомпоненты:
- `ExchangeFilter` - фильтр для одной биржи
- `PairSettingsEditor` - редактор настроек для пары
- `StrategyEditor` - редактор одной стратегии
- `ConditionEditor` - редактор одного условия
- `MessageTemplateEditor` - редактор шаблона сообщения
- ~~`EmojiPickerButton`~~ - **УДАЛЕНО**: кнопка emoji picker уже удалена из проекта

**Примечание**: При рефакторинге можно удалить мертвый код, связанный с EmojiPicker:
- Импорт `EmojiPicker` (строка 8)
- Состояние `showEmojiPicker` (строка 136)
- Refs `emojiButtonRef` и `conditionalEmojiButtonRefs` (строки 143-144)
- Функция `insertEmoji` (строка 587) - если не используется
- Рендер `EmojiPicker` компонентов (строки 1947-1971, 3939-3967)

#### Хуки:
- `useSettings` - загрузка и сохранение всех настроек
- `useTelegramSettings` - работа с настройками Telegram
- `useMessageTemplate` - работа с шаблонами сообщений
- `useStrategies` - работа с условными шаблонами

#### Утилиты:
- `validateBotToken` - валидация Bot Token
- `validateChatId` - валидация Chat ID
- `convertToTechnicalKeys` - преобразование плейсхолдеров
- `convertToFriendlyKeys` - обратное преобразование
- `generateMessagePreview` - генерация превью сообщения

---

## Порядок выполнения рефакторинга

### Этап 1: Подготовка (низкий риск)
1. ✅ Создать структуру папок
2. ✅ Вынести общие типы в `types.ts`
3. ✅ Вынести утилиты форматирования и валидации

### Этап 2: AdminTab.tsx (средний риск)
1. Создать структуру папок `AdminTab/`
2. Вынести типы в `types.ts`
3. Вынести утилиты валидации в `utils/validators.ts`
4. Вынести логику статусов в `utils/userStatus.ts`
5. Создать хук `useAdminUsers.ts`
6. Создать хук `useErrorLogs.ts`
7. Создать компонент `UserManagement.tsx`
8. Создать компонент `UserSettingsEditor.tsx`
9. Создать компонент `ErrorLogsPanel.tsx`
10. Создать компонент `ExchangeSettingsEditor.tsx`
11. Обновить главный компонент `index.tsx`

### Этап 3: SettingsTab.tsx (высокий риск - самый сложный)
1. Создать структуру папок `SettingsTab/`
2. Вынести типы в `types.ts`
3. Вынести утилиты в `utils/`:
   - `validators.ts` - валидация
   - `formatters.ts` - форматирование
   - `templateUtils.ts` - утилиты для шаблонов
   - `placeholderMap.ts` - маппинг плейсхолдеров
4. Создать хуки:
   - `useSettings.ts` - загрузка/сохранение настроек
   - `useTelegramSettings.ts` - настройки Telegram
   - `useMessageTemplate.ts` - работа с шаблонами
   - `useStrategies.ts` - условные шаблоны
5. Создать подкомпоненты в `components/`:
   - `ExchangeFilter.tsx`
   - `PairSettingsEditor.tsx`
   - `StrategyEditor.tsx`
   - `ConditionEditor.tsx`
   - `MessageTemplateEditor.tsx`
   - `EmojiPickerButton.tsx`
6. Создать основные компоненты:
   - `SettingsNavigation.tsx`
   - `TelegramSettings.tsx`
   - `MessageFormatSettings.tsx`
   - `SpikesSettings.tsx`
   - `BlacklistSettings.tsx`
   - `StrategiesSettings.tsx`
7. Обновить главный компонент `index.tsx`

---

## Рекомендации по реализации

1. **Начните с утилит и типов** - они используются везде
2. **Создавайте хуки постепенно** - извлекайте логику по частям
3. **Тестируйте после каждого этапа** - убедитесь, что ничего не сломалось
4. **Используйте поиск по коду** - найдите все места использования перед рефакторингом
5. **Сохраняйте обратную совместимость** - экспортируйте старые компоненты как обёртки

---

## Пример структуры после рефакторинга

```
WEB/
  app/
    (dashboard)/
      components/
        AdminTab/
          index.tsx                    # Главный компонент
          UserManagement.tsx            # Управление пользователями
          UserSettingsEditor.tsx        # Редактор настроек пользователя
          ErrorLogsPanel.tsx            # Панель логов ошибок
          ExchangeSettingsEditor.tsx    # Редактор настроек бирж
          hooks/
            useAdminUsers.ts            # Хук для работы с пользователями
            useErrorLogs.ts             # Хук для работы с логами
          utils/
            validators.ts               # Валидация
            userStatus.ts               # Логика статусов пользователей
          types.ts                      # Типы
        SettingsTab/
          index.tsx                     # Главный компонент
          SettingsNavigation.tsx        # Навигация по подтемам
          TelegramSettings.tsx           # Настройки Telegram
          MessageFormatSettings.tsx     # Формат сообщений
          SpikesSettings.tsx            # Настройки прострелов
          BlacklistSettings.tsx         # Чёрный список
          StrategiesSettings.tsx         # Условные шаблоны
          components/
            ExchangeFilter.tsx          # Фильтр биржи
            PairSettingsEditor.tsx      # Редактор настроек пары
            StrategyEditor.tsx          # Редактор стратегии
            ConditionEditor.tsx        # Редактор условия
            MessageTemplateEditor.tsx   # Редактор шаблона сообщения
            # EmojiPickerButton.tsx - УДАЛЕНО: кнопка уже удалена
          hooks/
            useSettings.ts              # Хук для загрузки/сохранения настроек
            useTelegramSettings.ts     # Хук для настроек Telegram
            useMessageTemplate.ts       # Хук для работы с шаблонами
            useStrategies.ts            # Хук для условных шаблонов
          utils/
            validators.ts               # Валидация
            formatters.ts               # Форматирование
            templateUtils.ts            # Утилиты для шаблонов
            placeholderMap.ts           # Маппинг плейсхолдеров
          types.ts                      # Типы
        # Остальные компоненты остаются без изменений:
        DashboardShell.tsx
        StatisticsTab.tsx
        MonitoringTab.tsx
        MetricsAdminTab.tsx
  components/
    ChatIdHelp.tsx                      # Остаётся без изменений
```

---

## Важные замечания

⚠️ **Внимание**: При рефакторинге SettingsTab.tsx будьте особенно осторожны с:
- Логикой условных шаблонов (очень сложная)
- Редактором шаблонов с contentEditable
- Валидацией условий стратегий

**Примечание**: Код EmojiPicker (импорт, состояние, refs, функция insertEmoji, рендер) можно удалить при рефакторинге, так как кнопка для его открытия уже удалена из проекта.

✅ **Преимущества после рефакторинга**:
- Легче поддерживать код
- Легче тестировать отдельные части
- Можно переиспользовать компоненты
- Улучшается читаемость
- Упрощается отладка
