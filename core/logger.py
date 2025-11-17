"""
Универсальная система логирования для проекта
"""
import logging
import logging.handlers
import traceback
import asyncio
import concurrent.futures
from pathlib import Path
from collections import deque
from threading import Lock

# Глобальная очередь для записи ошибок в БД
_error_queue = asyncio.Queue()
_queue_processor_started = False
_queue_lock = Lock()


async def _process_error_queue():
    """
    Фоновый процессор очереди ошибок.
    Обрабатывает ошибки последовательно, чтобы избежать блокировок БД.
    """
    from BD.database import db
    
    while True:
        try:
            # Получаем ошибку из очереди (блокирующий вызов)
            error_data = await _error_queue.get()
            
            if error_data is None:  # Сигнал остановки
                break
            
            try:
                # Записываем ошибку в БД
                await db.add_error(
                    error_type=error_data["error_type"],
                    error_message=error_data["error_message"],
                    exchange=error_data.get("exchange"),
                    connection_id=error_data.get("connection_id"),
                    market=error_data.get("market"),
                    symbol=error_data.get("symbol"),
                    stack_trace=error_data.get("stack_trace"),
                )
            except Exception as e:
                # Логируем ошибку записи в БД без записи в БД (избегаем рекурсии)
                logging.getLogger(__name__).error(
                    f"Ошибка при записи ошибки в БД: {e}",
                    exc_info=True,
                    extra={"skip_db_logging": True}
                )
            finally:
                _error_queue.task_done()
        except Exception as e:
            # Критическая ошибка в процессоре очереди
            logging.getLogger(__name__).error(
                f"Критическая ошибка в процессоре очереди ошибок: {e}",
                exc_info=True,
                extra={"skip_db_logging": True}
            )
            await asyncio.sleep(1)  # Небольшая задержка перед следующей попыткой


def _start_queue_processor():
    """
    Запускает фоновый процессор очереди ошибок, если он еще не запущен.
    """
    global _queue_processor_started
    
    with _queue_lock:
        if _queue_processor_started:
            return
        
        try:
            # Пытаемся получить текущий event loop
            loop = asyncio.get_running_loop()
            # Если loop запущен, создаем задачу
            if not hasattr(loop, '_error_queue_task'):
                loop._error_queue_task = asyncio.create_task(_process_error_queue())
                _queue_processor_started = True
        except RuntimeError:
            # Нет запущенного loop - запустим при первом вызове через asyncio.run
            # Это произойдет в отдельном потоке
            pass


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
            from BD.database import db

            # Пытаемся использовать текущий event loop
            try:
                loop = asyncio.get_running_loop()
                # Если loop запущен, создаем задачу (не блокирующую)
                asyncio.create_task(db.add_error(
                    error_type=str(error_type)[:64],
                    error_message=message[:1024],
                    exchange=exchange,
                    connection_id=connection_id,
                    market=market,
                    symbol=symbol,
                    stack_trace=stack_trace[:4000] if isinstance(stack_trace, str) else stack_trace,
                ))
            except RuntimeError:
                # Нет запущенного loop - используем очередь или просто игнорируем
                # В этом случае ошибка не будет записана в БД, но это лучше, чем блокировка
                # Можно также использовать threading для создания отдельного loop
                pass
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

