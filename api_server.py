"""
FastAPI сервер для работы с базой данных и предоставления API
"""
import traceback
import os
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from BD.database import db
import time
from core.logger import get_logger, setup_root_logger

setup_root_logger("INFO")
logger = get_logger(__name__)

app = FastAPI(title="Crypto Spikes API", version="1.0.0")

# Время запуска API сервера для расчета uptime
_start_time = time.time()

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


@app.middleware("http")
async def log_api_errors(request: Request, call_next):
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
    except HTTPException as exc:
        if exc.status_code >= 500:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            logger.error(
                f"HTTPException {exc.status_code} на {request.method} {request.url.path}: {detail}",
                extra={
                    "log_to_db": True,
                    "error_type": "api_exception",
                    "market": "api",
                    "symbol": request.url.path,
                    "stack_trace": detail,
                },
            )
        raise
    except Exception as exc:
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


class WhitelistEntry(BaseModel):
    username: str


# ==================== ПОЛЬЗОВАТЕЛИ ====================

@app.post("/api/auth/register/{user}", response_model=dict)
async def register_user(user: str, user_data: UserRegister):
    """Регистрирует нового пользователя"""
    try:
        if len(user_data.password) < 4:
            raise HTTPException(status_code=400, detail="Пароль должен быть не менее 4 символов")

        canonical_user = db.get_whitelisted_username(user)
        if not canonical_user:
            raise HTTPException(status_code=403, detail="Логин не одобрен администратором. Обратитесь к Владу.")
        
        user_id = db.register_user(
            user=canonical_user,
            password=user_data.password,
            tg_token=user_data.tg_token or "",
            chat_id=user_data.chat_id or "",
            options_json=user_data.options_json or "{}"
        )
        return {"id": user_id, "user": canonical_user, "message": "User registered successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/login/{user}", response_model=dict)
