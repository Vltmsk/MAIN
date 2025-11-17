"""
Модуль для работы с базой данных SQLite (асинхронная версия с aiosqlite)
"""
import sqlite3
import aiosqlite
import asyncio
import os
import hashlib
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from core.logger import get_logger

logger = get_logger(__name__)

# Путь к базе данных
DB_PATH = Path(__file__).parent / "detected_alerts.db"


class Database:
    """Класс для работы с базой данных SQLite (асинхронная версия)"""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Инициализация подключения к БД
        
        Args:
            db_path: Путь к файлу БД (по умолчанию detected_alerts.db в папке BD)
        """
        self.db_path = db_path or DB_PATH
        self._ensure_db_directory()
        self._initialized = False
        # Инициализация БД будет выполнена при первом вызове async метода
        # или можно вызвать await db.initialize() явно
    
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
        
        conn = await aiosqlite.connect(str(self.db_path))
        conn.row_factory = aiosqlite.Row  # Для доступа к колонкам по имени
        # Убеждаемся, что SQLite использует UTF-8 для работы с кириллицей
        await conn.execute("PRAGMA encoding = 'UTF-8'")
        # Включаем WAL режим для лучшей конкурентности
        await conn.execute("PRAGMA journal_mode = WAL")
        return conn
    
    async def _init_database(self):
        """Инициализирует БД: создаёт все таблицы, если их нет"""
        # Создаём подключение напрямую, без проверки инициализации
        conn = await aiosqlite.connect(str(self.db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA encoding = 'UTF-8'")
        await conn.execute("PRAGMA journal_mode = WAL")
        try:
            
            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user TEXT UNIQUE NOT NULL,
                    password_hash TEXT DEFAULT NULL,
                    tg_token TEXT DEFAULT '',
                    chat_id TEXT DEFAULT '',
                    options_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            
            # Миграция: добавляем поле password_hash если его нет
            try:
                await conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT NULL")
                logger.info("Добавлено поле password_hash в таблицу users")
            except aiosqlite.OperationalError:
                # Колонка уже существует, это нормально
                pass
            
            # Миграция: удаляем таблицу registration_whitelist (больше не используется)
            try:
                async with conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registration_whitelist'") as cursor:
                    table_exists = await cursor.fetchone()
                    if table_exists:
                        await conn.execute("DROP TABLE registration_whitelist")
                        logger.info("Удалена таблица registration_whitelist (больше не используется)")
            except aiosqlite.OperationalError as e:
                logger.warning(f"Ошибка при удалении таблицы registration_whitelist: {e}")
                # Продолжаем работу, это не критично
            
            # Таблица стрел (alerts) - уникальные стрелы без user_id
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    exchange TEXT NOT NULL,
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    delta REAL NOT NULL,
                    wick_pct REAL NOT NULL,
                    volume_usdt REAL NOT NULL,
                    meta TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ts, exchange, market, symbol, delta, wick_pct, volume_usdt)
                )
            """)
            
            # Таблица связи пользователей со стрелами (user_alerts)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(alert_id, user_id)
                )
            """)
            
            # Миграция: проверяем, есть ли старые данные с user_id в alerts
            try:
                async with conn.execute("PRAGMA table_info(alerts)") as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]
                    has_user_id_column = 'user_id' in columns
                    
                    if has_user_id_column:
                        # Выполняем миграцию данных
                        logger.info("Начинаем миграцию данных: разделение alerts и user_alerts")
                        
                        # Создаём временную таблицу для старых данных
                        await conn.execute("""
                            CREATE TABLE IF NOT EXISTS alerts_old_backup AS
                            SELECT * FROM alerts WHERE 1=0
                        """)
                        
                        # Копируем старые данные
                        await conn.execute("""
                            INSERT INTO alerts_old_backup
                            SELECT * FROM alerts
                        """)
                        
                        # Создаём новую таблицу без user_id
                        await conn.execute("""
                            CREATE TABLE alerts_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                ts INTEGER NOT NULL,
                                exchange TEXT NOT NULL,
                                market TEXT NOT NULL,
                                symbol TEXT NOT NULL,
                                delta REAL NOT NULL,
                                wick_pct REAL NOT NULL,
                                volume_usdt REAL NOT NULL,
                                meta TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(ts, exchange, market, symbol, delta, wick_pct, volume_usdt)
                            )
                        """)
                        
                        # Получаем все уникальные стрелы из старых данных и вставляем в новую таблицу
                        await conn.execute("""
                            INSERT OR IGNORE INTO alerts_new 
                            (id, ts, exchange, market, symbol, delta, wick_pct, volume_usdt, meta, created_at)
                            SELECT DISTINCT 
                                id, ts, exchange, market, symbol, delta, wick_pct, volume_usdt, meta, created_at
                            FROM alerts_old_backup
                            WHERE user_id IS NOT NULL
                        """)
                        
                        # Удаляем старую таблицу и переименовываем новую
                        await conn.execute("DROP TABLE alerts")
                        await conn.execute("ALTER TABLE alerts_new RENAME TO alerts")
                        
                        # Создаём связи в user_alerts
                        await conn.execute("""
                            INSERT OR IGNORE INTO user_alerts (alert_id, user_id, created_at)
                            SELECT 
                                a.id AS alert_id,
                                a_old.user_id,
                                a_old.created_at
                            FROM alerts_old_backup a_old
                            INNER JOIN alerts a ON 
                                a.ts = a_old.ts AND
                                a.exchange = a_old.exchange AND
                                a.market = a_old.market AND
                                a.symbol = a_old.symbol AND
                                a.delta = a_old.delta AND
                                a.wick_pct = a_old.wick_pct AND
                                a.volume_usdt = a_old.volume_usdt
                            WHERE a_old.user_id IS NOT NULL
                        """)
                        
                        # Удаляем временную таблицу
                        await conn.execute("DROP TABLE IF EXISTS alerts_old_backup")
                        
                        logger.info("Миграция данных завершена успешно")
            except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
                logger.warning(f"Ошибка при миграции данных (возможно, миграция уже выполнена): {e}")
                # Продолжаем работу - возможно, миграция уже была выполнена
            except aiosqlite.Error as e:
                logger.error(f"Ошибка БД при миграции данных: {e}", exc_info=True)
                # Продолжаем работу - возможно, миграция уже была выполнена
            
            # Таблица ошибок
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exchange TEXT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    connection_id TEXT,
                    market TEXT,
                    symbol TEXT,
                    stack_trace TEXT
                )
            """)
            
            # Таблица настроек бирж - чёрные списки символов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS exchange_blacklists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(exchange, market, symbol)
                )
            """)
            
            # Таблица алиасов символов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS symbol_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    market TEXT NOT NULL,
                    original_symbol TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(exchange, market, original_symbol, alias)
                )
            """)
            
            # Таблица статистики бирж и рынков
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS exchange_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    market TEXT NOT NULL,
                    symbols_count INTEGER NOT NULL DEFAULT 0,
                    ws_connections INTEGER NOT NULL DEFAULT 0,
                    batches_per_ws INTEGER DEFAULT NULL,
                    reconnects INTEGER NOT NULL DEFAULT 0,
                    candles_count INTEGER NOT NULL DEFAULT 0,
                    last_candle_time TIMESTAMP,
                    ticks_per_second REAL DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(exchange, market)
                )
            """)
            
            # Создаём индексы через отдельные команды (для совместимости)
            # SQLite не поддерживает INDEX в CREATE TABLE напрямую, создаём отдельно

            indexes = [
                # Индексы для alerts - оптимизация частых запросов
                "CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts)",
                "CREATE INDEX IF NOT EXISTS idx_alerts_exchange ON alerts(exchange)",
                "CREATE INDEX IF NOT EXISTS idx_alerts_market ON alerts(market)",
                "CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_alerts_exchange_market ON alerts(exchange, market)",
                # Составной индекс для запросов статистики по времени и бирже
                "CREATE INDEX IF NOT EXISTS idx_alerts_ts_exchange_market ON alerts(ts, exchange, market)",
                # Индексы для user_alerts
                "CREATE INDEX IF NOT EXISTS idx_user_alerts_alert_id ON user_alerts(alert_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_alerts_user_id ON user_alerts(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_alerts_alert_user ON user_alerts(alert_id, user_id)",
                # Индекс для быстрого поиска пользователей по имени
                "CREATE INDEX IF NOT EXISTS idx_users_user ON users(user)",
                # Индексы для errors
                "CREATE INDEX IF NOT EXISTS idx_errors_timestamp ON errors(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_errors_exchange ON errors(exchange)",
                "CREATE INDEX IF NOT EXISTS idx_errors_error_type ON errors(error_type)",
                # Составной индекс для фильтрации ошибок по времени и бирже
                "CREATE INDEX IF NOT EXISTS idx_errors_timestamp_exchange ON errors(timestamp, exchange)",
                # Индексы для exchange_statistics
                "CREATE INDEX IF NOT EXISTS idx_exchange_statistics_exchange ON exchange_statistics(exchange)",
                "CREATE INDEX IF NOT EXISTS idx_exchange_statistics_market ON exchange_statistics(market)",
                "CREATE INDEX IF NOT EXISTS idx_exchange_statistics_exchange_market ON exchange_statistics(exchange, market)",
                # Индексы для exchange_blacklists - для быстрой проверки
                "CREATE INDEX IF NOT EXISTS idx_exchange_blacklists_exchange_market_symbol ON exchange_blacklists(exchange, market, symbol)",
                # Индексы для symbol_aliases
                "CREATE INDEX IF NOT EXISTS idx_symbol_aliases_exchange_market_symbol ON symbol_aliases(exchange, market, original_symbol)",
            ]
            
            for index_sql in indexes:
                await conn.execute(index_sql)
            
            await conn.commit()
            logger.info(f"База данных инициализирована: {self.db_path}")
            
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при инициализации: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при инициализации: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    # ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """Хеширует пароль используя SHA-256"""
        return hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        """Проверяет пароль против хеша"""
        return Database._hash_password(password) == password_hash
    
    async def register_user(self, user: str, password: str, tg_token: str = "", 
                     chat_id: str = "", options_json: str = "{}") -> int:
        """
        Регистрирует нового пользователя (асинхронная версия)
        
        Args:
            user: Имя пользователя (уникальное)
            password: Пароль пользователя
            tg_token: Telegram токен
            chat_id: Telegram Chat ID
            options_json: JSON строка с настройками (thresholds, exchanges)
            
        Returns:
            int: ID созданного пользователя
            
        Raises:
            ValueError: Если пользователь не существует или уже зарегистрирован
        """
        normalized_user = self._normalize_username(user)
        if not normalized_user:
            raise ValueError("Имя пользователя не может быть пустым")

        conn = await self._get_connection()
        try:
            # Проверяем, существует ли пользователь в базе (должен быть создан администратором)
            async with conn.execute("SELECT id, user FROM users WHERE LOWER(user) = LOWER(?)", (normalized_user,)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    existing_username = existing[1] if len(existing) > 1 else user
                    # Проверяем, есть ли уже пароль (т.е. уже зарегистрирован)
                    user_id = existing[0] if isinstance(existing, aiosqlite.Row) else existing[0]
                    async with conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)) as cursor2:
                        password_row = await cursor2.fetchone()
                        if password_row and password_row[0]:
                            raise ValueError(f"Пользователь с логином '{existing_username}' уже зарегистрирован. Используйте страницу входа.")
                else:
                    raise ValueError("Регистрация для этого логина не разрешена. Обратитесь к администратору.")

            # Дополнительная проверка точного совпадения (на случай если регистр отличается)
            async with conn.execute("SELECT id, user FROM users WHERE user = ?", (normalized_user,)) as cursor:
                exact_match = await cursor.fetchone()
                if exact_match:
                    # Используем точное имя из базы
                    exact_username = exact_match[1] if isinstance(exact_match, aiosqlite.Row) else exact_match[1]
                    normalized_user = exact_username
                else:
                    # Если нет точного совпадения, используем первый найденный (с другим регистром)
                    normalized_user = existing_username
            
            # Хешируем пароль
            password_hash = self._hash_password(password)
            
            # Обновляем пароль и настройки для существующего пользователя
            await conn.execute("""
                UPDATE users 
                SET password_hash = ?, tg_token = ?, chat_id = ?, options_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(user) = LOWER(?)
            """, (password_hash, tg_token, chat_id, options_json, normalized_user))
            await conn.commit()
            
            # Получаем ID обновлённого пользователя
            async with conn.execute("SELECT id FROM users WHERE LOWER(user) = LOWER(?)", (normalized_user,)) as cursor:
                row = await cursor.fetchone()
                user_id = row[0] if row else None
            
            logger.info(f"Зарегистрирован новый пользователь {normalized_user} (ID: {user_id})")
            return user_id
        except ValueError:
            # Пробрасываем ValueError как есть
            raise
        except aiosqlite.IntegrityError as e:
            await conn.rollback()
            logger.warning(f"Ошибка при регистрации пользователя {normalized_user}: {e}")
            raise ValueError(f"Пользователь '{normalized_user}' уже зарегистрирован")
        except aiosqlite.OperationalError as e:
            logger.error(f"Ошибка БД при регистрации пользователя {normalized_user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при регистрации пользователя {normalized_user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def authenticate_user(self, user: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Проверяет аутентификацию пользователя (асинхронная версия)
        
        ВАЖНО: Эта функция ТОЛЬКО читает данные из базы, НЕ обновляет их.
        При входе пользователя его настройки (tg_token, chat_id, options_json) 
        остаются неизменными.
        
        Args:
            user: Имя пользователя
            password: Пароль пользователя
            
        Returns:
            Dict с данными пользователя или None если неверный логин/пароль
        """
        normalized_user = self._normalize_username(user)
        if not normalized_user:
            return None

        conn = await self._get_connection()
        try:
            # ТОЛЬКО SELECT - никаких UPDATE или INSERT
            # Ищем пользователя без учёта регистра
            async with conn.execute("SELECT * FROM users WHERE LOWER(user) = LOWER(?)", (normalized_user,)) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    logger.warning(f"Попытка входа: пользователь '{normalized_user}' не найден")
                    return None
                
                user_data = dict(row)
                password_hash = user_data.get('password_hash')
                
                # Пароль обязателен для всех пользователей - проверяем его строго
                if not password_hash:
                    logger.warning(f"Пользователь '{user_data.get('user')}' не имеет пароля - доступ запрещён. Необходимо зарегистрироваться или установить пароль.")
                    return None
                
                # Проверяем пароль
                if not self._verify_password(password, password_hash):
                    logger.warning(f"Неверный пароль для пользователя '{user_data.get('user')}' - доступ запрещён")
                    return None
                
                logger.info(f"Успешная аутентификация пользователя '{user_data.get('user')}' (пароль верный, данные НЕ обновляются)")
                return user_data
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при аутентификации пользователя {normalized_user}: {e}", exc_info=True)
            return None
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при аутентификации пользователя {normalized_user}: {e}", exc_info=True)
            return None
        finally:
            await conn.close()
    
    async def create_user(self, user: str, tg_token: str = "", chat_id: str = "", 
                   options_json: str = "{}") -> int:
        """
        Создаёт нового пользователя или обновляет существующего (БЕЗ перезаписи пароля)
        ВНИМАНИЕ: Используйте register_user() для регистрации новых пользователей с паролем
        
        Args:
            user: Имя пользователя (уникальное)
            tg_token: Telegram токен
            chat_id: Telegram Chat ID
            options_json: JSON строка с настройками (thresholds, exchanges)
            
        Returns:
            int: ID созданного пользователя
        """
        normalized_user = self._normalize_username(user)
        if not normalized_user:
            raise ValueError("Имя пользователя не может быть пустым")

        conn = await self._get_connection()
        try:
            # Проверяем, существует ли пользователь (без учета регистра)
            async with conn.execute("""
                SELECT id, user, password_hash 
                FROM users 
                WHERE LOWER(user) = LOWER(?)
            """, (normalized_user,)) as cursor:
                existing_user = await cursor.fetchone()
            
            if existing_user:
                stored_username = existing_user["user"] if isinstance(existing_user, aiosqlite.Row) else existing_user[1]
                user_id = existing_user["id"] if isinstance(existing_user, aiosqlite.Row) else existing_user[0]

                # Обновляем существующего пользователя (БЕЗ изменения пароля)
                if stored_username != normalized_user:
                    await conn.execute("""
                        UPDATE users 
                        SET user = ?, tg_token = ?, chat_id = ?, options_json = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (normalized_user, tg_token, chat_id, options_json, user_id))
                else:
                    await conn.execute("""
                        UPDATE users 
                        SET tg_token = ?, chat_id = ?, options_json = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (tg_token, chat_id, options_json, user_id))
                await conn.commit()
                logger.debug(f"Обновлён пользователь {normalized_user} (ID: {user_id}) - пароль не изменён")
            else:
                # Создаём нового пользователя БЕЗ пароля (для обратной совместимости)
                cursor = await conn.execute("""
                    INSERT INTO users (user, tg_token, chat_id, options_json, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (normalized_user, tg_token, chat_id, options_json))
                await conn.commit()
                user_id = cursor.lastrowid
                logger.debug(f"Создан пользователь {normalized_user} (ID: {user_id}) без пароля")
            
            return user_id
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при создании пользователя {normalized_user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при создании пользователя {normalized_user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def get_user(self, user: str) -> Optional[Dict[str, Any]]:
        """
        Получает пользователя по имени
        
        Args:
            user: Имя пользователя
            
        Returns:
            Dict с данными пользователя или None
        """
        conn = await self._get_connection()
        try:
            # Логируем для отладки
            logger.debug(f"[Database] get_user called with: '{user}' (type: {type(user)}, length: {len(user)})")
            logger.debug(f"[Database] User bytes: {user.encode('utf-8')}")
            
            # Получаем всех пользователей для сравнения
            async with conn.execute("SELECT user FROM users") as cursor:
                all_users = [row[0] for row in await cursor.fetchall()]
            logger.debug(f"[Database] All users in DB: {all_users}")
            
            # Выполняем поиск сначала точный, затем без учета регистра
            async with conn.execute("SELECT * FROM users WHERE user = ?", (user,)) as cursor:
                row = await cursor.fetchone()
            
            if row:
                user_dict = dict(row)
                logger.debug(f"[Database] User found: '{user_dict['user']}' (id: {user_dict.get('id')})")
                return user_dict
            else:
                # Попробуем найти без учета регистра
                async with conn.execute("SELECT * FROM users WHERE LOWER(user) = LOWER(?)", (user,)) as cursor:
                    row_case_insensitive = await cursor.fetchone()
                if row_case_insensitive:
                    found_user = dict(row_case_insensitive)
                    logger.warning(f"[Database] Found user with different case: '{found_user['user']}' (requested: '{user}')")
                    return found_user
                else:
                    logger.warning(f"[Database] User '{user}' not found. Available users: {all_users}")
                    return None
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении пользователя {user}: {e}", exc_info=True)
            return None
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении пользователя {user}: {e}", exc_info=True)
            return None
        finally:
            await conn.close()
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает пользователя по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict с данными пользователя или None
        """
        conn = await self._get_connection()
        try:
            async with conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
            return dict(row) if row else None
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении пользователя по ID {user_id}: {e}", exc_info=True)
            return None
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении пользователя по ID {user_id}: {e}", exc_info=True)
            return None
        finally:
            await conn.close()
    
    async def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Получает всех пользователей
        
        Returns:
            List[Dict]: Список всех пользователей
        """
        conn = await self._get_connection()
        try:
            async with conn.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении всех пользователей: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении всех пользователей: {e}", exc_info=True)
            return []
        finally:
            await conn.close()
    
    async def update_user_password(self, user: str, password: str) -> bool:
        """
        Устанавливает или обновляет пароль для существующего пользователя
        
        Args:
            user: Имя пользователя
            password: Новый пароль
            
        Returns:
            bool: True если пароль успешно установлен, False если пользователь не найден
        """
        conn = await self._get_connection()
        try:
            # Проверяем, существует ли пользователь
            async with conn.execute("SELECT id FROM users WHERE user = ?", (user,)) as cursor:
                if not await cursor.fetchone():
                    logger.warning(f"Попытка установить пароль для несуществующего пользователя '{user}'")
                    return False
            
            # Хешируем пароль
            password_hash = self._hash_password(password)
            
            # Обновляем пароль
            await conn.execute("""
                UPDATE users 
                SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user = ?
            """, (password_hash, user))
            await conn.commit()
            logger.info(f"Пароль успешно установлен для пользователя '{user}'")
            return True
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при установке пароля для пользователя {user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при установке пароля для пользователя {user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def update_user_settings(self, user: str, tg_token: str = None, 
                            chat_id: str = None, options_json: str = None):
        """
        Обновляет настройки пользователя
        
        Args:
            user: Имя пользователя
            tg_token: Новый Telegram токен (опционально)
            chat_id: Новый Chat ID (опционально)
            options_json: Новые настройки в JSON (опционально)
        """
        conn = await self._get_connection()
        try:
            # Собираем только те поля, которые нужно обновить
            updates = []
            params = []
            
            if tg_token is not None:
                updates.append("tg_token = ?")
                params.append(tg_token)
            if chat_id is not None:
                updates.append("chat_id = ?")
                params.append(chat_id)
            if options_json is not None:
                updates.append("options_json = ?")
                params.append(options_json)
            
            if not updates:
                return  # Нечего обновлять
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user)
            
            sql = f"UPDATE users SET {', '.join(updates)} WHERE user = ?"
            await conn.execute(sql, params)
            await conn.commit()
            logger.debug(f"Обновлены настройки пользователя {user}")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при обновлении настроек пользователя {user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при обновлении настроек пользователя {user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()

    async def update_user_timezone(
        self,
        user: str,
        timezone: str,
        timezone_offset_minutes: Optional[int] = None,
        timezone_offset_formatted: Optional[str] = None,
        timezone_client_locale: Optional[str] = None,
        source: str = "login_auto_detect",
    ) -> bool:
        """
        Обновляет информацию о временной зоне пользователя в options_json.

        Args:
            user: Имя пользователя
            timezone: Идентификатор временной зоны (например, "Europe/Moscow")
            timezone_offset_minutes: Смещение в минутах относительно UTC
            timezone_offset_formatted: Строковое представление смещения (например, "+03:00")
            timezone_client_locale: Локаль браузера пользователя
            source: Источник обновления (по умолчанию login_auto_detect)

        Returns:
            bool: True если данные были обновлены, False если изменений нет
        """
        conn = await self._get_connection()
        try:
            async with conn.execute(
                "SELECT options_json FROM users WHERE user = ?",
                (user,),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                logger.warning(f"Попытка обновления временной зоны для несуществующего пользователя '{user}'")
                return False

            raw_options = row["options_json"] if isinstance(row, aiosqlite.Row) else row[0]
            options: Dict[str, Any] = {}

            if raw_options:
                try:
                    options = json.loads(raw_options)
                    if not isinstance(options, dict):
                        logger.warning(f"options_json пользователя '{user}' не является объектом, перезаписываем")
                        options = {}
                except json.JSONDecodeError as decode_error:
                    logger.warning(
                        f"Не удалось распарсить options_json пользователя '{user}': {decode_error}. "
                        "Создаём новый объект настроек."
                    )
                    options = {}

            # Подготовка данных о временной зоне
            options_updated = dict(options)  # Копия для сравнения
            options_updated["timezone"] = timezone

            if timezone_offset_minutes is not None:
                options_updated["timezone_offset_minutes"] = timezone_offset_minutes
            else:
                options_updated.pop("timezone_offset_minutes", None)

            if timezone_offset_formatted:
                options_updated["timezone_offset_formatted"] = timezone_offset_formatted
            else:
                options_updated.pop("timezone_offset_formatted", None)

            if timezone_client_locale:
                options_updated["timezone_locale"] = timezone_client_locale
            else:
                options_updated.pop("timezone_locale", None)

            timezone_meta = options_updated.get("timezone_meta")
            if not isinstance(timezone_meta, dict):
                timezone_meta = {}
            timezone_meta.update(
                {
                    "detected_at": datetime.utcnow().isoformat(),
                    "source": source,
                }
            )
            options_updated["timezone_meta"] = timezone_meta

            serialized_new = json.dumps(options_updated, ensure_ascii=False)
            serialized_old = json.dumps(options, ensure_ascii=False)

            if serialized_new == serialized_old:
                logger.debug(f"Временная зона пользователя '{user}' не изменилась, обновление не требуется")
                return False

            await conn.execute(
                """
                UPDATE users
                SET options_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user = ?
                """,
                (serialized_new, user),
            )
            await conn.commit()
            logger.info(
                f"Обновлена временная зона пользователя '{user}' на '{timezone}' "
                f"(offset: {timezone_offset_formatted or timezone_offset_minutes})"
            )
            return True
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при обновлении временной зоны пользователя {user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при обновлении временной зоны пользователя {user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def delete_user(self, user: str):
        """
        Удаляет пользователя
        
        Args:
            user: Имя пользователя
            
        Returns:
            dict: Результат удаления с полями user и removed_from_users
        """
        normalized = self._normalize_username(user)
        if not normalized:
            raise ValueError("Имя пользователя не может быть пустым")
        
        conn = await self._get_connection()
        deleted_rows = 0
        exact_username = None
        try:
            # Находим точное имя пользователя в базе (без учета регистра)
            async with conn.execute("SELECT id, user FROM users WHERE LOWER(user) = LOWER(?)", (normalized,)) as cursor:
                existing_user = await cursor.fetchone()
            
            if existing_user:
                exact_username = existing_user[1] if isinstance(existing_user, aiosqlite.Row) else existing_user[1]
                
                # Удаляем пользователя (благодаря CASCADE автоматически удалятся связи в user_alerts)
                cursor = await conn.execute("DELETE FROM users WHERE user = ?", (exact_username,))
                deleted_rows = cursor.rowcount
                
                # Удаляем стрелы, которые остались без связей (если они были связаны только с этим пользователем)
                # Это происходит автоматически благодаря CASCADE в user_alerts, но мы можем также удалить
                # стрелы, которые больше ни с кем не связаны
                cursor2 = await conn.execute("""
                    DELETE FROM alerts 
                    WHERE id NOT IN (SELECT DISTINCT alert_id FROM user_alerts)
                """)
                orphaned_alerts_count = cursor2.rowcount
                if orphaned_alerts_count > 0:
                    logger.debug(f"Удалено {orphaned_alerts_count} стрел без связей после удаления пользователя {exact_username}")
            else:
                # Пользователь не найден в базе данных
                logger.warning(f"Пользователь '{normalized}' не найден в базе данных")
            
            await conn.commit()
            logger.debug(f"Удалён пользователь {exact_username or normalized} (записей в users: {deleted_rows})")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            error_user = exact_username or normalized
            logger.error(f"Ошибка БД при удалении пользователя {error_user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            error_user = exact_username or normalized
            logger.error(f"Ошибка БД при удалении пользователя {error_user}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()

        final_username = exact_username or normalized
        
        return {
            "user": final_username,
            "removed_from_users": deleted_rows > 0,
        }

    def _normalize_username(self, username: str) -> str:
        """Обрезает пробелы вокруг логина."""
        return username.strip()
    
    # ==================== РАБОТА СО СТРЕЛАМИ (ALERTS) ====================
    
    async def add_alert(self, ts: int, exchange: str, market: str, symbol: str,
                 delta: float, wick_pct: float, volume_usdt: float,
                 meta: Optional[str] = None, user_id: Optional[int] = None) -> int:
        """
        Добавляет новую стрелу в БД или связывает существующую с пользователем (асинхронная версия)
        
        Args:
            ts: Timestamp в миллисекундах
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            symbol: Торговая пара
            delta: Изменение цены в процентах
            wick_pct: Процент тени свечи
            volume_usdt: Объём в USDT
            meta: Дополнительная метаинформация (JSON строка)
            user_id: ID пользователя, для которого обнаружена стрела
            
        Returns:
            int: ID созданной или найденной записи в alerts
        """
        if user_id is None:
            raise ValueError("user_id обязателен для добавления стрелы")
        
        conn = await self._get_connection()
        try:
            # Проверяем, существует ли уже такая стрела по уникальному ключу
            async with conn.execute("""
                SELECT id FROM alerts 
                WHERE ts = ? AND exchange = ? AND market = ? AND symbol = ? 
                  AND delta = ? AND wick_pct = ? AND volume_usdt = ?
            """, (ts, exchange, market, symbol, delta, wick_pct, volume_usdt)) as cursor:
                existing_alert = await cursor.fetchone()
            
            if existing_alert:
                # Стрела уже существует, используем её ID
                alert_id = existing_alert[0]
                logger.debug(f"Найдена существующая стрела (ID: {alert_id}): {exchange} {market} {symbol} (delta: {delta}%)")
            else:
                # Создаём новую стрелу
                cursor = await conn.execute("""
                    INSERT INTO alerts 
                    (ts, exchange, market, symbol, delta, wick_pct, volume_usdt, meta)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (ts, exchange, market, symbol, delta, wick_pct, volume_usdt, meta))
                alert_id = cursor.lastrowid
                logger.debug(f"Создана новая стрела (ID: {alert_id}): {exchange} {market} {symbol} (delta: {delta}%)")
            
            # Создаём связь пользователя со стрелой (если её ещё нет)
            await conn.execute("""
                INSERT OR IGNORE INTO user_alerts (alert_id, user_id)
                VALUES (?, ?)
            """, (alert_id, user_id))
            
            await conn.commit()
            return alert_id
        except aiosqlite.IntegrityError as e:
            # Это может быть из-за UNIQUE constraint в user_alerts - это нормально
            if "UNIQUE constraint failed" in str(e):
                logger.debug(f"Связь пользователя {user_id} со стрелой {alert_id} уже существует")
                await conn.rollback()
                # Возвращаем alert_id, даже если связь уже есть
                return alert_id
            else:
                logger.error(f"Ошибка целостности при добавлении стрелы: {e}", exc_info=True)
                await conn.rollback()
                raise
        except aiosqlite.OperationalError as e:
            logger.error(f"Ошибка БД при добавлении стрелы: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при добавлении стрелы: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def get_alerts(self, exchange: Optional[str] = None, market: Optional[str] = None,
                  symbol: Optional[str] = None, user_id: Optional[int] = None,
                  ts_from: Optional[int] = None, ts_to: Optional[int] = None,
                  delta_min: Optional[float] = None, delta_max: Optional[float] = None,
                  volume_min: Optional[float] = None, volume_max: Optional[float] = None,
                  limit: Optional[int] = None, offset: Optional[int] = None,
                  order_by: str = "ts DESC") -> List[Dict[str, Any]]:
        """
        Получает стрелы с фильтрацией
        
        Args:
            exchange: Фильтр по бирже
            market: Фильтр по рынку
            symbol: Фильтр по символу
            user_id: Фильтр по пользователю (если None, возвращает все стрелы)
            ts_from: Начало временного диапазона (timestamp в мс)
            ts_to: Конец временного диапазона (timestamp в мс)
            delta_min: Минимальная дельта
            delta_max: Максимальная дельта
            volume_min: Минимальный объём
            volume_max: Максимальный объём
            limit: Лимит записей
            offset: Смещение для пагинации
            order_by: Поле для сортировки (по умолчанию ts DESC)
            
        Returns:
            List[Dict]: Список стрел (с полем user_id для обратной совместимости)
        """
        conn = await self._get_connection()
        try:
            conditions = []
            params = []
            
            # Если user_id указан, используем JOIN с user_alerts
            if user_id is not None:
                join_clause = "INNER JOIN user_alerts ua ON a.id = ua.alert_id"
                conditions.append("ua.user_id = ?")
                params.append(user_id)
            else:
                join_clause = ""
            
            # Условия для фильтрации по полям alerts
            if exchange:
                conditions.append("a.exchange = ?")
                params.append(exchange)
            if market:
                conditions.append("a.market = ?")
                params.append(market)
            if symbol:
                conditions.append("a.symbol = ?")
                params.append(symbol)
            if ts_from is not None:
                conditions.append("a.ts >= ?")
                params.append(ts_from)
            if ts_to is not None:
                conditions.append("a.ts <= ?")
                params.append(ts_to)
            if delta_min is not None:
                conditions.append("a.delta >= ?")
                params.append(delta_min)
            if delta_max is not None:
                conditions.append("a.delta <= ?")
                params.append(delta_max)
            if volume_min is not None:
                conditions.append("a.volume_usdt >= ?")
                params.append(volume_min)
            if volume_max is not None:
                conditions.append("a.volume_usdt <= ?")
                params.append(volume_max)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            limit_clause = f"LIMIT {limit}" if limit else ""
            offset_clause = f"OFFSET {offset}" if offset else ""
            
            # Если user_id указан, возвращаем user_id для обратной совместимости
            if user_id is not None:
                select_clause = """
                    SELECT a.id, a.ts, a.exchange, a.market, a.symbol, a.delta, 
                           a.wick_pct, a.volume_usdt, a.meta, a.created_at,
                           ua.user_id
                    FROM alerts a
                """
            else:
                # Если user_id не указан, возвращаем все стрелы без user_id
                select_clause = """
                    SELECT a.id, a.ts, a.exchange, a.market, a.symbol, a.delta, 
                           a.wick_pct, a.volume_usdt, a.meta, a.created_at,
                           NULL as user_id
                    FROM alerts a
                """
            
            # Формируем ORDER BY с алиасом таблицы
            order_by_clause = order_by
            if "ts" in order_by:
                order_by_clause = order_by.replace("ts", "a.ts")
            elif "created_at" in order_by:
                order_by_clause = order_by.replace("created_at", "a.created_at")
            elif "delta" in order_by:
                order_by_clause = order_by.replace("delta", "a.delta")
            elif "volume_usdt" in order_by:
                order_by_clause = order_by.replace("volume_usdt", "a.volume_usdt")
            
            sql = f"""
                {select_clause}
                {join_clause}
                {where_clause}
                ORDER BY {order_by_clause}
                {limit_clause}
                {offset_clause}
            """
            
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении стрел: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении стрел: {e}", exc_info=True)
            return []
        finally:
            await conn.close()
    
    async def clear_alerts(self, exchange: Optional[str] = None, market: Optional[str] = None,
                     user_id: Optional[int] = None) -> int:
        """
        Очищает стрелы (удаляет связи user_alerts или сами стрелы) - асинхронная версия
        
        Args:
            exchange: Если указано, удаляет только для этой биржи
            market: Если указано, удаляет только для этого рынка (spot/linear)
            user_id: Если указано, удаляет только связи для этого пользователя (без удаления самих стрел)
            
        Returns:
            int: Количество удалённых записей
        """
        conn = await self._get_connection()
        try:
            if user_id is not None:
                # Удаляем только связи пользователя со стрелами (не сами стрелы)
                conditions = ["ua.user_id = ?"]
                params = [user_id]
                
                # Добавляем фильтры по бирже и рынку через JOIN
                join_clause = "INNER JOIN alerts a ON ua.alert_id = a.id"
                if exchange:
                    conditions.append("a.exchange = ?")
                    params.append(exchange)
                if market:
                    conditions.append("a.market = ?")
                    params.append(market)
                
                where_clause = "WHERE " + " AND ".join(conditions)
                
                # Получаем количество связей для удаления
                count_query = f"SELECT COUNT(*) FROM user_alerts ua {join_clause} {where_clause}"
                async with conn.execute(count_query, params) as cursor:
                    count = (await cursor.fetchone())[0]
                
                # Удаляем связи
                delete_query = f"DELETE FROM user_alerts WHERE id IN (SELECT ua.id FROM user_alerts ua {join_clause} {where_clause})"
                await conn.execute(delete_query, params)
                
                # Удаляем стрелы, которые остались без связей (сиротские стрелы)
                # Это гарантирует, что если все пользователи удалят свои стрелы, в базе не останется никаких стрел
                orphaned_conditions = ["id NOT IN (SELECT DISTINCT alert_id FROM user_alerts WHERE alert_id IS NOT NULL)"]
                orphaned_params = []
                
                # Если были фильтры по бирже/рынку, применяем их и к очистке сиротских стрел
                if exchange:
                    orphaned_conditions.append("exchange = ?")
                    orphaned_params.append(exchange)
                if market:
                    orphaned_conditions.append("market = ?")
                    orphaned_params.append(market)
                
                orphaned_where = "WHERE " + " AND ".join(orphaned_conditions)
                
                cursor_orphaned = await conn.execute(f"DELETE FROM alerts {orphaned_where}", orphaned_params)
                orphaned_count = cursor_orphaned.rowcount
                if orphaned_count > 0:
                    logger.debug(f"Удалено {orphaned_count} сиротских стрел без связей после удаления связей пользователя {user_id}")
            else:
                # Удаляем все стрелы (и связи через CASCADE)
                conditions = []
                params = []
                
                if exchange:
                    conditions.append("exchange = ?")
                    params.append(exchange)
                if market:
                    conditions.append("market = ?")
                    params.append(market)
                
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                
                # Получаем количество стрел для удаления
                count_query = f"SELECT COUNT(*) FROM alerts {where_clause}"
                async with conn.execute(count_query, params) as cursor:
                    count = (await cursor.fetchone())[0]
                
                # Удаляем стрелы (связи удалятся автоматически через CASCADE)
                delete_query = f"DELETE FROM alerts {where_clause}"
                await conn.execute(delete_query, params)
            
            await conn.commit()
            logger.info(f"Очищено {count} записей" + 
                       (f" (exchange={exchange}, market={market}, user_id={user_id})" if exchange or market or user_id is not None else ""))
            
            return count
            
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при очистке alerts: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при очистке alerts: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def delete_user_spikes(self, user: str) -> int:
        """
        Удаляет всю статистику стрел для указанного пользователя - асинхронная версия
        
        Args:
            user: Имя пользователя
            
        Returns:
            int: Количество удалённых связей (user_alerts)
        """
        user_data = await self.get_user(user)
        if not user_data:
            raise ValueError(f"Пользователь '{user}' не найден")
        
        user_id = user_data["id"]
        return await self.clear_alerts(user_id=user_id)
    
    async def get_alerts_count(self, exchange: Optional[str] = None, market: Optional[str] = None,
                        symbol: Optional[str] = None, user_id: Optional[int] = None,
                        ts_from: Optional[int] = None, ts_to: Optional[int] = None,
                        created_after: Optional[str] = None) -> int:
        """
        Получает количество стрел с фильтрацией - асинхронная версия
        
        Args:
            exchange: Фильтр по бирже
            market: Фильтр по рынку
            symbol: Фильтр по символу
            user_id: Фильтр по пользователю (если None, считает все стрелы)
            ts_from: Начало временного диапазона (timestamp в мс)
            ts_to: Конец временного диапазона (timestamp в мс)
            created_after: Фильтр по времени создания (TIMESTAMP строка, например '2025-11-17 19:00:00')
            
        Returns:
            int: Количество записей
        """
        conn = await self._get_connection()
        try:
            conditions = []
            params = []
            
            # Если user_id указан, используем JOIN с user_alerts
            if user_id is not None:
                join_clause = "INNER JOIN user_alerts ua ON a.id = ua.alert_id"
                conditions.append("ua.user_id = ?")
                params.append(user_id)
            else:
                join_clause = ""
            
            # Условия для фильтрации по полям alerts
            if exchange:
                conditions.append("a.exchange = ?")
                params.append(exchange)
            if market:
                conditions.append("a.market = ?")
                params.append(market)
            if symbol:
                conditions.append("a.symbol = ?")
                params.append(symbol)
            if ts_from is not None:
                conditions.append("a.ts >= ?")
                params.append(ts_from)
            if ts_to is not None:
                conditions.append("a.ts <= ?")
                params.append(ts_to)
            if created_after:
                conditions.append("a.created_at >= ?")
                params.append(created_after)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            sql = f"SELECT COUNT(DISTINCT a.id) FROM alerts a {join_clause} {where_clause}"
            async with conn.execute(sql, params) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при подсчёте стрел: {e}", exc_info=True)
            return 0
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при подсчёте стрел: {e}", exc_info=True)
            return 0
        finally:
            await conn.close()
    
    # ==================== РАБОТА С ОШИБКАМИ ====================
    
    async def add_error(self, error_type: str, error_message: str,
                 exchange: Optional[str] = None, connection_id: Optional[str] = None,
                 market: Optional[str] = None, symbol: Optional[str] = None,
                 stack_trace: Optional[str] = None):
        """
        Добавляет ошибку в БД - асинхронная версия
        
        Args:
            error_type: Тип ошибки (например, "reconnect", "websocket_error", "critical")
            error_message: Сообщение об ошибке
            exchange: Название биржи
            connection_id: ID соединения
            market: Тип рынка
            symbol: Торговая пара
            stack_trace: Стек трейс ошибки
        """
        conn = await self._get_connection()
        try:
            await conn.execute("""
                INSERT INTO errors 
                (error_type, error_message, exchange, connection_id, market, symbol, stack_trace)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (error_type, error_message, exchange, connection_id, market, symbol, stack_trace))
            await conn.commit()
            logger.debug(f"Добавлена ошибка: {error_type} - {exchange}")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при добавлении ошибки в БД: {e}", exc_info=True)
            await conn.rollback()
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при добавлении ошибки в БД: {e}", exc_info=True)
            await conn.rollback()
        finally:
            await conn.close()
    
    async def get_errors(self, exchange: Optional[str] = None,
                  error_type: Optional[str] = None,
                  timestamp_from: Optional[str] = None,
                  timestamp_to: Optional[str] = None,
                  limit: Optional[int] = None,
                  order_by: str = "timestamp DESC") -> List[Dict[str, Any]]:
        """
        Получает ошибки с фильтрацией - асинхронная версия
        
        Args:
            exchange: Фильтр по бирже
            error_type: Фильтр по типу ошибки
            timestamp_from: Начало временного диапазона
            timestamp_to: Конец временного диапазона
            limit: Лимит записей
            order_by: Поле для сортировки
            
        Returns:
            List[Dict]: Список ошибок
        """
        conn = await self._get_connection()
        try:
            conditions = []
            params = []
            
            if exchange:
                conditions.append("exchange = ?")
                params.append(exchange)
            if error_type:
                conditions.append("error_type = ?")
                params.append(error_type)
            if timestamp_from:
                conditions.append("timestamp >= ?")
                params.append(timestamp_from)
            if timestamp_to:
                conditions.append("timestamp <= ?")
                params.append(timestamp_to)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            limit_clause = f"LIMIT {limit}" if limit else ""
            
            sql = f"""
                SELECT * FROM errors
                {where_clause}
                ORDER BY {order_by}
                {limit_clause}
            """
            
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении ошибок: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении ошибок: {e}", exc_info=True)
            return []
        finally:
            await conn.close()
    
    async def delete_error(self, error_id: int) -> bool:
        """
        Удаляет ошибку по ID - асинхронная версия
        
        Args:
            error_id: ID ошибки для удаления
            
        Returns:
            bool: True если ошибка была удалена, False если не найдена
        """
        conn = await self._get_connection()
        try:
            cursor = await conn.execute("DELETE FROM errors WHERE id = ?", (error_id,))
            deleted = cursor.rowcount > 0
            await conn.commit()
            if deleted:
                logger.info(f"Удалена ошибка с ID {error_id}")
            else:
                logger.warning(f"Ошибка с ID {error_id} не найдена")
            return deleted
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при удалении ошибки {error_id}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при удалении ошибки {error_id}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def delete_all_errors(self) -> int:
        """
        Удаляет все ошибки из БД - асинхронная версия
        
        Returns:
            int: Количество удалённых ошибок
        """
        conn = await self._get_connection()
        try:
            # Получаем количество ошибок перед удалением
            async with conn.execute("SELECT COUNT(*) FROM errors") as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0
            
            # Удаляем все ошибки
            await conn.execute("DELETE FROM errors")
            await conn.commit()
            logger.info(f"Удалено всех ошибок: {count}")
            return count
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при удалении всех ошибок: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при удалении всех ошибок: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    # ==================== РАБОТА С ЧЁРНЫМИ СПИСКАМИ ====================
    
    async def add_to_blacklist(self, exchange: str, market: str, symbol: str):
        """
        Добавляет символ в чёрный список биржи - асинхронная версия
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            symbol: Торговая пара
        """
        conn = await self._get_connection()
        try:
            await conn.execute("""
                INSERT OR IGNORE INTO exchange_blacklists (exchange, market, symbol)
                VALUES (?, ?, ?)
            """, (exchange, market, symbol))
            await conn.commit()
            logger.debug(f"Добавлен в чёрный список: {exchange} {market} {symbol}")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при добавлении в чёрный список: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при добавлении в чёрный список: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def remove_from_blacklist(self, exchange: str, market: str, symbol: str):
        """
        Удаляет символ из чёрного списка - асинхронная версия
        
        Args:
            exchange: Название биржи
            market: Тип рынка
            symbol: Торговая пара
        """
        conn = await self._get_connection()
        try:
            await conn.execute("""
                DELETE FROM exchange_blacklists
                WHERE exchange = ? AND market = ? AND symbol = ?
            """, (exchange, market, symbol))
            await conn.commit()
            logger.debug(f"Удалён из чёрного списка: {exchange} {market} {symbol}")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при удалении из чёрного списка: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при удалении из чёрного списка: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def get_blacklist(self, exchange: Optional[str] = None,
                     market: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получает чёрный список - асинхронная версия
        
        Args:
            exchange: Фильтр по бирже
            market: Фильтр по рынку
            
        Returns:
            List[Dict]: Список символов в чёрном списке
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
            
            sql = f"SELECT * FROM exchange_blacklists {where_clause} ORDER BY exchange, market, symbol"
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении чёрного списка: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении чёрного списка: {e}", exc_info=True)
            return []
        finally:
            await conn.close()
    
    async def is_blacklisted(self, exchange: str, market: str, symbol: str) -> bool:
        """
        Проверяет, находится ли символ в чёрном списке - асинхронная версия
        
        Args:
            exchange: Название биржи
            market: Тип рынка
            symbol: Торговая пара
            
        Returns:
            bool: True если символ в чёрном списке
        """
        conn = await self._get_connection()
        try:
            async with conn.execute("""
                SELECT 1 FROM exchange_blacklists
                WHERE exchange = ? AND market = ? AND symbol = ?
            """, (exchange, market, symbol)) as cursor:
                row = await cursor.fetchone()
                return row is not None
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при проверке чёрного списка: {e}", exc_info=True)
            return False
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при проверке чёрного списка: {e}", exc_info=True)
            return False
        finally:
            await conn.close()
    
    # ==================== РАБОТА С АЛИАСАМИ ====================
    
    async def add_alias(self, exchange: str, market: str, original_symbol: str, alias: str):
        """
        Добавляет алиас для символа - асинхронная версия
        
        Args:
            exchange: Название биржи
            market: Тип рынка
            original_symbol: Оригинальное название символа
            alias: Алиас
        """
        conn = await self._get_connection()
        try:
            await conn.execute("""
                INSERT OR REPLACE INTO symbol_aliases 
                (exchange, market, original_symbol, alias)
                VALUES (?, ?, ?, ?)
            """, (exchange, market, original_symbol, alias))
            await conn.commit()
            logger.debug(f"Добавлен алиас: {exchange} {market} {original_symbol} -> {alias}")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при добавлении алиаса: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при добавлении алиаса: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def get_alias(self, exchange: str, market: str, symbol: str) -> Optional[str]:
        """
        Получает алиас для символа, если он существует - асинхронная версия
        
        Args:
            exchange: Название биржи
            market: Тип рынка
            symbol: Торговая пара
            
        Returns:
            str: Алиас или None
        """
        conn = await self._get_connection()
        try:
            async with conn.execute("""
                SELECT alias FROM symbol_aliases
                WHERE exchange = ? AND market = ? AND original_symbol = ?
            """, (exchange, market, symbol)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении алиаса: {e}", exc_info=True)
            return None
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении алиаса: {e}", exc_info=True)
            return None
        finally:
            await conn.close()
    
    async def get_all_aliases(self, exchange: Optional[str] = None,
                       market: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получает все алиасы - асинхронная версия
        
        Args:
            exchange: Фильтр по бирже
            market: Фильтр по рынку
            
        Returns:
            List[Dict]: Список алиасов
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
            
            sql = f"SELECT * FROM symbol_aliases {where_clause} ORDER BY exchange, market, original_symbol"
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении алиасов: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении алиасов: {e}", exc_info=True)
            return []
        finally:
            await conn.close()
    
    # ==================== РАБОТА СО СТАТИСТИКОЙ БИРЖ ====================
    
    async def upsert_exchange_statistics(
        self,
        exchange: str,
        market: str,
        symbols_count: int,
        ws_connections: int,
        batches_per_ws: Optional[int] = None,
        reconnects: int = 0,
        candles_count: int = 0,
        last_candle_time: Optional[str] = None,
        ticks_per_second: Optional[float] = None,
    ):
        """
        Сохраняет или обновляет статистику биржи и рынка - асинхронная версия.
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            symbols_count: Количество торговых пар
            ws_connections: Количество WebSocket-подключений
            batches_per_ws: Количество батчей внутри одного вебсокета (если есть)
            reconnects: Количество реконнектов
            candles_count: Количество собранных свечей
            last_candle_time: Время последней собранной свечи (TIMESTAMP строка)
            ticks_per_second: Среднее количество входящих сообщений в секунду
        """
        conn = await self._get_connection()
        try:
            await conn.execute("""
                INSERT OR REPLACE INTO exchange_statistics 
                (exchange, market, symbols_count, ws_connections, batches_per_ws, 
                 reconnects, candles_count, last_candle_time, ticks_per_second, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                exchange,
                market,
                symbols_count,
                ws_connections,
                batches_per_ws,
                reconnects,
                candles_count,
                last_candle_time,
                ticks_per_second,
            ))
            await conn.commit()
            logger.debug(f"Обновлена статистика: {exchange} {market}")
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при сохранении статистики {exchange} {market}: {e}", exc_info=True)
            await conn.rollback()
            raise
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при сохранении статистики {exchange} {market}: {e}", exc_info=True)
            await conn.rollback()
            raise
        finally:
            await conn.close()
    
    async def get_exchange_statistics(
        self,
        exchange: Optional[str] = None,
        market: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает статистику бирж и рынков - асинхронная версия.
        
        Args:
            exchange: Фильтр по бирже (опционально)
            market: Фильтр по рынку (опционально)
            
        Returns:
            List[Dict]: Список статистики
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
            
            sql = f"""
                SELECT * FROM exchange_statistics
                {where_clause}
                ORDER BY exchange, market
            """
            
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except (aiosqlite.OperationalError, aiosqlite.IntegrityError) as e:
            logger.error(f"Ошибка БД при получении статистики: {e}", exc_info=True)
            return []
        except aiosqlite.Error as e:
            logger.error(f"Ошибка БД при получении статистики: {e}", exc_info=True)
            return []
        finally:
            await conn.close()


# Глобальный экземпляр БД для использования в приложении
db = Database()

