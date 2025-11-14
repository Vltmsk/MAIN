"""
Универсальная система логирования для проекта
"""
import logging
import logging.handlers
import traceback
from pathlib import Path


class DatabaseErrorHandler(logging.Handler):
    """
    Кастомный handler для записи ошибок в БД.
    """

    def emit(self, record: logging.LogRecord) -> None:
        should_log = record.levelno >= logging.ERROR or getattr(record, "log_to_db", False)
        if not should_log or getattr(record, "skip_db_logging", False):
            return

        try:
            message = record.getMessage()
        except Exception:
            message = record.msg if isinstance(record.msg, str) else str(record.msg)

        error_type = getattr(record, "error_type", None) or record.levelname.lower()
        exchange = getattr(record, "exchange", None)
        connection_id = getattr(record, "connection_id", None)
        market = getattr(record, "market", None)
        symbol = getattr(record, "symbol", None)
        stack_trace = getattr(record, "stack_trace", None)

        if stack_trace is None:
            if record.exc_info:
                stack_trace = "".join(traceback.format_exception(*record.exc_info))
            elif record.stack_info:
                stack_trace = record.stack_info

        try:
            from BD.database import db  # Ленивая загрузка во избежание циклических импортов

            db.add_error(
                error_type=str(error_type)[:64],
                error_message=message[:1024],
                exchange=exchange,
                connection_id=connection_id,
                market=market,
                symbol=symbol,
                stack_trace=stack_trace[:4000] if isinstance(stack_trace, str) else stack_trace,
            )
        except Exception:
            # Избегаем рекурсивного логирования при ошибках записи в БД
            pass


def _ensure_db_handler(logger: logging.Logger) -> None:
    """
    Добавляет DatabaseErrorHandler к указанному логгеру, если он ещё не добавлен.
    """
    has_db_handler = any(isinstance(handler, DatabaseErrorHandler) for handler in logger.handlers)
    if not has_db_handler:
        db_handler = DatabaseErrorHandler()
        db_handler.setLevel(logging.INFO)
        logger.addHandler(db_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер для указанного модуля.
    
    Args:
        name: Имя модуля (обычно __name__)
        
    Returns:
        Настроенный логгер
    """
    logger = logging.getLogger(name)

    # Если менеджмент уже настроен, просто убеждаемся, что handler для БД подключён
    if logger.handlers:
        _ensure_db_handler(logger)
        return logger

    # Проверяем root logger
    root_logger = logging.getLogger()
    if root_logger.handlers:
        logger.setLevel(logging.INFO)
        _ensure_db_handler(logger)
        return logger

    # Если root logger не настроен, настраиваем локально
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _ensure_db_handler(logger)

    return logger


def setup_root_logger(level: str = "INFO", enable_file_logging: bool = True):
    """
    Настройка корневого логгера с поддержкой ротации логов.
    
    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        enable_file_logging: Включить запись логов в файл с ротацией
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    
    # Очищаем существующие handlers, если они есть
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Форматтер для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler (всегда включен)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # File handler с ротацией (опционально)
    if enable_file_logging:
        # Создаём директорию для логов, если её нет
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / "app.log"
        
        # RotatingFileHandler: максимум 10MB на файл, храним 5 файлов
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

    root_logger.setLevel(log_level)
    _ensure_db_handler(root_logger)

