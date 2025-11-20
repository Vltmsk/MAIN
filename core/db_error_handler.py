"""
Утилиты для обработки ошибок БД в API
"""
import sqlite3
import aiosqlite
from fastapi import HTTPException
from core.logger import get_logger

logger = get_logger(__name__)


def handle_db_error(
    error: Exception,
    operation: str,
    user: str = None,
    endpoint: str = None,
    raise_exception: bool = True
) -> HTTPException:
    """
    Обрабатывает ошибки БД и возвращает соответствующий HTTPException.
    
    Args:
        error: Исключение из БД
        operation: Описание операции (например, "регистрация пользователя")
        user: Имя пользователя (опционально)
        endpoint: Путь эндпоинта (опционально)
        raise_exception: Если True, выбрасывает HTTPException, иначе возвращает
        
    Returns:
        HTTPException: Исключение для FastAPI
        
    Raises:
        HTTPException: Если raise_exception=True
    """
    user_str = f" '{user}'" if user else ""
    endpoint_str = f" на {endpoint}" if endpoint else ""
    
    # Ошибки целостности (UNIQUE constraint, FOREIGN KEY и т.д.)
    if isinstance(error, (sqlite3.IntegrityError, aiosqlite.IntegrityError)):
        logger.error(
            f"Ошибка целостности БД при {operation}{user_str}: {error}",
            exc_info=True,
            extra={
                "log_to_db": True,
                "error_type": "db_integrity_error",
                "market": "api",
                "symbol": endpoint or operation,
            },
        )
        exc = HTTPException(
            status_code=400,
            detail="Пользователь уже существует или нарушена целостность данных"
        )
        if raise_exception:
            raise exc
        return exc
    
    # Операционные ошибки БД (таблица не существует, синтаксические ошибки и т.д.)
    if isinstance(error, (sqlite3.OperationalError, aiosqlite.OperationalError)):
        logger.error(
            f"Ошибка БД при {operation}{user_str}: {error}",
            exc_info=True,
            extra={
                "log_to_db": True,
                "error_type": "db_operational_error",
                "market": "api",
                "symbol": endpoint or operation,
            },
        )
        exc = HTTPException(
            status_code=500,
            detail="Ошибка базы данных. Попробуйте позже."
        )
        if raise_exception:
            raise exc
        return exc
    
    # Общие ошибки БД
    if isinstance(error, (sqlite3.Error, aiosqlite.Error)):
        logger.error(
            f"Ошибка БД при {operation}{user_str}: {error}",
            exc_info=True,
            extra={
                "log_to_db": True,
                "error_type": "db_error",
                "market": "api",
                "symbol": endpoint or operation,
            },
        )
        exc = HTTPException(
            status_code=500,
            detail="Ошибка базы данных. Попробуйте позже."
        )
        if raise_exception:
            raise exc
        return exc
    
    # Неожиданные ошибки
    logger.error(
        f"Неожиданная ошибка при {operation}{user_str}: {error}",
        exc_info=True,
        extra={
            "log_to_db": True,
            "error_type": f"{operation}_error",
            "market": "api",
            "symbol": endpoint or operation,
        },
    )
    exc = HTTPException(
        status_code=500,
        detail="Внутренняя ошибка сервера"
    )
    if raise_exception:
        raise exc
    return exc





