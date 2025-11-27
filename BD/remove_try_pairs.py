"""
Скрипт для удаления всех записей с торговыми парами TRY для Binance Spot
"""
import asyncio
import json
from pathlib import Path
from database import Database

async def remove_try_pairs():
    """
    Удаляет все записи с торговыми парами TRY для Binance Spot:
    1. Удаляет записи из таблицы alerts с символами, заканчивающимися на TRY
    2. Удаляет настройки пользователей (pairSettings) с TRY парами для Binance Spot
    3. Удаляет записи из user_alerts, связанные с удаленными alerts
    """
    db = Database()
    await db.initialize()
    
    conn = await db._get_connection()
    try:
        # 1. Находим все alerts с символами, заканчивающимися на TRY для Binance Spot
        print("Поиск записей с TRY парами для Binance Spot...")
        async with conn.execute("""
            SELECT id, symbol, exchange, market 
            FROM alerts 
            WHERE exchange = 'binance' 
            AND market = 'spot' 
            AND (symbol LIKE '%TRY' OR normalized_symbol LIKE '%TRY')
        """) as cursor:
            alerts = await cursor.fetchall()
            print(f"Найдено {len(alerts)} записей в alerts")
            
            if alerts:
                alert_ids = [row[0] for row in alerts]
                symbols = set([row[1] for row in alerts])
                print(f"Уникальные символы: {', '.join(sorted(symbols))}")
                
                # Удаляем связанные записи из user_alerts
                print("Удаление связанных записей из user_alerts...")
                cursor = await conn.execute("""
                    DELETE FROM user_alerts 
                    WHERE alert_id IN ({})
                """.format(','.join('?' * len(alert_ids))), alert_ids)
                deleted_user_alerts = cursor.rowcount
                print(f"Удалено {deleted_user_alerts} записей из user_alerts")
                
                # Удаляем alerts
                print("Удаление записей из alerts...")
                cursor = await conn.execute("""
                    DELETE FROM alerts 
                    WHERE id IN ({})
                """.format(','.join('?' * len(alert_ids))), alert_ids)
                deleted_alerts = cursor.rowcount
                print(f"Удалено {deleted_alerts} записей из alerts")
        
        # 2. Обновляем настройки пользователей - удаляем TRY пары из pairSettings
        print("\nОбновление настроек пользователей...")
        async with conn.execute("SELECT id, user, options_json FROM users") as cursor:
            users = await cursor.fetchall()
            updated_users = 0
            
            for user_row in users:
                user_id = user_row[0]
                username = user_row[1]
                options_json = user_row[2] or "{}"
                
                try:
                    options = json.loads(options_json)
                    pair_settings = options.get("pairSettings", {})
                    
                    # Ищем и удаляем пары с TRY для Binance Spot
                    keys_to_remove = []
                    for key in pair_settings.keys():
                        if key.startswith("binance_spot_") and key.endswith("_TRY"):
                            keys_to_remove.append(key)
                        # Также проверяем пары вида binance_spot_TRY
                        if key == "binance_spot_TRY":
                            keys_to_remove.append(key)
                    
                    if keys_to_remove:
                        for key in keys_to_remove:
                            del pair_settings[key]
                            print(f"  Удалена пара {key} для пользователя {username}")
                        
                        options["pairSettings"] = pair_settings
                        new_options_json = json.dumps(options, ensure_ascii=False)
                        
                        await conn.execute("""
                            UPDATE users 
                            SET options_json = ?, updated_at = CURRENT_TIMESTAMP 
                            WHERE id = ?
                        """, (new_options_json, user_id))
                        updated_users += 1
                except json.JSONDecodeError:
                    print(f"  Ошибка парсинга JSON для пользователя {username}, пропускаем")
                    continue
            
            print(f"Обновлено {updated_users} пользователей")
        
        # 3. Удаляем записи из exchange_blacklists с TRY для Binance Spot
        print("\nУдаление записей из exchange_blacklists...")
        cursor = await conn.execute("""
            DELETE FROM exchange_blacklists 
            WHERE exchange = 'binance' 
            AND market = 'spot' 
            AND (symbol LIKE '%TRY' OR symbol = 'TRY')
        """)
        deleted_blacklist = cursor.rowcount
        print(f"Удалено {deleted_blacklist} записей из exchange_blacklists")
        
        # 4. Удаляем записи из symbol_aliases с TRY для Binance Spot
        print("\nУдаление записей из symbol_aliases...")
        cursor = await conn.execute("""
            DELETE FROM symbol_aliases 
            WHERE exchange = 'binance' 
            AND market = 'spot' 
            AND (original_symbol LIKE '%TRY' OR alias LIKE '%TRY' OR original_symbol = 'TRY' OR alias = 'TRY')
        """)
        deleted_aliases = cursor.rowcount
        print(f"Удалено {deleted_aliases} записей из symbol_aliases")
        
        await conn.commit()
        print("\n✅ Очистка завершена успешно!")
        
    except Exception as e:
        await conn.rollback()
        print(f"\n❌ Ошибка при очистке: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Удаление торговых пар TRY для Binance Spot")
    print("=" * 60)
    print()
    
    asyncio.run(remove_try_pairs())

