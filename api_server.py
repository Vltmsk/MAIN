"""
FastAPI сервер для работы с базой данных и предоставления API
"""
import traceback
import os
import sqlite3
import aiosqlite
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from typing import Optional, List
from BD.database import db
import time
from datetime import datetime
import pytz
from core.logger import get_logger, setup_root_logger
from core.db_error_handler import handle_db_error
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

setup_root_logger("INFO")
logger = get_logger(__name__)

# Инициализация rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Crypto Spikes API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Функция для получения времени запуска main.py
def get_main_start_time() -> Optional[float]:
    """
    Получает время запуска main.py из файла.
    Если файл не существует (main.py не запущен), возвращает None.
    """
    try:
        import os
        start_time_file = os.path.join(os.path.dirname(__file__), ".main_start_time")
        if os.path.exists(start_time_file):
            with open(start_time_file, 'r') as f:
                main_start_time = float(f.read().strip())
            return main_start_time
    except Exception as e:
        logger.debug(f"Не удалось прочитать время запуска main.py: {e}")
    # Если файл не существует, main.py не запущен
    return None

# Настройка CORS для работы с Next.js
# Поддержка локальной разработки и production домена
cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Добавляем домен из переменной окружения (для production)
domain = os.getenv("DOMAIN", "")
if domain:
    # Поддержка HTTP и HTTPS
    if not domain.startswith("http"):
        cors_origins.extend([
            f"http://{domain}",
            f"https://{domain}",
        ])
    else:
        cors_origins.append(domain)
    # Также добавляем вариант с www
    if not domain.startswith("www."):
        cors_origins.extend([
            f"http://www.{domain}",
            f"https://www.{domain}",
        ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Централизованная обработка ошибок
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Обработка ошибок валидации Pydantic"""
    logger.warning(
        f"Ошибка валидации на {request.method} {request.url.path}: {exc.errors()}",
        extra={
            "log_to_db": False,  # Ошибки валидации не критичны
            "error_type": "validation_error",
            "market": "api",
            "symbol": request.url.path,
        },
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Обработка HTTP исключений"""
    # Логируем только критические ошибки (500+)
    if exc.status_code >= 500:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        logger.error(
            f"HTTPException {exc.status_code} на {request.method} {request.url.path}: {detail}",
            exc_info=True,
            extra={
                "log_to_db": True,
                "error_type": "api_exception",
                "market": "api",
                "symbol": request.url.path,
                "stack_trace": detail,
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Централизованная обработка всех необработанных исключений"""
    # Не перехватываем критические системные исключения
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        raise exc
    
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(
        f"Необработанная ошибка на {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={
            "log_to_db": True,
            "error_type": "api_exception",
            "market": "api",
            "symbol": request.url.path,
            "stack_trace": stack,
        },
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервера. Ошибка залогирована в админ панель.",
            "error_type": "internal_server_error"
        },
    )


@app.middleware("http")
async def log_api_errors(request: Request, call_next):
    """Middleware для логирования ошибок API"""
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            logger.error(
                f"API ответ {response.status_code} для {request.method} {request.url.path}",
                extra={
                    "log_to_db": True,
                    "error_type": "api_error",
                    "market": "api",
                    "symbol": request.url.path,
                },
            )
        return response
    except Exception as exc:
        # Исключения обрабатываются централизованными handlers
        raise


# Модели данных
class UserCreate(BaseModel):
    tg_token: Optional[str] = ""
    chat_id: Optional[str] = ""
    options_json: Optional[str] = "{}"


class UserRegister(BaseModel):
    password: str
    tg_token: Optional[str] = ""
    chat_id: Optional[str] = ""
    options_json: Optional[str] = "{}"


class UserLogin(BaseModel):
    password: str
    timezone: Optional[str] = None
    timezone_offset_minutes: Optional[int] = None
    timezone_offset_formatted: Optional[str] = None
    timezone_client_locale: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    user: str
    tg_token: str
    chat_id: str
    options_json: str
    created_at: str
    updated_at: str


class AlertCreate(BaseModel):
    ts: int
    exchange: str
    market: str
    symbol: str
    delta: float
    wick_pct: float
    volume_usdt: float
    meta: Optional[str] = None
    user_id: Optional[int] = None


class AlertResponse(BaseModel):
    id: int
    ts: int
    exchange: str
    market: str
    symbol: str
    delta: float
    wick_pct: float
    volume_usdt: float
    meta: Optional[str]
    user_id: Optional[int]
    created_at: str


class ErrorCreate(BaseModel):
    error_type: str
    error_message: str
    exchange: Optional[str] = None
    connection_id: Optional[str] = None
    market: Optional[str] = None
    symbol: Optional[str] = None
    stack_trace: Optional[str] = None


# ==================== ВАЛИДАЦИЯ СТРАТЕГИЙ ====================

def validate_strategy(strategy: dict, strategy_index: int) -> List[str]:
    """
    Валидирует стратегию и возвращает список ошибок.
    
    Args:
        strategy: Словарь со стратегией
        strategy_index: Индекс стратегии (для сообщений об ошибках)
        
    Returns:
        List[str]: Список сообщений об ошибках (пустой, если ошибок нет)
    """
    errors = []
    strategy_name = strategy.get("name", f"Стратегия #{strategy_index + 1}")
    
    # Проверяем только если стратегия включена и useGlobalFilters = false
    enabled = strategy.get("enabled", True)
    use_global_filters = strategy.get("useGlobalFilters", True)  # По умолчанию True для обратной совместимости
    
    if enabled is False:
        # Если стратегия отключена, не валидируем её
        return errors
    
    if use_global_filters is False:
        # Проверяем наличие базовых фильтров
        conditions = strategy.get("conditions", [])
        
        has_delta = False
        has_volume = False
        has_wick_pct = False
        
        for condition in conditions:
            condition_type = condition.get("type")
            
            if condition_type == "delta":
                value_min = condition.get("valueMin")
                if value_min is not None:
                    has_delta = True
                    # Валидация диапазона delta (0.01% - 100%)
                    if value_min < 0.01 or value_min > 100:
                        errors.append(
                            f'Стратегия "{strategy_name}": Дельта должна быть в диапазоне от 0.01% до 100%'
                        )
                    value_max = condition.get("valueMax")
                    if value_max is not None and (value_max < 0.01 or value_max > 100):
                        errors.append(
                            f'Стратегия "{strategy_name}": Максимальная дельта должна быть в диапазоне от 0.01% до 100%'
                        )
                    if value_max is not None and value_min > value_max:
                        errors.append(
                            f'Стратегия "{strategy_name}": Минимальная дельта не может быть больше максимальной'
                        )
            
            elif condition_type == "volume":
                value = condition.get("value")
                if value is not None:
                    has_volume = True
                    # Валидация диапазона volume (1 - 1,000,000,000 USDT)
                    if value < 1 or value > 1_000_000_000:
                        errors.append(
                            f'Стратегия "{strategy_name}": Объём должен быть в диапазоне от 1 до 1,000,000,000 USDT'
                        )
            
            elif condition_type == "wick_pct":
                value_min = condition.get("valueMin")
                value_max = condition.get("valueMax")
                if value_min is not None:
                    has_wick_pct = True
                    # Валидация минимального значения wick_pct (0% - 100%)
                    if value_min < 0 or value_min > 100:
                        errors.append(
                            f'Стратегия "{strategy_name}": Тень должна быть в диапазоне от 0% до 100%'
                        )
                # Проверяем, что valueMax не указан для wick_pct (больше не поддерживается)
                if value_max is not None:
                    errors.append(
                        f'Стратегия "{strategy_name}": Для условия "wick_pct" поддерживается только минимальное значение (valueMin). Параметр valueMax больше не используется.'
                    )
            
        
        # Проверяем наличие базовых фильтров
        missing_fields = []
        if not has_delta:
            missing_fields.append("Дельта")
        if not has_volume:
            missing_fields.append("Объём")
        if not has_wick_pct:
            missing_fields.append("Тень")
        
        if missing_fields:
            errors.append(
                f'Стратегия "{strategy_name}" не может работать без базовых фильтров. '
                f'Пожалуйста, либо включите "Использовать мои фильтры из глобальных настроек", '
                f'либо укажите значения для {", ".join(missing_fields)} в условиях стратегии.'
            )
    
    # Валидация для всех стратегий (независимо от useGlobalFilters)
    conditions = strategy.get("conditions", [])
    for condition in conditions:
        condition_type = condition.get("type")
        
        if condition_type == "series":
            count = condition.get("count")
            if count is not None and (count < 1 or count > 100):
                errors.append(
                    f'Стратегия "{strategy_name}": Количество стрел в серии должно быть от 1 до 100'
                )
            
            time_window = condition.get("timeWindowSeconds")
            if time_window is not None and (time_window < 1 or time_window > 3600):
                errors.append(
                    f'Стратегия "{strategy_name}": Временное окно должно быть от 1 до 3600 секунд (1 час)'
                )
        
        elif condition_type == "direction":
            direction = condition.get("direction")
            if direction is not None and direction not in ["up", "down"]:
                errors.append(
                    f'Стратегия "{strategy_name}": Направление может быть только "up" или "down"'
                )
    
    return errors


def validate_strategies(options_json: str) -> List[str]:
    """
    Валидирует все стратегии в options_json.
    
    Args:
        options_json: JSON строка с настройками пользователя
        
    Returns:
        List[str]: Список всех ошибок валидации (пустой, если ошибок нет)
    """
    errors = []
    
    try:
        import json
        options = json.loads(options_json) if options_json else {}
        conditional_templates = options.get("conditionalTemplates", [])
        
        if not isinstance(conditional_templates, list):
            return [f"Поле 'conditionalTemplates' должно быть массивом"]
        
        # Ограничение количества стратегий (рекомендуется до 50)
        if len(conditional_templates) > 50:
            errors.append(
                f"Превышено рекомендуемое количество стратегий (50). "
                f"Текущее количество: {len(conditional_templates)}. "
                f"Большое количество стратегий может повлиять на производительность."
            )
        
        # Валидируем каждую стратегию
        for index, strategy in enumerate(conditional_templates):
            if not isinstance(strategy, dict):
                errors.append(f"Стратегия #{index + 1} должна быть объектом")
                continue
            
            strategy_errors = validate_strategy(strategy, index)
            errors.extend(strategy_errors)
    
    except json.JSONDecodeError as e:
        errors.append(f"Ошибка парсинга JSON: {str(e)}")
    except Exception as e:
        errors.append(f"Ошибка валидации стратегий: {str(e)}")
    
    return errors


# ==================== ПОЛЬЗОВАТЕЛИ ====================

@app.post("/api/auth/register/{user}", response_model=dict)
@limiter.limit("5/minute")  # Ограничение: 5 попыток в минуту с одного IP
async def register_user(request: Request, user: str, user_data: UserRegister):
    """Регистрирует нового пользователя"""
    try:
        if len(user_data.password) < 4:
            raise HTTPException(status_code=400, detail="Пароль должен быть не менее 4 символов")
        
        # Дефолтные настройки для нового пользователя: все биржи отключены, все значения пустые
        default_options = {
            "exchanges": {
                "gate": False,
                "binance": False,
                "bitget": False,
                "bybit": False,
                "hyperliquid": False,
            },
            "pairSettings": {}
        }
        
        # Если пользователь передал свои настройки, используем их, иначе дефолтные
        import json
        if user_data.options_json and user_data.options_json != "{}":
            try:
                user_options = json.loads(user_data.options_json)
                # Объединяем с дефолтами, чтобы убедиться что все поля присутствуют
                default_options.update(user_options)
                options_json = json.dumps(default_options)
            except (json.JSONDecodeError, ValueError):
                # Если ошибка парсинга, используем дефолтные настройки
                options_json = json.dumps(default_options)
        else:
            options_json = json.dumps(default_options)
        
        user_id = await db.register_user(
            user=user,
            password=user_data.password,
            tg_token=user_data.tg_token or "",
            chat_id=user_data.chat_id or "",
            options_json=options_json
        )
        # Получаем точное имя пользователя из базы
        user_info = await db.get_user(user)
        canonical_user = user_info["user"] if user_info else user
        
        return {"id": user_id, "user": canonical_user, "message": "User registered successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (sqlite3.IntegrityError, sqlite3.OperationalError, sqlite3.Error,
            aiosqlite.IntegrityError, aiosqlite.OperationalError, aiosqlite.Error) as e:
        handle_db_error(e, "регистрации пользователя", user=user, endpoint=f"register/{user}")
    except Exception as e:
        handle_db_error(e, "регистрации пользователя", user=user, endpoint=f"register/{user}")


@app.post("/api/auth/login/{user}", response_model=dict)
@limiter.limit("5/minute")  # Ограничение: 5 попыток в минуту с одного IP
async def login_user(request: Request, user: str, login_data: UserLogin):
    """
    Аутентифицирует пользователя
    
    Основная логика: проверка пароля и возврат существующих данных.
    Дополнительно при наличии информации о временной зоне обновляет её в профиле.
    """
    try:
        # Проверяем, что параметр user не является строкой 'login' (это может быть ошибка маршрутизации)
        if user.lower() == 'login':
            logger.error(f"[Login] Обнаружена попытка входа с параметром 'login' вместо имени пользователя. URL: {request.url.path}")
            raise HTTPException(status_code=400, detail="Некорректный параметр пользователя. Убедитесь, что имя пользователя указано правильно в URL.")
        
        logger.debug(f"[Login] Попытка входа для пользователя: '{user}' (URL path: {request.url.path})")
        # Проверяем, что пароль не пустой
        if not login_data.password or len(login_data.password.strip()) == 0:
            raise HTTPException(status_code=400, detail="Пароль не может быть пустым")
        
        # ТОЛЬКО проверка пароля и чтение данных - никаких обновлений
        try:
            user_data = await db.authenticate_user(user, login_data.password)
        except ValueError as e:
            # Специальные пользовательские ошибки (например, нет пароля / не завершена регистрация)
            raise HTTPException(status_code=400, detail=str(e))
        if not user_data:
            # Пользователь не найден или пароль неверный
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")

        canonical_user = user_data["user"]
        
        # Обновляем временную зону, если пришла от клиента
        if login_data.timezone:
            try:
                await db.update_user_timezone(
                    user=canonical_user,
                    timezone=login_data.timezone,
                    timezone_offset_minutes=login_data.timezone_offset_minutes,
                    timezone_offset_formatted=login_data.timezone_offset_formatted,
                    timezone_client_locale=login_data.timezone_client_locale,
                    source="login_auto_detect",
                )
            except (sqlite3.OperationalError, sqlite3.IntegrityError, aiosqlite.OperationalError, aiosqlite.IntegrityError) as tz_error:
                # Не прерываем вход, но логируем ошибку БД
                logger.warning(
                    f"Не удалось обновить временную зону пользователя '{user}': {tz_error}",
                    exc_info=True,
                    extra={
                        "log_to_db": True,
                        "error_type": "timezone_update_error",
                        "market": "api",
                        "symbol": f"login/{user}",
                    },
                )
            except Exception as tz_error:
                # Не прерываем вход, но логируем ошибку
                logger.warning(
                    f"Не удалось обновить временную зону пользователя '{user}': {tz_error}",
                    exc_info=True,
                    extra={
                        "log_to_db": False,  # Не критично
                        "error_type": "timezone_update_warning",
                        "market": "api",
                        "symbol": f"login/{user}",
                    },
                )
        
        # Возвращаем данные пользователя (без пароля)
        return {
            "id": user_data["id"],
            "user": user_data["user"],
            "tg_token": user_data.get("tg_token", ""),
            "chat_id": user_data.get("chat_id", ""),
            "options_json": user_data.get("options_json", "{}"),
            "message": "Login successful"
        }
    except HTTPException:
        raise
    except (sqlite3.IntegrityError, sqlite3.OperationalError, sqlite3.Error,
            aiosqlite.IntegrityError, aiosqlite.OperationalError, aiosqlite.Error) as e:
        handle_db_error(e, "входе пользователя", user=user, endpoint=f"login/{user}")
    except Exception as e:
        handle_db_error(e, "входе пользователя", user=user, endpoint=f"login/{user}")


@app.post("/api/users/{user}/settings", response_model=dict)
async def create_or_update_user(user: str, user_data: UserCreate):
    """Создаёт или обновляет пользователя"""
    try:
        # FastAPI автоматически декодирует параметры пути, но на случай двойного кодирования
        # пытаемся декодировать еще раз. Если уже декодировано, unquote вернет исходное значение
        try:
            decoded_user = unquote(user)
            # Если декодирование не изменило строку, значит она уже была декодирована
            if decoded_user == user:
                decoded_user = user
        except Exception:
            # Если ошибка декодирования, используем исходное значение
            decoded_user = user
        
        # Убираем лишние пробелы
        decoded_user = decoded_user.strip()
        
        if not decoded_user:
            raise HTTPException(status_code=400, detail="Имя пользователя не может быть пустым")
        
        logger.info(f"Создание/обновление пользователя: исходный параметр='{user}', декодированный='{decoded_user}'")
        
        # Проверяем права доступа: получаем пользователя из БД для проверки
        existing_user = await db.get_user(decoded_user)
        if existing_user:
            # Пользователь существует - проверяем, что это тот же пользователь
            # (в будущем можно добавить проверку токена/сессии)
            pass
        # Если пользователь не существует, он будет создан
        
        # Валидация стратегий перед сохранением
        options_json = user_data.options_json or "{}"
        validation_errors = validate_strategies(options_json)
        
        if validation_errors:
            error_message = "Ошибки валидации стратегий:\n" + "\n".join(f"• {error}" for error in validation_errors)
            logger.warning(
                f"Ошибки валидации стратегий для пользователя '{decoded_user}': {validation_errors}",
                extra={
                    "log_to_db": False,  # Ошибки валидации не критичны
                    "error_type": "strategy_validation_error",
                    "market": "api",
                    "symbol": f"settings/{decoded_user}",
                },
            )
            raise HTTPException(status_code=400, detail=error_message)
        
        user_id = await db.create_user(
            user=decoded_user,
            tg_token=user_data.tg_token or "",
            chat_id=user_data.chat_id or "",
            options_json=options_json
        )
        # Получаем точное имя пользователя из базы
        user_info = await db.get_user(decoded_user)
        canonical_user = user_info["user"] if user_info else decoded_user
        
        # Инвалидируем кэш детектора стрел, чтобы применить новые настройки сразу
        try:
            from core.spike_detector import spike_detector
            spike_detector.invalidate_cache()
            print(f"[Backend] Кэш детектора стрел сброшен после обновления настроек пользователя '{user}'")
        except Exception as cache_error:
            print(f"[Backend] Ошибка при сбросе кэша: {cache_error}")
        
        return {"id": user_id, "user": canonical_user, "message": "User created/updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users", response_model=dict)
async def get_all_users():
    """Получает всех пользователей"""
    try:
        users = await db.get_all_users()
        return {"users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ ====================
# ВАЖНО: Этот маршрут должен быть ПЕРЕД /api/users/{user}, иначе FastAPI будет интерпретировать "metrics" как имя пользователя

@app.get("/api/users/metrics", response_model=dict)
async def get_all_users_metrics():
    """Получает все настройки метрик для всех пользователей"""
    try:
        settings = await db.get_all_users_metrics_settings()
        return {"settings": settings}
    except Exception as e:
        logger.error(f"Ошибка при получении настроек метрик: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user}", response_model=Optional[UserResponse])
async def get_user(user: str):
    """Получает пользователя по имени"""
    try:
        # FastAPI автоматически декодирует URL параметры, но логируем для отладки
        print(f"[Backend] get_user called with user: '{user}' (type: {type(user)}, length: {len(user)})")
        print(f"[Backend] User bytes: {user.encode('utf-8')}")
        
        # Получаем всех пользователей для отладки
        all_users = await db.get_all_users()
        print(f"[Backend] All users in DB: {[u['user'] for u in all_users]}")
        
        user_data = await db.get_user(user)
        if not user_data:
            print(f"[Backend] User '{user}' not found in database")
            raise HTTPException(status_code=404, detail="User not found")
        
        print(f"[Backend] User found: {user_data['user']}, has tg_token: {bool(user_data.get('tg_token'))}, has chat_id: {bool(user_data.get('chat_id'))}, has options_json: {bool(user_data.get('options_json'))}")
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Backend] Error in get_user: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def _delete_user_internal(user: str):
    """Внутренняя функция для удаления пользователя (используется обоими маршрутами)"""
    # FastAPI автоматически декодирует параметры пути, но на случай двойного кодирования
    # пытаемся декодировать еще раз. Если уже декодировано, unquote вернет исходное значение
    try:
        decoded_user = unquote(user)
        # Если декодирование не изменило строку, значит она уже была декодирована
        if decoded_user == user:
            decoded_user = user
    except Exception:
        # Если ошибка декодирования, используем исходное значение
        decoded_user = user
    
    # Убираем лишние пробелы
    decoded_user = decoded_user.strip()
    
    if not decoded_user:
        raise HTTPException(status_code=400, detail="Имя пользователя не может быть пустым")
    
    # Логируем детальную информацию для отладки
    logger.info(f"Попытка удаления пользователя:")
    logger.info(f"  - Исходный параметр: '{user}' (type: {type(user)}, length: {len(user)})")
    logger.info(f"  - Декодированный: '{decoded_user}' (type: {type(decoded_user)}, length: {len(decoded_user)})")
    logger.info(f"  - Байты исходного: {user.encode('utf-8')}")
    logger.info(f"  - Байты декодированного: {decoded_user.encode('utf-8')}")
    
    if decoded_user.lower() in {"stats", "влад"}:
        raise HTTPException(status_code=403, detail=f"Пользователя '{decoded_user}' нельзя удалить")

    # Получаем user_id перед удалением для очистки данных трекера
    logger.info(f"Вызов db.get_user('{decoded_user}')...")
    user_data = await db.get_user(decoded_user)
    user_id = user_data.get("id") if user_data else None
    
    # Логируем результат поиска
    if user_data:
        logger.info(f"Пользователь найден в БД через get_user: id={user_id}, имя='{user_data.get('user')}'")
        logger.info(f"  - Сравнение: запрошено '{decoded_user}' vs найдено '{user_data.get('user')}'")
        logger.info(f"  - Совпадают: {decoded_user == user_data.get('user')}")
    else:
        logger.warning(f"Пользователь '{decoded_user}' не найден в БД через get_user")
        # Получаем всех пользователей для отладки
        all_users = await db.get_all_users()
        logger.warning(f"  - Доступные пользователи в БД: {[u['user'] for u in all_users]}")

    result = await db.delete_user(decoded_user)
    
    # Если пользователь не найден, возвращаем 404
    if not result["removed_from_users"]:
        logger.warning(f"Пользователь '{decoded_user}' не найден. Результат: {result}")
        raise HTTPException(
            status_code=404, 
            detail=f"Пользователь '{result['user']}' не найден"
        )
    
    # Очищаем данные трекера для удалённого пользователя
    if user_id and result.get("removed_from_users"):
        from core.spike_detector import spike_detector
        spike_detector.cleanup_user_data(user_id)
    
    message = f"Пользователь '{result['user']}' удалён"

    return {"message": message, **result}


@app.delete("/api/users/{user}")
async def delete_user(user: str):
    """Удаляет пользователя"""
    try:
        return await _delete_user_internal(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя {user}: {e}", exc_info=True, extra={
            "log_to_db": True,
            "error_type": "user_deletion_error",
            "market": "api",
            "symbol": f"/api/users/{user}",
        })
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/users/{user}/delete")
async def delete_user_with_delete_path(user: str):
    """Удаляет пользователя (альтернативный путь для совместимости с клиентом)"""
    try:
        return await _delete_user_internal(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя {user}: {e}", exc_info=True, extra={
            "log_to_db": True,
            "error_type": "user_deletion_error",
            "market": "api",
            "symbol": f"/api/users/{user}/delete",
        })
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/users/{user}/test")
async def test_telegram(user: str):
    """Отправляет тестовое сообщение в Telegram пользователю"""
    try:
        user_data = await db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        tg_token = user_data.get("tg_token", "")
        chat_id = user_data.get("chat_id", "")
        
        if not tg_token or not chat_id:
            raise HTTPException(
                status_code=400, 
                detail="Telegram bot token or chat ID not configured"
            )
        
        # Импортируем нотификатор
        from core.telegram_notifier import telegram_notifier
        
        # Отправляем тестовое сообщение
        success, error_message = await telegram_notifier.send_test_message(tg_token, chat_id)
        
        if success:
            return {"message": "Test message sent successfully"}
        else:
            # Возвращаем детальное сообщение об ошибке
            raise HTTPException(
                status_code=500,
                detail=error_message or "Failed to send test message to Telegram"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MetricsUpdateRequest(BaseModel):
    enabled: bool


@app.post("/api/users/{user}/metrics", response_model=dict)
async def update_user_metrics(user: str, request: MetricsUpdateRequest):
    """Обновляет настройку метрик производительности для пользователя"""
    try:
        # Получаем пользователя по имени
        user_data = await db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=404, detail="User ID not found")
        
        # Обновляем настройку метрик
        success = await db.set_user_metrics_enabled(user_id, request.enabled)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update metrics settings")
        
        return {
            "message": f"Metrics settings updated for user {user}",
            "user_id": user_id,
            "enabled": request.enabled
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обновлении настроек метрик для пользователя {user}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== СТРЕЛЫ (ALERTS) ====================

@app.post("/api/alerts", response_model=dict)
async def create_alert(alert: AlertCreate):
    """Создаёт новую стрелу"""
    try:
        alert_id = await db.add_alert(
            ts=alert.ts,
            exchange=alert.exchange,
            market=alert.market,
            symbol=alert.symbol,
            delta=alert.delta,
            wick_pct=alert.wick_pct,
            volume_usdt=alert.volume_usdt,
            meta=alert.meta,
            user_id=alert.user_id
        )
        return {"id": alert_id, "message": "Alert created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spikes", response_model=dict)
async def get_spikes(
    exchange: Optional[str] = None,
    market: Optional[str] = None,
    symbol: Optional[str] = None,
    user: Optional[str] = None,
    ts_from: Optional[int] = None,
    ts_to: Optional[int] = None,
    delta_min: Optional[float] = None,
    delta_max: Optional[float] = None,
    volume_min: Optional[float] = None,
    volume_max: Optional[float] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0
):
    """Получает стрелы с фильтрацией"""
    try:
        from core.symbol_utils import normalize_symbol, denormalize_symbol, is_normalized
        
        user_id = None
        if user:
            user_data = await db.get_user(user)
            if user_data:
                user_id = user_data["id"]
        
        # Если указан символ для фильтрации, проверяем, нужно ли денормализовать
        filter_symbol = symbol
        if symbol:
            # Если символ нормализован, получаем все варианты для фильтрации
            if is_normalized(symbol):
                # Получаем все варианты символа для всех бирж и рынков
                denormalized_symbols = []
                if exchange and market:
                    denormalized_symbols = await denormalize_symbol(symbol, exchange, market)
                else:
                    # Если биржа/рынок не указаны, получаем для всех
                    for ex in ["binance", "gate", "bitget", "bybit", "hyperliquid"]:
                        for mkt in ["spot", "linear"]:
                            denorm = await denormalize_symbol(symbol, ex, mkt)
                            denormalized_symbols.extend(denorm)
                
                # Если нашли варианты, используем их для фильтрации
                # Но для упрощения, если вариантов много, используем исходный символ
                # В реальности нужно будет изменить логику БД для поддержки IN запросов
                # Пока используем исходный символ, если он нормализован
                if not denormalized_symbols:
                    filter_symbol = None  # Не фильтруем, если не нашли варианты
        
        alerts = await db.get_alerts(
            exchange=exchange,
            market=market,
            symbol=filter_symbol,  # Используем оригинальный символ для фильтрации в БД
            user_id=user_id,
            ts_from=ts_from,
            ts_to=ts_to,
            delta_min=delta_min,
            delta_max=delta_max,
            volume_min=volume_min,
            volume_max=volume_max,
            limit=limit,
            offset=offset
        )
        
        # Используем оригинальный symbol для отображения (содержит полную информацию о паре)
        normalized_alerts = []
        for alert in alerts:
            alert_copy = dict(alert)
            # Используем оригинальный symbol для отображения (содержит полную информацию о паре)
            alert_copy["symbol"] = alert["symbol"]
            normalized_alerts.append(alert_copy)
        
        return {"spikes": normalized_alerts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spikes/stats", response_model=dict)
async def get_spikes_stats(
    exchange: Optional[str] = None,
    market: Optional[str] = None,
    user: Optional[str] = None,
    ts_from: Optional[int] = None,
    ts_to: Optional[int] = None
):
    """Получает статистику по стрелам"""
    try:
        user_id = None
        if user:
            user_data = await db.get_user(user)
            if user_data:
                user_id = user_data["id"]
        
        count = await db.get_alerts_count(
            exchange=exchange,
            market=market,
            user_id=user_id,
            ts_from=ts_from,
            ts_to=ts_to
        )
        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user}/spikes/stats", response_model=dict)
async def get_user_spikes_stats(
    user: str,
    exchange: Optional[str] = None,
    market: Optional[str] = None,
    ts_from: Optional[int] = None,
    ts_to: Optional[int] = None,
    days: Optional[int] = 30
):
    """Получает подробную статистику по стрелам конкретного пользователя"""
    try:
        user_data = await db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Получаем стрелы для конкретного пользователя (включая "Stats")
        # Общая статистика показывает только стрелы, пойманные фильтрами пользователя "Stats"
        user_id = user_data["id"]
        
        # Получаем все стрелы пользователя за указанный период (по умолчанию 30 дней)
        if ts_from is None:
            import time
            days_value = days if days and days > 0 else 30
            ts_from = int((time.time() - days_value * 24 * 60 * 60) * 1000)
        
        # Получаем все стрелы для статистики (без лимита)
        alerts = await db.get_alerts(
            exchange=exchange,
            market=market,
            user_id=user_id,
            ts_from=ts_from,
            ts_to=ts_to
            # limit не указываем - получаем все записи
        )
        
        if not alerts:
            result = {
                "total_count": 0,
                "avg_delta": 0,
                "avg_volume": 0,
                "total_volume": 0,
                "chart_data": [],
                "by_exchange": {},
                "by_market": {},
                "top_symbols": [],
                "top_by_delta": [],
                "top_by_volume": [],
                "spikes": []
            }
            return result
        
        # Вычисляем статистику
        total_count = len(alerts)
        total_delta = sum(a["delta"] for a in alerts)
        avg_delta = total_delta / total_count if total_count > 0 else 0
        
        total_volume = sum(a["volume_usdt"] for a in alerts)
        avg_volume = total_volume / total_count if total_count > 0 else 0
        
        # Группировка по биржам
        by_exchange = {}
        for alert in alerts:
            ex = alert["exchange"]
            by_exchange[ex] = by_exchange.get(ex, 0) + 1
        
        # Группировка по рынкам
        by_market = {}
        for alert in alerts:
            mkt = alert["market"]
            by_market[mkt] = by_market.get(mkt, 0) + 1
        
        # Топ символов (используем normalized_symbol из БД)
        symbol_counts = {}
        for alert in alerts:
            # Используем normalized_symbol из БД (уже нормализован при записи)
            normalized_sym = alert.get("normalized_symbol") or alert["symbol"]
            symbol_counts[normalized_sym] = symbol_counts.get(normalized_sym, 0) + 1
        
        top_symbols = sorted(
            [{"symbol": sym, "count": cnt} for sym, cnt in symbol_counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]
        
        # График по дням
        from collections import defaultdict
        from datetime import datetime
        daily_counts = defaultdict(int)
        
        for alert in alerts:
            # ts в миллисекундах, конвертируем в дату
            date = datetime.fromtimestamp(alert["ts"] / 1000).strftime("%Y-%m-%d")
            daily_counts[date] += 1
        
        chart_data = sorted(
            [{"date": date, "count": count} for date, count in daily_counts.items()],
            key=lambda x: x["date"]
        )
        
        # Последние 20 стрел для таблицы (используем оригинальный symbol для отображения)
        recent_spikes_raw = sorted(alerts, key=lambda x: x["ts"], reverse=True)[:20]
        recent_spikes = []
        for alert in recent_spikes_raw:
            alert_copy = dict(alert)
            # Используем оригинальный symbol для отображения (содержит полную информацию о паре)
            alert_copy["symbol"] = alert["symbol"]
            recent_spikes.append(alert_copy)
        
        # Топ 10 стрел по дельте (абсолютное значение) (используем оригинальный symbol для отображения)
        top_by_delta_raw = sorted(
            alerts,
            key=lambda x: abs(x["delta"]),
            reverse=True
        )[:10]
        top_by_delta = []
        for alert in top_by_delta_raw:
            alert_copy = dict(alert)
            # Используем оригинальный symbol для отображения (содержит полную информацию о паре)
            alert_copy["symbol"] = alert["symbol"]
            top_by_delta.append(alert_copy)
        
        # Топ 10 стрел по объёму (используем оригинальный symbol для отображения)
        top_by_volume_raw = sorted(
            alerts,
            key=lambda x: x["volume_usdt"],
            reverse=True
        )[:10]
        top_by_volume = []
        for alert in top_by_volume_raw:
            alert_copy = dict(alert)
            # Используем оригинальный symbol для отображения (содержит полную информацию о паре)
            alert_copy["symbol"] = alert["symbol"]
            top_by_volume.append(alert_copy)
        
        # Группировка по месяцам
        monthly_counts = defaultdict(int)
        for alert in alerts:
            date = datetime.fromtimestamp(alert["ts"] / 1000)
            month_key = date.strftime("%Y-%m")
            monthly_counts[month_key] += 1
        
        monthly_data = sorted(
            [{"month": month, "count": count} for month, count in monthly_counts.items()],
            key=lambda x: x["month"]
        )
        
        result = {
            "total_count": total_count,
            "avg_delta": avg_delta,
            "avg_volume": avg_volume,
            "total_volume": total_volume,
            "chart_data": chart_data,
            "monthly_data": monthly_data,
            "by_exchange": by_exchange,
            "by_market": by_market,
            "top_symbols": top_symbols,
            "top_by_delta": top_by_delta,
            "top_by_volume": top_by_volume,
            "spikes": recent_spikes
        }
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user}/spikes/by-symbol/{symbol}", response_model=dict)
async def get_user_spikes_by_symbol(
    user: str,
    symbol: str,
    exchange: Optional[str] = None,
    market: Optional[str] = None,
    ts_from: Optional[int] = None,
    ts_to: Optional[int] = None
):
    """Получает все стрелы пользователя по конкретной монете"""
    try:
        from core.symbol_utils import normalize_symbol, denormalize_symbol, is_normalized
        
        logger.info(f"Запрос сигналов по символу: user={user}, symbol={symbol}, exchange={exchange}, market={market}")
        
        user_data = await db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_data["id"]
        
        # Если символ нормализован, получаем все варианты для фильтрации
        filter_symbols = [symbol]
        normalized_symbol = symbol
        
        if is_normalized(symbol):
            # Символ уже нормализован, используем его для ответа
            normalized_symbol = symbol
            # Получаем все варианты для фильтрации
            if exchange and market:
                denormalized = await denormalize_symbol(symbol, exchange, market)
                if denormalized:
                    filter_symbols = denormalized
            else:
                # Если биржа/рынок не указаны, получаем для всех
                for ex in ["binance", "gate", "bitget", "bybit", "hyperliquid"]:
                    for mkt in ["spot", "linear"]:
                        denorm = await denormalize_symbol(symbol, ex, mkt)
                        filter_symbols.extend(denorm)
        else:
            # Символ не нормализован, нормализуем для ответа
            # Для фильтрации используем исходный символ
            if exchange and market:
                normalized_symbol = await normalize_symbol(symbol, exchange, market)
            else:
                # Если биржа/рынок не указаны, пробуем нормализовать для первой найденной биржи
                normalized_symbol = await normalize_symbol(symbol, "binance", "spot")
        
        # Получаем все стрелы пользователя по нормализованному символу
        # Используем прямой SQL запрос, чтобы фильтровать по normalized_symbol
        from pathlib import Path
        # Путь к БД относительно api_server.py
        db_path = Path(__file__).parent / "BD" / "detected_alerts.db"
        conn = await aiosqlite.connect(str(db_path))
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
            
            # Фильтруем по normalized_symbol
            conditions.append("a.normalized_symbol = ?")
            params.append(normalized_symbol.upper())
            
            # Условия для фильтрации по полям alerts
            if exchange:
                conditions.append("a.exchange = ?")
                params.append(exchange)
            if market:
                conditions.append("a.market = ?")
                params.append(market)
            if ts_from is not None:
                conditions.append("a.ts >= ?")
                params.append(ts_from)
            if ts_to is not None:
                conditions.append("a.ts <= ?")
                params.append(ts_to)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Формируем SELECT с JOIN
            if user_id is not None:
                select_clause = """
                    SELECT a.id, a.ts, a.exchange, a.market, a.symbol, a.normalized_symbol, a.delta, 
                           a.wick_pct, a.volume_usdt, a.meta, a.created_at,
                           ua.user_id
                    FROM alerts a
                """
            else:
                select_clause = """
                    SELECT a.id, a.ts, a.exchange, a.market, a.symbol, a.normalized_symbol, a.delta, 
                           a.wick_pct, a.volume_usdt, a.meta, a.created_at,
                           NULL as user_id
                    FROM alerts a
                """
            
            query = f"{select_clause} {join_clause} {where_clause} ORDER BY a.ts DESC"
            
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            
            # Конвертируем в список словарей
            unique_alerts = []
            for row in rows:
                alert = {
                    "id": row[0],
                    "ts": row[1],
                    "exchange": row[2],
                    "market": row[3],
                    "symbol": row[4],
                    "normalized_symbol": row[5],
                    "delta": row[6],
                    "wick_pct": row[7],
                    "volume_usdt": row[8],
                    "meta": row[9],
                    "created_at": row[10],
                    "user_id": row[11] if len(row) > 11 else None
                }
                unique_alerts.append(alert)
            
            logger.info(f"Найдено сигналов для символа {normalized_symbol}: {len(unique_alerts)}")
        finally:
            await conn.close()
        
        # Используем оригинальный symbol для отображения (содержит полную информацию о паре)
        normalized_alerts = []
        for alert in unique_alerts:
            alert_copy = dict(alert)
            # Используем оригинальный symbol для отображения (содержит полную информацию о паре)
            alert_copy["symbol"] = alert["symbol"]
            normalized_alerts.append(alert_copy)
        
        # Сортируем по времени (новые первыми)
        normalized_alerts = sorted(normalized_alerts, key=lambda x: x["ts"], reverse=True)
        
        logger.info(f"Возвращаем {len(normalized_alerts)} сигналов для символа {normalized_symbol}")
        
        return {
            "symbol": normalized_symbol,
            "total_count": len(normalized_alerts),
            "spikes": normalized_alerts
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/users/{user}/spikes", response_model=dict)
async def delete_user_spikes(user: str):
    """Удаляет всю статистику стрел пользователя"""
    try:
        user_data = await db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Удаляем все связи пользователя со стрелами (для всех пользователей, включая "Stats")
        deleted_count = await db.delete_user_spikes(user)
        return {
            "message": f"Удалено {deleted_count} записей статистики стрел для пользователя '{user}'",
            "deleted_count": deleted_count
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ОШИБКИ ====================

def convert_timestamp_to_utc_iso(timestamp_str: str) -> str:
    """
    Преобразует timestamp из локального времени сервера (Europe/Chisinau, UTC+2/UTC+3)
    в UTC и возвращает в ISO 8601 формате.
    
    Args:
        timestamp_str: Timestamp в формате SQLite "YYYY-MM-DD HH:MM:SS" или ISO 8601
        
    Returns:
        ISO 8601 строка с UTC часовым поясом (например, "2025-12-02T09:46:34+00:00")
    """
    if not timestamp_str:
        return timestamp_str
    
    try:
        # Если уже в ISO формате с часовым поясом, возвращаем как есть
        if 'T' in timestamp_str and ('Z' in timestamp_str or '+' in timestamp_str or 
                                     (timestamp_str.count('-') > 2 and ':' in timestamp_str[-6:])):
            # Парсим ISO формат
            if timestamp_str.endswith('Z'):
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(timestamp_str)
            # Конвертируем в UTC
            if dt.tzinfo is None:
                # Если нет часового пояса, предполагаем что это UTC
                dt = pytz.UTC.localize(dt)
            else:
                dt = dt.astimezone(pytz.UTC)
            return dt.isoformat()
        else:
            # SQLite формат "YYYY-MM-DD HH:MM:SS" - предполагаем что это локальное время сервера
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            # Локализуем в часовой пояс сервера (Europe/Chisinau)
            server_tz = pytz.timezone('Europe/Chisinau')
            dt_local = server_tz.localize(dt)
            # Конвертируем в UTC
            dt_utc = dt_local.astimezone(pytz.UTC)
            return dt_utc.isoformat()
    except (ValueError, AttributeError) as e:
        logger.debug(f"Не удалось преобразовать timestamp '{timestamp_str}': {e}")
        # Если не удалось распарсить, возвращаем как есть
        return timestamp_str


@app.post("/api/errors")
async def create_error(error: ErrorCreate):
    """Логирует ошибку"""
    try:
        await db.add_error(
            error_type=error.error_type,
            error_message=error.error_message,
            exchange=error.exchange,
            connection_id=error.connection_id,
            market=error.market,
            symbol=error.symbol,
            stack_trace=error.stack_trace
        )
        return {"message": "Error logged successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/errors", response_model=dict)
async def get_errors(
    exchange: Optional[str] = None,
    error_type: Optional[str] = None,
    limit: Optional[int] = 100
):
    """Получает ошибки"""
    try:
        errors = await db.get_errors(
            exchange=exchange,
            error_type=error_type,
            limit=limit
        )
        
        # Преобразуем timestamp в ISO 8601 формат с UTC для правильного отображения в веб-интерфейсе
        for error in errors:
            if error.get('timestamp'):
                error['timestamp'] = convert_timestamp_to_utc_iso(error['timestamp'])
        
        return {"errors": errors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/errors/{error_id}")
async def delete_error(error_id: int, user: Optional[str] = Query(None)):
    """Удаляет ошибку по ID (только для пользователя 'Влад')"""
    try:
        # Проверяем, что пользователь - "Влад"
        if not user or user.lower() != "влад":
            raise HTTPException(
                status_code=403, 
                detail="Удаление логов ошибок доступно только для пользователя 'Влад'"
            )
        
        deleted = await db.delete_error(error_id)
        if deleted:
            return {"message": f"Ошибка с ID {error_id} удалена", "deleted": True}
        else:
            raise HTTPException(status_code=404, detail=f"Ошибка с ID {error_id} не найдена")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/errors")
async def delete_all_errors(user: Optional[str] = Query(None)):
    """Удаляет все ошибки (только для пользователя 'Влад')"""
    try:
        # Проверяем, что пользователь - "Влад"
        if not user or user.lower() != "влад":
            raise HTTPException(
                status_code=403, 
                detail="Удаление всех логов ошибок доступно только для пользователя 'Влад'"
            )
        
        count = await db.delete_all_errors()
        return {"message": f"Удалено ошибок: {count}", "deleted_count": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ЗДОРОВЬЕ СИСТЕМЫ ====================

@app.get("/api/health")
async def health_check():
    """Проверка здоровья API"""
    return {"ok": True, "timestamp": int(time.time() * 1000)}


@app.get("/api/status")
async def get_status():
    """Получает статус системы"""
    try:
        users_count = len(await db.get_all_users())
        
        # Получаем время запуска main.py
        main_start_time = get_main_start_time()
        
        # Если main.py не запущен, возвращаем None для uptime и start_time
        if main_start_time is None:
            # Получаем общее количество детектов
            total_alerts = await db.get_alerts_count()
            
            return {
                "users": users_count,
                "total_alerts": total_alerts,
                "alerts_since_start": 0,  # Нет детектов, так как main.py не запущен
                "uptime_seconds": None,  # None означает, что main.py не запущен
                "start_time": None,  # None означает, что main.py не запущен
                "start_datetime": None,  # None означает, что main.py не запущен
                "status": "running"
            }
        
        # Вычисляем uptime как время работы main.py
        uptime_seconds = int(time.time() - main_start_time)
        
        # Конвертируем время запуска в формат TIMESTAMP для SQL
        from datetime import datetime
        start_datetime = datetime.fromtimestamp(main_start_time)
        start_timestamp_str = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
        
        # Получаем количество детектов только с момента запуска main.py
        alerts_since_start = await db.get_alerts_count(created_after=start_timestamp_str)
        
        # Получаем общее количество детектов (для обратной совместимости)
        total_alerts = await db.get_alerts_count()
        
        return {
            "users": users_count,
            "total_alerts": total_alerts,  # Все детекты (для обратной совместимости)
            "alerts_since_start": alerts_since_start,  # Детекты с момента запуска main.py
            "uptime_seconds": uptime_seconds,
            "start_time": main_start_time,  # Unix timestamp времени запуска main.py
            "start_datetime": start_timestamp_str,  # Время запуска в читаемом формате
            "status": "running"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics")
async def get_metrics():
    """Получает метрики системы"""
    try:
        users_count = len(await db.get_all_users())
        total_alerts = await db.get_alerts_count()
        
        # Получаем статистику бирж из новой таблицы
        exchange_stats = await db.get_exchange_statistics()
        
        # Форматируем статистику для удобного доступа
        stats_by_exchange = {}
        for stat in exchange_stats:
            exchange = stat["exchange"]
            market = stat["market"]
            
            if exchange not in stats_by_exchange:
                stats_by_exchange[exchange] = {}
            
            stats_by_exchange[exchange][market] = {
                "symbols_count": stat["symbols_count"],
                "ws_connections": stat["ws_connections"],
                "batches_per_ws": stat["batches_per_ws"],
                "reconnects": stat["reconnects"],
                "candles_count": stat["candles_count"],
                "last_candle_time": stat["last_candle_time"],
                "ticks_per_second": stat["ticks_per_second"],
                "updated_at": stat["updated_at"]
            }
        
        return {
            "metrics": {
                "users": users_count,
                "alerts": total_alerts,
                "timestamp": int(time.time() * 1000)
            },
            "exchange_statistics": stats_by_exchange
        }
    except Exception as e:
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


def get_exchange_limits() -> dict:
    """
    Получает лимиты символов/стримов на одно WebSocket-соединение для каждой биржи.
    Импортирует актуальные значения из ws_handler модулей.
    """
    limits = {}
    
    try:
        # Binance
        from exchanges.binance.ws_handler import STREAMS_PER_CONNECTION
        limits["binance"] = {
            "spot": STREAMS_PER_CONNECTION,
            "linear": STREAMS_PER_CONNECTION
        }
    except ImportError:
        logger.warning("Не удалось импортировать лимиты для Binance")
    
    try:
        # Gate.io
        from exchanges.gate.ws_handler import SPOT_SYMBOLS_PER_CONNECTION, LINEAR_SYMBOLS_PER_CONNECTION
        limits["gate"] = {
            "spot": SPOT_SYMBOLS_PER_CONNECTION,
            "linear": LINEAR_SYMBOLS_PER_CONNECTION
        }
    except ImportError:
        logger.warning("Не удалось импортировать лимиты для Gate.io")
    
    try:
        # Bybit
        from exchanges.bybit.ws_handler import WS_SYMBOLS_PER_CONNECTION_SPOT, WS_SYMBOLS_PER_CONNECTION_LINEAR
        limits["bybit"] = {
            "spot": WS_SYMBOLS_PER_CONNECTION_SPOT,
            "linear": WS_SYMBOLS_PER_CONNECTION_LINEAR
        }
    except ImportError:
        logger.warning("Не удалось импортировать лимиты для Bybit")
    
    try:
        # Bitget
        from exchanges.bitget.ws_handler import BATCH_SIZE, FUT_BATCH_SIZE
        limits["bitget"] = {
            "spot": BATCH_SIZE,
            "linear": FUT_BATCH_SIZE
        }
    except ImportError:
        logger.warning("Не удалось импортировать лимиты для Bitget")
    
    try:
        # Hyperliquid
        from exchanges.hyperliquid.ws_handler import SPOT_SYMBOLS_PER_CONNECTION, LINEAR_SYMBOLS_PER_CONNECTION
        limits["hyperliquid"] = {
            "spot": SPOT_SYMBOLS_PER_CONNECTION,
            "linear": LINEAR_SYMBOLS_PER_CONNECTION
        }
    except ImportError:
        logger.warning("Не удалось импортировать лимиты для Hyperliquid")
    
    return limits


@app.get("/api/exchanges/stats")
async def get_exchanges_stats():
    """Получает статистику бирж"""
    try:
        # Получаем статистику бирж из новой таблицы
        exchange_stats = await db.get_exchange_statistics()
        
        # Получаем актуальные лимиты из ws_handler модулей
        exchange_limits = get_exchange_limits()
        
        # Форматируем статистику в формате, который ожидает dashboard
        exchanges_data = {}
        for stat in exchange_stats:
            exchange = stat["exchange"]
            market = stat["market"]
            
            if exchange not in exchanges_data:
                exchanges_data[exchange] = {}
            
            exchanges_data[exchange][market] = {
                "active_connections": stat["ws_connections"],
                "active_symbols": stat["symbols_count"],
                "reconnects": stat["reconnects"],
                "candles": stat["candles_count"],
                "batches_per_ws": stat["batches_per_ws"],
                "last_candle_time": stat["last_candle_time"],
                "ticks_per_second": stat["ticks_per_second"],
                "updated_at": stat["updated_at"]
            }
        
        return {
            "exchanges": exchanges_data,
            "limits": exchange_limits  # Также возвращаем отдельно для удобства
        }
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