async def login_user(user: str, login_data: UserLogin):
    """
    Аутентифицирует пользователя
    
    Основная логика: проверка пароля и возврат существующих данных.
    Дополнительно при наличии информации о временной зоне обновляет её в профиле.
    """
    try:
        # Проверяем, что пароль не пустой
        if not login_data.password or len(login_data.password.strip()) == 0:
            raise HTTPException(status_code=400, detail="Пароль не может быть пустым")
        
        # ТОЛЬКО проверка пароля и чтение данных - никаких обновлений
        user_data = db.authenticate_user(user, login_data.password)
        if not user_data:
            # Пользователь не найден или пароль неверный
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")

        canonical_user = user_data["user"]
        
        # Обновляем временную зону, если пришла от клиента
        if login_data.timezone:
            try:
                db.update_user_timezone(
                    user=canonical_user,
                    timezone=login_data.timezone,
                    timezone_offset_minutes=login_data.timezone_offset_minutes,
                    timezone_offset_formatted=login_data.timezone_offset_formatted,
                    timezone_client_locale=login_data.timezone_client_locale,
                    source="login_auto_detect",
                )
            except Exception as tz_error:
                # Не прерываем вход, но логируем ошибку
                print(f"[Backend] Не удалось обновить временную зону пользователя '{user}': {tz_error}")
        
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/whitelist", response_model=dict)
async def get_whitelist():
    """Возвращает текущий белый список логинов"""
    try:
        whitelist = db.get_whitelist()
        return {"whitelist": whitelist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/whitelist", response_model=dict)
async def add_to_whitelist(entry: WhitelistEntry):
    """Добавляет логин в белый список"""
    try:
        username = entry.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="Логин не может быть пустым")

        canonical = db.add_login_to_whitelist(username)
        return {"username": canonical, "message": f"Логин '{canonical}' добавлен в белый список"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/auth/whitelist/{username}", response_model=dict)
async def remove_from_whitelist(username: str):
    """Удаляет логин из белого списка"""
    try:
        if not username:
            raise HTTPException(status_code=400, detail="Не указан логин для удаления")

        canonical = db.get_whitelisted_username(username)
        if not canonical:
            raise HTTPException(status_code=404, detail="Логин не найден в белом списке")

        removed = db.remove_login_from_whitelist(canonical)
        if not removed:
            raise HTTPException(status_code=500, detail="Не удалось удалить логин из белого списка")
        return {"message": f"Логин '{canonical}' удалён из белого списка"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/users/{user}/settings", response_model=dict)
async def create_or_update_user(user: str, user_data: UserCreate):
    """Создаёт или обновляет пользователя"""
    try:
        user_id = db.create_user(
            user=user,
            tg_token=user_data.tg_token or "",
            chat_id=user_data.chat_id or "",
            options_json=user_data.options_json or "{}"
        )
        canonical_user = db.get_whitelisted_username(user) or user.strip()
        
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
        users = db.get_all_users()
        return {"users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user}", response_model=Optional[UserResponse])
async def get_user(user: str):
    """Получает пользователя по имени"""
    try:
        # FastAPI автоматически декодирует URL параметры, но логируем для отладки
        print(f"[Backend] get_user called with user: '{user}' (type: {type(user)}, length: {len(user)})")
        print(f"[Backend] User bytes: {user.encode('utf-8')}")
        
        # Получаем всех пользователей для отладки
        all_users = db.get_all_users()
        print(f"[Backend] All users in DB: {[u['user'] for u in all_users]}")
        
        user_data = db.get_user(user)
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


@app.delete("/api/users/{user}")
async def delete_user(user: str):
    """Удаляет пользователя"""
    try:
        if user.lower() in {"stats", "влад"}:
            raise HTTPException(status_code=403, detail=f"Пользователя '{user}' нельзя удалить")

        result = db.delete_user(user)
        if result["removed_from_users"] and result["removed_from_whitelist"]:
            message = f"Пользователь '{result['user']}' удалён и исключён из белого списка"
        elif result["removed_from_users"]:
            message = f"Пользователь '{result['user']}' удалён, но в белом списке не найден"
        elif result["removed_from_whitelist"]:
            message = f"Логин '{result['user']}' удалён из белого списка"
        else:
            message = f"Пользователь '{result['user']}' не найден"

        return {"message": message, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/users/{user}/test")
async def test_telegram(user: str):
    """Отправляет тестовое сообщение в Telegram пользователю"""
    try:
        user_data = db.get_user(user)
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


# ==================== СТРЕЛЫ (ALERTS) ====================

@app.post("/api/alerts", response_model=dict)
async def create_alert(alert: AlertCreate):
    """Создаёт новую стрелу"""
    try:
        alert_id = db.add_alert(
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
        user_id = None
        if user:
            user_data = db.get_user(user)
            if user_data:
                user_id = user_data["id"]
        
        alerts = db.get_alerts(
            exchange=exchange,
            market=market,
            symbol=symbol,
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
        return {"spikes": alerts}
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
            user_data = db.get_user(user)
            if user_data:
                user_id = user_data["id"]
        
        count = db.get_alerts_count(
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
        user_data = db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Для пользователя "Stats" получаем все стрелы без фильтрации по user_id
        # Для остальных пользователей - только их стрелы
        is_stats_user = user.lower() == "stats"
        user_id = None if is_stats_user else user_data["id"]
        
        # Получаем все стрелы пользователя за указанный период (по умолчанию 30 дней)
        if ts_from is None:
            import time
            days_value = days if days and days > 0 else 30
            ts_from = int((time.time() - days_value * 24 * 60 * 60) * 1000)
        
        # Получаем все стрелы для статистики (без лимита)
        alerts = db.get_alerts(
            exchange=exchange,
            market=market,
            user_id=user_id,
            ts_from=ts_from,
            ts_to=ts_to
            # limit не указываем - получаем все записи
        )
        
        if not alerts:
            return {
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
        
        # Топ символов
        symbol_counts = {}
        for alert in alerts:
            sym = alert["symbol"]
            symbol_counts[sym] = symbol_counts.get(sym, 0) + 1
        
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
        
        # Последние 20 стрел для таблицы
        recent_spikes = sorted(alerts, key=lambda x: x["ts"], reverse=True)[:20]
        
        # Топ 10 стрел по дельте (абсолютное значение)
        top_by_delta = sorted(
            alerts,
            key=lambda x: abs(x["delta"]),
            reverse=True
        )[:10]
        
        # Топ 10 стрел по объёму
        top_by_volume = sorted(
            alerts,
            key=lambda x: x["volume_usdt"],
            reverse=True
        )[:10]
        
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
        
        return {
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
        user_data = db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_data["id"]
        
        # Получаем все стрелы пользователя по символу
        alerts = db.get_alerts(
            exchange=exchange,
            market=market,
            symbol=symbol,
            user_id=user_id,
            ts_from=ts_from,
            ts_to=ts_to
        )
        
        # Сортируем по времени (новые первыми)
        alerts = sorted(alerts, key=lambda x: x["ts"], reverse=True)
        
        return {
            "symbol": symbol,
            "total_count": len(alerts),
            "spikes": alerts
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/users/{user}/spikes", response_model=dict)
async def delete_user_spikes(user: str):
    """Удаляет всю статистику стрел пользователя"""
    try:
        user_data = db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        deleted_count = db.delete_user_spikes(user)
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

@app.post("/api/errors")
async def create_error(error: ErrorCreate):
    """Логирует ошибку"""
    try:
        db.add_error(
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
        errors = db.get_errors(
            exchange=exchange,
            error_type=error_type,
            limit=limit
        )
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
        
        deleted = db.delete_error(error_id)
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
        
        count = db.delete_all_errors()
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
        users_count = len(db.get_all_users())
        total_alerts = db.get_alerts_count()
        # Вычисляем uptime как время работы API сервера
        uptime_seconds = int(time.time() - _start_time)
        return {
            "users": users_count,
            "total_alerts": total_alerts,
            "uptime_seconds": uptime_seconds,
            "status": "running"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics")
async def get_metrics():
    """Получает метрики системы"""
    try:
        users_count = len(db.get_all_users())
        total_alerts = db.get_alerts_count()
        
        # Получаем статистику бирж из новой таблицы
        exchange_stats = db.get_exchange_statistics()
        
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


@app.get("/api/exchanges/stats")
async def get_exchanges_stats():
    """Получает статистику бирж"""
    try:
        # Получаем статистику бирж из новой таблицы
        exchange_stats = db.get_exchange_statistics()
        
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
            "exchanges": exchanges_data
        }
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

