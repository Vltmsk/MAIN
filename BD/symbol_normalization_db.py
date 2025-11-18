"""
Модуль для работы с базой данных нормализации символов
Отдельная БД для быстрого доступа к нормализованным символам
"""
import aiosqlite
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from core.logger import get_logger

logger = get_logger(__name__)

# Путь к базе данных нормализации
DB_PATH = Path(__file__).parent / "symbol_normalization.db"


class SymbolNormalizationDB:
    """Класс для работы с БД нормализации символов"""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Инициализация подключения к БД
        
        Args:
            db_path: Путь к файлу БД (по умолчанию symbol_normalization.db в папке BD)
        """
        self.db_path = db_path or DB_PATH
        self._ensure_db_directory()
        self._initialized = False
    
    def _ensure_db_directory(self):
        """Создаёт директорию для БД, если её нет"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self):
        """Явная инициализация БД (создание таблиц)"""
        if not self._initialized:
            await self._init_database()
            self._initialized = True
    
    async def _get_connection(self) -> aiosqlite.Connection:
        """
        Создаёт новое асинхронное подключение к БД
        
        Returns:
            aiosqlite.Connection: Асинхронное подключение к БД
        """
        # Инициализируем БД при первом подключении, если ещё не инициализирована
        if not self._initialized:
            await self.initialize()
        
        conn = await aiosqlite.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA encoding = 'UTF-8'")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA busy_timeout = 30000")
        await conn.execute("PRAGMA synchronous = NORMAL")
        return conn
    
    async def _init_database(self):
        """Инициализирует БД: создаёт все таблицы, если их нет"""
        conn = await aiosqlite.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA encoding = 'UTF-8'")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA busy_timeout = 30000")
        await conn.execute("PRAGMA synchronous = NORMAL")
        try:
            # Таблица нормализации символов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS symbol_normalization (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    market TEXT NOT NULL,
                    original_symbol TEXT NOT NULL,
                    normalized_symbol TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(exchange, market, original_symbol)
                )
            """)
            
            # Индексы для быстрого поиска
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_lookup 
                ON symbol_normalization(exchange, market, original_symbol)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_normalized_lookup 
                ON symbol_normalization(normalized_symbol)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_exchange_market_normalized 
                ON symbol_normalization(exchange, market, normalized_symbol)
            """)
            
            await conn.commit()
            logger.info(f"База данных нормализации символов инициализирована: {self.db_path}")
            
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при инициализации нормализации: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при инициализации нормализации: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def get_normalized_symbol(
        self, 
        exchange: str, 
        market: str, 
        original_symbol: str
    ) -> Optional[str]:
        """
        Получает нормализованный символ из БД
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            original_symbol: Оригинальный символ
            
        Returns:
            Нормализованный символ или None если не найден
        """
        conn = await self._get_connection()
        try:
            async with conn.execute("""
                SELECT normalized_symbol FROM symbol_normalization
                WHERE exchange = ? AND market = ? AND original_symbol = ?
            """, (exchange, market, original_symbol)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении нормализованного символа: {e}", exc_info=True)
            return None
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении нормализованного символа: {e}", exc_info=True)
            return None
        finally:
            await conn.close()
    
    async def save_normalized_symbol(
        self,
        exchange: str,
        market: str,
        original_symbol: str,
        normalized_symbol: str
    ):
        """
        Сохраняет нормализованный символ в БД (асинхронно, не блокирует)
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            original_symbol: Оригинальный символ
            normalized_symbol: Нормализованный символ
        """
        conn = await self._get_connection()
        try:
            await conn.execute("""
                INSERT OR REPLACE INTO symbol_normalization
                (exchange, market, original_symbol, normalized_symbol, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (exchange, market, original_symbol, normalized_symbol))
            await conn.commit()
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.warning(f"Ошибка БД при сохранении нормализованного символа: {e}")
            await conn.rollback()
        except aiosqlite.Error as e:
            logger.warning(f"Ошибка БД при сохранении нормализованного символа: {e}")
            await conn.rollback()
        finally:
            await conn.close()
    
    async def get_denormalized_symbols(
        self,
        normalized_symbol: str,
        exchange: Optional[str] = None,
        market: Optional[str] = None
    ) -> List[str]:
        """
        Получает все варианты символов для нормализованного символа
        
        Args:
            normalized_symbol: Нормализованный символ
            exchange: Фильтр по бирже (опционально)
            market: Фильтр по рынку (опционально)
            
        Returns:
            Список оригинальных символов
        """
        conn = await self._get_connection()
        try:
            conditions = ["normalized_symbol = ?"]
            params = [normalized_symbol]
            
            if exchange:
                conditions.append("exchange = ?")
                params.append(exchange)
            if market:
                conditions.append("market = ?")
                params.append(market)
            
            where_clause = "WHERE " + " AND ".join(conditions)
            
            async with conn.execute(f"""
                SELECT original_symbol FROM symbol_normalization
                {where_clause}
            """, params) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении денормализованных символов: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении денормализованных символов: {e}", exc_info=True)
            return []
        finally:
            await conn.close()
    
    async def get_all_symbols(
        self,
        exchange: Optional[str] = None,
        market: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получает все символы из БД
        
        Args:
            exchange: Фильтр по бирже (опционально)
            market: Фильтр по рынку (опционально)
            
        Returns:
            Список словарей с полями exchange, market, original_symbol, normalized_symbol
        """
        conn = await self._get_connection()
        try:
            conditions = []
            params = []
            
            if exchange:
                conditions.append("exchange = ?")
                params.append(exchange)
            if market:
                conditions.append("market = ?")
                params.append(market)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            async with conn.execute(f"""
                SELECT exchange, market, original_symbol, normalized_symbol
                FROM symbol_normalization
                {where_clause}
                ORDER BY exchange, market, original_symbol
            """, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении всех символов: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении всех символов: {e}", exc_info=True)
            return []
        finally:
            await conn.close()
    
    async def clear_all(self):
        """Очищает всю БД нормализации (для тестирования или перезаполнения)"""
        conn = await self._get_connection()
        try:
            await conn.execute("DELETE FROM symbol_normalization")
            await conn.commit()
            logger.info("База данных нормализации символов очищена")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при очистке: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при очистке: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()


# Глобальный экземпляр БД для использования в приложении
symbol_normalization_db = SymbolNormalizationDB()

