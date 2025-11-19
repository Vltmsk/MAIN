# Инструкция по синхронизации и пересборке

## Проблема
На сервере все еще старая версия файла `DashboardShell.tsx` с ошибкой TypeScript.

## Решение

### Вариант 1: Использовать скрипт (рекомендуется)

На сервере выполните:
```powershell
cd C:\onlyWS
.\fix_build.ps1
```

Скрипт автоматически:
- Проверит, что файл обновлен
- Очистит кэш Next.js
- Пересоберет проект

### Вариант 2: Ручная синхронизация

1. **Убедитесь, что изменения закоммичены локально:**
   ```powershell
   cd C:\onlyWS
   git status
   git add .
   git commit -m "Fix TypeScript types for sendChart property"
   ```

2. **На сервере синхронизируйте изменения:**
   ```powershell
   cd C:\onlyWS
   git pull origin main
   # Или если есть конфликты:
   git stash
   git pull origin main
   git stash pop
   ```

3. **Очистите кэш и пересоберите:**
   ```powershell
   cd C:\onlyWS\WEB
   Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
   npm run build
   ```

4. **Если сборка успешна, перезапустите службу:**
   ```powershell
   Restart-Service CryptoSpikesWeb
   ```

## Проверка, что файл обновлен

Проверьте строку 1505 в файле `WEB\app\(dashboard)\components\DashboardShell.tsx`:

**Старый код (неправильный):**
```typescript
pairSettingsWithCharts[key] = {
  ...pairSettings[key],
  sendChart: chartSettings[key]
};
```

**Новый код (правильный):**
```typescript
const currentSettings = pairSettings[key];
const newSettings: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean } = {
  enabled: currentSettings.enabled,
  delta: currentSettings.delta,
  volume: currentSettings.volume,
  shadow: currentSettings.shadow,
  sendChart: chartSettings[key]
};
pairSettingsWithCharts[key] = newSettings;
```

Если вы видите старый код, значит файл не обновлен на сервере.

## Если проблема сохраняется

1. Убедитесь, что файл действительно обновлен на сервере
2. Очистите все кэши:
   ```powershell
   cd C:\onlyWS\WEB
   Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
   Remove-Item -Recurse -Force node_modules\.cache -ErrorAction SilentlyContinue
   npm run build
   ```
3. Проверьте версию TypeScript:
   ```powershell
   npm list typescript
   ```

