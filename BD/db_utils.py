"""
Утилиты для работы с базой данных
"""
import aiosqlite
from typing import AsyncContextManager
from contextlib import asynccontextmanager
from core.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def db_connection(db_path: str) -> AsyncContextManager[aiosqlite.Connection]:
    """
    Асинхронный контекстный менеджер для работы с подключением к БД.
    Автоматически создаёт подключение, настраивает его и закрывает после использования.
    
    Args:
        db_path: Путь к файлу БД
        
    Yields:
        aiosqlite.Connection: Подключение к БД
        
    Example:
        async with db_connection(str(db_path)) as conn:
            await conn.execute("SELECT * FROM users")
            await conn.commit()
    """
    conn = None
    try:
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        # Убеждаемся, что SQLite использует UTF-8 для работы с кириллицей
        await conn.execute("PRAGMA encoding = 'UTF-8'")
        # Включаем WAL режим для лучшей конкурентности
        await conn.execute("PRAGMA journal_mode = WAL")
        yield conn
    finally:
        if conn:
            await conn.close()









