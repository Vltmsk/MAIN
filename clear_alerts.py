"""
Скрипт для полной очистки таблиц alerts и user_alerts из базы данных
"""
import asyncio
import sys
from pathlib import Path
from BD.database import Database, DB_PATH


async def clear_all_alerts():
    """
    Удаляет все записи из таблиц alerts и user_alerts
    """
    db = Database()
    
    # Подключаемся к БД
    conn = await db._get_connection()
    
    try:
        # Получаем количество записей перед удалением
        async with conn.execute("SELECT COUNT(*) FROM user_alerts") as cursor:
            user_alerts_count = (await cursor.fetchone())[0]
        
        async with conn.execute("SELECT COUNT(*) FROM alerts") as cursor:
            alerts_count = (await cursor.fetchone())[0]
        
        print(f"Найдено записей:")
        print(f"  - user_alerts: {user_alerts_count}")
        print(f"  - alerts: {alerts_count}")
        
        if user_alerts_count == 0 and alerts_count == 0:
            print("\nБаза данных уже пуста. Нечего удалять.")
            return
        
        # Запрашиваем подтверждение
        print(f"\n⚠️  ВНИМАНИЕ: Будет удалено {user_alerts_count} связей и {alerts_count} стрел!")
        confirmation = input("Введите 'YES' для подтверждения: ")
        
        if confirmation != 'YES':
            print("Операция отменена.")
            return
        
        # Удаляем все связи из user_alerts
        print("\nУдаление связей из user_alerts...")
        cursor1 = await conn.execute("DELETE FROM user_alerts")
        deleted_user_alerts = cursor1.rowcount
        
        # Удаляем все стрелы из alerts
        print("Удаление стрел из alerts...")
        cursor2 = await conn.execute("DELETE FROM alerts")
        deleted_alerts = cursor2.rowcount
        
        # Сохраняем изменения
        await conn.commit()
        
        print(f"\n✅ Успешно удалено:")
        print(f"  - {deleted_user_alerts} связей из user_alerts")
        print(f"  - {deleted_alerts} стрел из alerts")
        
    except Exception as e:
        await conn.rollback()
        print(f"\n❌ Ошибка при удалении: {e}")
        raise
    finally:
        await conn.close()


async def main():
    """Главная функция"""
    print("=" * 60)
    print("Очистка таблиц alerts и user_alerts")
    print("=" * 60)
    print(f"База данных: {DB_PATH}")
    print()
    
    # Проверяем существование БД
    if not DB_PATH.exists():
        print(f"❌ База данных не найдена: {DB_PATH}")
        sys.exit(1)
    
    try:
        await clear_all_alerts()
    except KeyboardInterrupt:
        print("\n\nОперация прервана пользователем.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

