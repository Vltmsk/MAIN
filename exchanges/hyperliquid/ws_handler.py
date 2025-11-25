"""
WebSocket обработчик для Hyperliquid
"""
import ssl
import certifi
import asyncio
import math
import re
import time
from typing import Awaitable, Callable, List
from collections import deque
import aiohttp
import json
import socket
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from .symbol_fetcher import fetch_symbols

logger = get_logger(__name__)

# Hyperliquid WebSocket endpoint
HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"

# Лимиты Hyperliquid API
MAX_WEBSOCKET_CONNECTIONS = 100  # Максимум 100 websocket соединений
MAX_WEBSOCKET_SUBSCRIPTIONS = 1000  # Максимум 1000 websocket подписок
MAX_MESSAGES_PER_MINUTE = 2000  # Максимум 2000 сообщений в минуту
MAX_INFLIGHT_POST_MESSAGES = 100  # Максимум 100 одновременных inflight post сообщений

# Конфигурация подключения
# Количество символов на одно WS-соединение для спота и перпов.
SPOT_SYMBOLS_PER_CONNECTION = 50
LINEAR_SYMBOLS_PER_CONNECTION = 50
PING_INTERVAL_SEC = 55
RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60

# Пороги предупреждений (в процентах от лимита)
WARNING_THRESHOLD = 0.8  # 80% от лимита

# Глобальные переменные
_builder: CandleBuilder | None = None
_tasks: List[asyncio.Task] = []
_spot_tasks: List[asyncio.Task] = []
_linear_tasks: List[asyncio.Task] = []
_session: aiohttp.ClientSession | None = None
_stats = {
    "spot": {
        "active_connections": 0,
        "active_symbols": 0,
        "reconnects": 0,
        "total_subscriptions": 0,
    },
    "linear": {
        "active_connections": 0,
        "active_symbols": 0,
        "reconnects": 0,
        "total_subscriptions": 0,
    },
}

# Rate limiting для сообщений
_message_timestamps: deque = deque()  # Хранит timestamps отправленных сообщений
_rate_limit_lock = asyncio.Lock()  # Блокировка для thread-safe доступа


def _parse_float(x) -> float:
    """Безопасное преобразование в float."""
    try:
        return float(x)
    except Exception:
        return 0.0


async def _check_rate_limit(is_ping: bool = False) -> None:
    """
    Проверяет и применяет rate limiting для сообщений.
    Удаляет старые timestamps (старше 1 минуты) и ждёт, если лимит превышен.
    
    Использует цикл для повторной проверки лимита после ожидания, чтобы предотвратить
    превышение лимита, когда несколько корутин одновременно ждут и просыпаются.
    
    Args:
        is_ping: Если True, ping сообщения обходят rate limiting (критично для соединения)
    """
    global _message_timestamps
    
    # Ping сообщения обходят rate limiting, так как они критичны для поддержания соединения
    if is_ping:
        # Ping сообщения НЕ учитываются в rate limit, но очищаем старые timestamps
        # для предотвращения утечки памяти
        async with _rate_limit_lock:
            current_time = time.time()
            minute_ago = current_time - 60
            
            # Удаляем timestamps старше 1 минуты (для предотвращения утечки памяти)
            while _message_timestamps and _message_timestamps[0] < minute_ago:
                _message_timestamps.popleft()
            
            # НЕ добавляем timestamp для ping - они обходят rate limiting полностью
        return
    
    # Используем цикл для повторной проверки лимита после ожидания
    while True:
        wait_time = 0.0
        message_count = 0  # Сохраняем количество для логирования
        async with _rate_limit_lock:
            current_time = time.time()
            minute_ago = current_time - 60
            
            # Удаляем timestamps старше 1 минуты
            while _message_timestamps and _message_timestamps[0] < minute_ago:
                _message_timestamps.popleft()
            
            # Сохраняем текущее количество для логирования (внутри блокировки)
            message_count = len(_message_timestamps)
            
            # Проверяем лимит после очистки старых timestamps
            if message_count < MAX_MESSAGES_PER_MINUTE:
                # Есть место - добавляем timestamp и выходим
                _message_timestamps.append(current_time)
                return
            
            # Лимит всё ещё достигнут - вычисляем время ожидания
            if _message_timestamps:
                oldest_timestamp = _message_timestamps[0]
                wait_time = 60 - (current_time - oldest_timestamp) + 0.1  # +0.1 для безопасности
            else:
                # Если список пуст после очистки (не должно быть), просто добавляем
                _message_timestamps.append(current_time)
                return
        
        # Ожидание выполняется ВНЕ блокировки, чтобы не блокировать другие корутины
        if wait_time > 0:
            logger.warning(
                f"Rate limit достигнут ({message_count}/{MAX_MESSAGES_PER_MINUTE} сообщений/мин). "
                f"Ожидание {wait_time:.2f} секунд..."
            )
            await asyncio.sleep(wait_time)
            # После ожидания цикл продолжится и повторит проверку лимита
        else:
            # Если wait_time = 0, выходим (не должно происходить в нормальных условиях)
            break


def _check_limits_warning(connections: int, subscriptions: int) -> None:
    """
    Проверяет приближение к лимитам и выводит предупреждения.
    
    Args:
        connections: Текущее количество соединений
        subscriptions: Текущее количество подписок
    """
    # Проверка лимита соединений
    if connections >= MAX_WEBSOCKET_CONNECTIONS * WARNING_THRESHOLD:
        logger.warning(
            f"⚠️ Приближение к лимиту соединений Hyperliquid: {connections}/{MAX_WEBSOCKET_CONNECTIONS} "
            f"({connections/MAX_WEBSOCKET_CONNECTIONS*100:.1f}%)"
        )
    
    if connections >= MAX_WEBSOCKET_CONNECTIONS:
        logger.error(
            f"❌ Превышен лимит соединений Hyperliquid: {connections}/{MAX_WEBSOCKET_CONNECTIONS}"
        )
    
    # Проверка лимита подписок
    if subscriptions >= MAX_WEBSOCKET_SUBSCRIPTIONS * WARNING_THRESHOLD:
        logger.warning(
            f"⚠️ Приближение к лимиту подписок Hyperliquid: {subscriptions}/{MAX_WEBSOCKET_SUBSCRIPTIONS} "
            f"({subscriptions/MAX_WEBSOCKET_SUBSCRIPTIONS*100:.1f}%)"
        )
    
    if subscriptions >= MAX_WEBSOCKET_SUBSCRIPTIONS:
        logger.error(
            f"❌ Превышен лимит подписок Hyperliquid: {subscriptions}/{MAX_WEBSOCKET_SUBSCRIPTIONS}"
        )


def _normalize_symbol(symbol: str) -> str:
    """
    Нормализует символ Hyperliquid для использования в системе.
    Hyperliquid может использовать формат "BTC/USDC:USDC", "BTC", "@index" или "PURR/USDC".
    
    Args:
        symbol: Символ от Hyperliquid
        
    Returns:
        Нормализованный символ (например, "BTCUSDC")
    """
    if not symbol:
        return ""
    
    # Убираем пробелы и преобразуем в верхний регистр
    symbol = symbol.upper().strip()
    
    # Если символ начинается с "@", это специальный формат "@index" для спота
    # Убираем "@" для нормализации (например, "@index" -> "index")
    if symbol.startswith("@"):
        symbol = symbol.replace("@", "")
        # После удаления "@" проверяем, не является ли это специальным символом "index"
        # Если это "index", оставляем как есть (не добавляем USDC)
        if symbol == "INDEX":
            return symbol
    
    # Если символ содержит "/", извлекаем базовую валюту
    if "/" in symbol:
        parts = symbol.split("/")
        if len(parts) >= 2:
            base = parts[0]
            quote = parts[1].split(":")[0] if ":" in parts[1] else parts[1]
            return f"{base}{quote}"
    
    # Если это просто базовая валюта, добавляем USDC
    # Исключение: если это "INDEX" (уже обработан выше), не добавляем USDC
    if not symbol.endswith("USDC") and not symbol.endswith("USDT") and symbol != "INDEX":
        return f"{symbol}USDC"
    
    return symbol


async def _ws_connection_worker(
    symbols: List[str],
    market: str,
    connection_id: str,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
):
    """
    WebSocket worker для одного соединения.
    """
    reconnect_attempt = 0
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        
        try:
            if reconnect_attempt > 1:
                delay = min(2 ** min(reconnect_attempt - 1, 5), MAX_RECONNECT_DELAY)
                _stats[market]["reconnects"] += 1
                await on_error({
                    "exchange": "hyperliquid",
                    "market": market,
                    "connection_id": connection_id,
                    "type": "reconnect",
                })
                await asyncio.sleep(delay)
            
            async with _session.ws_connect(
                HYPERLIQUID_WS_URL,
                heartbeat=PING_INTERVAL_SEC,
                timeout=aiohttp.ClientTimeout(total=180)
            ) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                was_connected = True  # Устанавливаем флаг успешного подключения
                
                _stats[market]["active_connections"] += 1
                
                # Небольшая задержка после подключения для стабилизации соединения
                await asyncio.sleep(0.5)
                
                # Подписываемся на сделки для каждого символа
                # Hyperliquid использует формат: {"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC"}}
                subscription_errors = []
                for symbol in symbols:
                    # Для перпов: coin = name из meta.universe (например "BTC", "ETH")
                    # Для спота: coin может быть "PURR/USDC" или "@index" (из spotMeta.universe)
                    # Используем оригинальный символ как есть
                    coin = symbol
                    
                    # Формируем сообщение подписки
                    subscribe_msg = {
                        "method": "subscribe",
                        "subscription": {
                            "type": "trades",
                            "coin": coin
                        }
                    }
                    
                    try:
                        # Проверяем, что соединение еще открыто
                        if ws.closed:
                            logger.warning(f"Соединение закрыто при подписке на {symbol}")
                            break
                        
                        # Проверяем rate limit перед отправкой сообщения
                        await _check_rate_limit()
                        
                        await ws.send_json(subscribe_msg)
                        await asyncio.sleep(0.05)  # Небольшая задержка между подписками
                    except Exception as e:
                        error_msg = str(e)
                        # Не логируем "Cannot write to closing transport" как WARNING, это нормально при закрытии
                        if "closing transport" not in error_msg.lower():
                            subscription_errors.append(f"{symbol}: {e}")
                        
                        # Если соединение закрыто, прерываем подписку
                        if ws.closed or "closing" in error_msg.lower():
                            break
                
                # Логируем ошибки подписки, если они есть
                if subscription_errors and len(subscription_errors) <= 5:
                    for error in subscription_errors:
                        logger.warning(f"Ошибка подписки на {error}")
                elif subscription_errors:
                    logger.warning(f"Ошибки подписки на {len(subscription_errors)} символов")
                
                # Запускаем heartbeat задачу
                # Hyperliquid требует ping каждые 60 секунд, иначе разорвёт соединение
                async def ping_loop():
                    """Отправляет ping сообщения для поддержания соединения"""
                    while True:
                        try:
                            await asyncio.sleep(PING_INTERVAL_SEC)
                            
                            # Проверяем, что соединение еще открыто
                            if ws.closed:
                                break
                            
                            # Проверяем rate limit перед отправкой ping
                            # is_ping=True позволяет ping обходить rate limiting (критично для соединения)
                            await _check_rate_limit(is_ping=True)
                            
                            # Hyperliquid использует JSON формат: {"method": "ping"}
                            ping_msg = {"method": "ping"}
                            await ws.send_json(ping_msg)
                            
                        except asyncio.CancelledError:
                            # Нормальная отмена задачи - выходим из цикла
                            break
                        except Exception as e:
                            # Логируем ошибку, но продолжаем попытки отправки ping
                            error_msg = str(e)
                            # Не логируем "Cannot write to closing transport" как WARNING, это нормально при закрытии
                            if "closing transport" not in error_msg.lower():
                                logger.warning(f"Ошибка отправки ping Hyperliquid {market}: {e}")
                            
                            # Если соединение закрыто, выходим из цикла
                            if ws.closed or "closing" in error_msg.lower():
                                break
                            
                            # Для других ошибок продолжаем попытки (с небольшой задержкой)
                            await asyncio.sleep(1)
                
                ping_task = asyncio.create_task(ping_loop())
                
                try:
                    # Читаем сообщения
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                raw_data = msg.data
                                
                                # Парсим JSON
                                data = json.loads(raw_data)
                                
                                # Обрабатываем pong ответ: {"channel": "pong"}
                                if isinstance(data, dict) and data.get("channel") == "pong":
                                    continue
                                
                                # Обрабатываем подтверждение подписки: {"channel": "subscriptionResponse", ...}
                                if isinstance(data, dict) and data.get("channel") == "subscriptionResponse":
                                    continue
                                
                                # Обрабатываем сделки
                                # Формат: {"channel": "trades", "data": [...]}
                                trades = []
                                
                                if isinstance(data, dict):
                                    # Проверяем канал
                                    channel = data.get("channel", "")
                                    
                                    # Обрабатываем только канал "trades"
                                    if channel == "trades":
                                        # Данные в поле "data"
                                        data_field = data.get("data", [])
                                        if isinstance(data_field, list):
                                            trades = data_field
                                
                                # Обрабатываем каждую сделку
                                if trades:
                                    for trade in trades:
                                        if not isinstance(trade, dict):
                                            continue
                                        
                                        try:
                                            # Извлекаем данные о сделке
                                            # Пробуем разные поля
                                            price = _parse_float(
                                                trade.get("price") or 
                                                trade.get("p") or 
                                                trade.get("px") or 
                                                0
                                            )
                                            size = _parse_float(
                                                trade.get("size") or 
                                                trade.get("sz") or 
                                                trade.get("qty") or 
                                                trade.get("v") or 
                                                trade.get("volume") or
                                                0
                                            )
                                            timestamp = int(
                                                trade.get("time") or 
                                                trade.get("ts") or 
                                                trade.get("timestamp") or 
                                                trade.get("T") or 
                                                trade.get("time_ms") or
                                                0
                                            )
                                            
                                            # Получаем символ
                                            symbol = (
                                                trade.get("coin") or 
                                                trade.get("symbol") or 
                                                trade.get("s") or 
                                                trade.get("pair") or
                                                ""
                                            )
                                            
                                            # Если timestamp в секундах, преобразуем в миллисекунды
                                            # Unix timestamp в секундах для текущей даты (2024+) находится в диапазоне ~1700000000-1800000000
                                            # Если timestamp меньше 10000000000 (10 миллиардов), это скорее всего секунды
                                            # Максимальный Unix timestamp в секундах до 2038 года: 2147483647
                                            if timestamp > 0:
                                                # Проверяем, что timestamp в разумном диапазоне для секунд
                                                # Если меньше 10000000000, это скорее всего секунды (не миллисекунды)
                                                if timestamp < 10000000000:
                                                    timestamp = timestamp * 1000
                                                # Если timestamp уже в миллисекундах, оставляем как есть
                                            
                                            # Нормализуем символ
                                            normalized_symbol = _normalize_symbol(symbol)
                                            
                                            # Логируем проблемные сделки для отладки (только первые несколько раз)
                                            if not normalized_symbol and symbol:
                                                # Символ был, но после нормализации стал пустым - это не должно происходить
                                                logger.debug(f"Hyperliquid: символ '{symbol}' стал пустым после нормализации")
                                            
                                            # Проверяем валидность всех данных перед обработкой
                                            if price > 0 and size > 0 and normalized_symbol and timestamp > 0:
                                                if _builder:
                                                    finished = await _builder.add_trade(
                                                        exchange="hyperliquid",
                                                        market=market,
                                                        symbol=normalized_symbol,
                                                        price=price,
                                                        qty=abs(size),
                                                        ts_ms=timestamp,
                                                    )
                                                    
                                                    if finished is not None:
                                                        await on_candle(finished)
                                        except Exception as trade_error:
                                            # Игнорируем ошибки обработки отдельной сделки
                                            logger.debug(f"Ошибка обработки сделки: {trade_error}")
                                            continue
                                
                            except json.JSONDecodeError:
                                # Игнорируем ошибки парсинга JSON
                                continue
                            except Exception as e:
                                # Логируем только первые несколько ошибок, чтобы не засорять лог
                                logger.debug(f"Ошибка обработки сообщения Hyperliquid: {e}")
                                continue
                        
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            # Переподключение будет подсчитано в начале следующей итерации цикла
                            # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                            break
                        
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            # Переподключение будет подсчитано в начале следующей итерации цикла
                            # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                            break
                
                finally:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass
                
                _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                # Сбрасываем флаг подключения при выходе из контекста WebSocket
                was_connected = False
        
        except asyncio.CancelledError:
            break
        except aiohttp.WSServerHandshakeError as e:
            # Обработка ошибок WebSocket handshake (502, 503, 504 и т.д.)
            status = getattr(e, 'status', None) or getattr(e, 'code', None)
            error_str = str(e)
            
            # Извлекаем код статуса из сообщения об ошибке, если он не в атрибутах
            if status is None:
                status_match = re.search(r'(\d{3})', error_str)
                if status_match:
                    try:
                        status = int(status_match.group(1))
                    except ValueError:
                        pass
            
            # Определяем, является ли это серверной ошибкой (5xx)
            is_server_error = False
            if status:
                is_server_error = status >= 500
                error_msg = f"WebSocket handshake error {status}: {error_str}"
            else:
                # Проверяем строку ошибки на наличие кодов 5xx
                if '502' in error_str or '503' in error_str or '504' in error_str:
                    is_server_error = True
                    error_msg = f"WebSocket handshake error: {error_str}"
                else:
                    error_msg = f"WebSocket handshake error: {error_str}"
            
            logger.error(f"Ошибка в WS соединении Hyperliquid {connection_id}: {error_msg}")
            
            # Для ошибок 5xx (проблемы на стороне сервера) увеличиваем задержку
            if is_server_error:
                # Увеличиваем базовую задержку для серверных ошибок
                additional_delay = min(10 * reconnect_attempt, 30)  # До 30 секунд дополнительной задержки
                logger.warning(f"Серверная ошибка WebSocket, дополнительная задержка: {additional_delay}с")
                await asyncio.sleep(additional_delay)
            
            await on_error({
                "exchange": "hyperliquid",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "status_code": status,
                "error_type": "websocket_handshake",
            })
            _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
        except aiohttp.ClientResponseError as e:
            # Специальная обработка HTTP ошибок (502, 503, 504 и т.д.)
            status = e.status
            error_msg = f"HTTP {status}: {e.message}"
            logger.error(f"Ошибка в WS соединении Hyperliquid {connection_id}: {error_msg}")
            
            # Для ошибок 5xx (проблемы на стороне сервера) увеличиваем задержку
            if status >= 500:
                # Увеличиваем базовую задержку для серверных ошибок
                additional_delay = min(10 * reconnect_attempt, 30)  # До 30 секунд дополнительной задержки
                logger.warning(f"Серверная ошибка {status}, дополнительная задержка: {additional_delay}с")
                await asyncio.sleep(additional_delay)
            
            await on_error({
                "exchange": "hyperliquid",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "status_code": status,
            })
            _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
        except (ConnectionResetError, ConnectionError) as e:
            # Обработка ConnectionResetError (WinError 10054) - соединение принудительно закрыто удаленным хостом
            error_msg = f"Соединение принудительно закрыто удаленным хостом: {e}"
            logger.warning(f"Hyperliquid {connection_id}: {error_msg}")
            await on_error({
                "exchange": "hyperliquid",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "error_type": "connection_reset",
            })
            _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
        except aiohttp.ClientError as e:
            # Обработка других ошибок клиента (сеть, таймауты и т.д.)
            error_msg = f"Client error: {e}"
            logger.error(f"Ошибка в WS соединении Hyperliquid {connection_id}: {error_msg}")
            await on_error({
                "exchange": "hyperliquid",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
            })
            _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
        except Exception as e:
            # Обработка всех остальных ошибок, включая случаи, когда ошибка 502 приходит как строка
            error_str = str(e)
            
            # Проверяем, содержит ли ошибка код 502 или другие серверные ошибки
            is_server_error = False
            status = None
            if '502' in error_str or 'Invalid response status' in error_str:
                is_server_error = True
                status = 502
                # Извлекаем код статуса из сообщения, если возможно
                status_match = re.search(r'(\d{3})', error_str)
                if status_match:
                    try:
                        status = int(status_match.group(1))
                    except ValueError:
                        pass
            
            error_msg = error_str if not is_server_error else f"HTTP {status}: {error_str}"
            logger.error(f"Ошибка в WS соединении Hyperliquid {connection_id}: {error_msg}")
            
            # Для ошибок 5xx увеличиваем задержку
            if is_server_error:
                additional_delay = min(10 * reconnect_attempt, 30)
                logger.warning(f"Обнаружена серверная ошибка, дополнительная задержка: {additional_delay}с")
                await asyncio.sleep(additional_delay)
            
            await on_error({
                "exchange": "hyperliquid",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "status_code": status,
            })
            _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)


async def start(
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
    config: AppConfig,
    **kwargs  # Для совместимости с возможными дополнительными параметрами
) -> List[asyncio.Task]:
    """
    Запускает WebSocket клиенты для spot и linear рынков.
    
    Args:
        on_candle: Callback для обработки завершённых 1-секундных свечей
        on_error: Callback для обработки ошибок
        config: Конфигурация приложения
        
    Returns:
        Список asyncio задач для запущенных соединений
    """
    global _builder, _tasks, _spot_tasks, _linear_tasks, _session
    
    # Создаём сессию с SSL сертификатами из certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    _session = aiohttp.ClientSession(connector=connector)
    
    # Получаем callback для подсчёта трейдов, если передан
    on_trade = kwargs.get('on_trade', None)
    # Создаём CandleBuilder
    _builder = CandleBuilder(
        maxlen=config.memory_max_candles_per_symbol,
        on_trade=on_trade,
        on_candle=on_candle,
    )
    
    # Проверяем конфигурацию и получаем символы только для включенных рынков
    fetch_spot = config.exchanges.hyperliquid_spot
    fetch_linear = config.exchanges.hyperliquid_linear
    
    if fetch_spot and fetch_linear:
        spot_symbols, linear_symbols = await asyncio.gather(
            fetch_symbols("spot"),
            fetch_symbols("linear")
        )
    elif fetch_spot:
        spot_symbols = await fetch_symbols("spot")
        linear_symbols = []
    elif fetch_linear:
        spot_symbols = []
        linear_symbols = await fetch_symbols("linear")
    else:
        spot_symbols = []
        linear_symbols = []
    
    _tasks = []
    _spot_tasks = []
    _linear_tasks = []
    
    # Подсчитываем общее количество соединений и подписок
    total_connections = 0
    total_subscriptions = 0
    
    # Планируем соединения для SPOT
    spot_connections_planned = 0
    spot_subscriptions_planned = 0
    if fetch_spot and spot_symbols:
        spot_connections_planned = math.ceil(len(spot_symbols) / SPOT_SYMBOLS_PER_CONNECTION)
        spot_subscriptions_planned = len(spot_symbols)
    
    # Планируем соединения для LINEAR
    linear_connections_planned = 0
    linear_subscriptions_planned = 0
    if fetch_linear and linear_symbols:
        linear_connections_planned = math.ceil(len(linear_symbols) / LINEAR_SYMBOLS_PER_CONNECTION)
        linear_subscriptions_planned = len(linear_symbols)
    
    total_connections = spot_connections_planned + linear_connections_planned
    total_subscriptions = spot_subscriptions_planned + linear_subscriptions_planned
    
    # Проверяем лимиты перед созданием соединений
    _check_limits_warning(total_connections, total_subscriptions)
    
    # Ограничиваем количество соединений до лимита
    if total_connections > MAX_WEBSOCKET_CONNECTIONS:
        logger.error(
            f"❌ Превышен лимит соединений Hyperliquid: планируется {total_connections}, "
            f"максимум {MAX_WEBSOCKET_CONNECTIONS}. Соединения будут ограничены."
        )
        
        # Распределяем лимит соединений пропорционально между spot и linear
        if total_connections > 0:
            spot_ratio = spot_connections_planned / total_connections
            linear_ratio = linear_connections_planned / total_connections
            
            max_connections_spot = int(MAX_WEBSOCKET_CONNECTIONS * spot_ratio)
            max_connections_linear = MAX_WEBSOCKET_CONNECTIONS - max_connections_spot
            
            if fetch_spot and spot_symbols:
                max_spot_symbols = max_connections_spot * SPOT_SYMBOLS_PER_CONNECTION
                if len(spot_symbols) > max_spot_symbols:
                    logger.warning(
                        f"Ограничение символов SPOT: {len(spot_symbols)} -> {max_spot_symbols} "
                        f"из-за лимита соединений"
                    )
                    spot_symbols = spot_symbols[:max_spot_symbols]
                    spot_connections_planned = max_connections_spot
                    spot_subscriptions_planned = len(spot_symbols)
            
            if fetch_linear and linear_symbols:
                max_linear_symbols = max_connections_linear * LINEAR_SYMBOLS_PER_CONNECTION
                if len(linear_symbols) > max_linear_symbols:
                    logger.warning(
                        f"Ограничение символов LINEAR: {len(linear_symbols)} -> {max_linear_symbols} "
                        f"из-за лимита соединений"
                    )
                    linear_symbols = linear_symbols[:max_linear_symbols]
                    linear_connections_planned = max_connections_linear
                    linear_subscriptions_planned = len(linear_symbols)
        
        total_connections = spot_connections_planned + linear_connections_planned
        total_subscriptions = spot_subscriptions_planned + linear_subscriptions_planned
    
    # Ограничиваем количество подписок до лимита
    if total_subscriptions > MAX_WEBSOCKET_SUBSCRIPTIONS:
        logger.error(
            f"❌ Превышен лимит подписок Hyperliquid: планируется {total_subscriptions}, "
            f"максимум {MAX_WEBSOCKET_SUBSCRIPTIONS}. Подписки будут ограничены."
        )
        
        # Распределяем лимит подписок пропорционально между spot и linear
        if total_subscriptions > 0:
            spot_ratio = spot_subscriptions_planned / total_subscriptions
            linear_ratio = linear_subscriptions_planned / total_subscriptions
            
            max_spot_subscriptions = int(MAX_WEBSOCKET_SUBSCRIPTIONS * spot_ratio)
            max_linear_subscriptions = MAX_WEBSOCKET_SUBSCRIPTIONS - max_spot_subscriptions
            
            if fetch_spot and spot_symbols and len(spot_symbols) > max_spot_subscriptions:
                logger.warning(
                    f"Ограничение подписок SPOT: {len(spot_symbols)} -> {max_spot_subscriptions} "
                    f"из-за лимита подписок"
                )
                spot_symbols = spot_symbols[:max_spot_subscriptions]
                spot_subscriptions_planned = len(spot_symbols)
                spot_connections_planned = math.ceil(len(spot_symbols) / SPOT_SYMBOLS_PER_CONNECTION)
            
            if fetch_linear and linear_symbols and len(linear_symbols) > max_linear_subscriptions:
                logger.warning(
                    f"Ограничение подписок LINEAR: {len(linear_symbols)} -> {max_linear_subscriptions} "
                    f"из-за лимита подписок"
                )
                linear_symbols = linear_symbols[:max_linear_subscriptions]
                linear_subscriptions_planned = len(linear_symbols)
                linear_connections_planned = math.ceil(len(linear_symbols) / LINEAR_SYMBOLS_PER_CONNECTION)
        
        total_connections = spot_connections_planned + linear_connections_planned
        total_subscriptions = spot_subscriptions_planned + linear_subscriptions_planned
    
    # Логируем финальную конфигурацию
    logger.info(
        f"Hyperliquid: планируется {total_connections} соединений, {total_subscriptions} подписок "
        f"(SPOT: {spot_connections_planned} соединений, {spot_subscriptions_planned} подписок; "
        f"LINEAR: {linear_connections_planned} соединений, {linear_subscriptions_planned} подписок)"
    )
    
    # Запускаем SPOT
    if fetch_spot and spot_symbols:
        _stats["spot"]["active_symbols"] = len(spot_symbols)
        _stats["spot"]["total_subscriptions"] = len(spot_symbols)
        
        # Создаём соединения для SPOT
        for i in range(0, len(spot_symbols), SPOT_SYMBOLS_PER_CONNECTION):
            chunk = spot_symbols[i:i + SPOT_SYMBOLS_PER_CONNECTION]
            connection_id = f"SPOT#{i // SPOT_SYMBOLS_PER_CONNECTION + 1}"
            
            task = asyncio.create_task(_ws_connection_worker(
                symbols=chunk,
                market="spot",
                connection_id=connection_id,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _spot_tasks.append(task)
            await asyncio.sleep(0.5)  # Задержка между соединениями
    
    # Запускаем LINEAR
    if fetch_linear and linear_symbols:
        _stats["linear"]["active_symbols"] = len(linear_symbols)
        _stats["linear"]["total_subscriptions"] = len(linear_symbols)
        
        # Создаём соединения для LINEAR
        for i in range(0, len(linear_symbols), LINEAR_SYMBOLS_PER_CONNECTION):
            chunk = linear_symbols[i:i + LINEAR_SYMBOLS_PER_CONNECTION]
            connection_id = f"LINEAR#{i // LINEAR_SYMBOLS_PER_CONNECTION + 1}"
            
            task = asyncio.create_task(_ws_connection_worker(
                symbols=chunk,
                market="linear",
                connection_id=connection_id,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _linear_tasks.append(task)
            await asyncio.sleep(0.5)  # Задержка между соединениями
    
    return list(_tasks)


async def stop(tasks: List[asyncio.Task]) -> None:
    """Останавливает все WebSocket соединения и очищает ресурсы."""
    global _tasks, _spot_tasks, _linear_tasks, _builder, _session
    
    for t in tasks:
        t.cancel()
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Даём время всем соединениям корректно закрыться
    await asyncio.sleep(0.5)
    
    if _session and not _session.closed:
        await _session.close()
    
    _stats["spot"]["active_connections"] = 0
    _stats["linear"]["active_connections"] = 0
    _builder = None
    _session = None
    _spot_tasks = []
    _linear_tasks = []
    
    logger.info("Все соединения Hyperliquid остановлены")


def get_statistics() -> dict:
    """
    Возвращает текущую статистику биржи.
    
    Returns:
        Словарь с ключами "spot" и "linear", каждый содержит:
        - active_connections: int
        - active_symbols: int  
        - reconnects: int
        - total_subscriptions: int
    """
    # Обновляем статистику активных соединений на основе отдельных списков задач
    _stats["spot"]["active_connections"] = len([t for t in _spot_tasks if not t.done()])
    _stats["linear"]["active_connections"] = len([t for t in _linear_tasks if not t.done()])
    
    # Добавляем информацию о лимитах
    total_connections = _stats["spot"]["active_connections"] + _stats["linear"]["active_connections"]
    total_subscriptions = _stats["spot"]["total_subscriptions"] + _stats["linear"]["total_subscriptions"]
    
    stats_with_limits = _stats.copy()
    stats_with_limits["limits"] = {
        "max_connections": MAX_WEBSOCKET_CONNECTIONS,
        "max_subscriptions": MAX_WEBSOCKET_SUBSCRIPTIONS,
        "max_messages_per_minute": MAX_MESSAGES_PER_MINUTE,
        "current_connections": total_connections,
        "current_subscriptions": total_subscriptions,
        "connections_usage_percent": (total_connections / MAX_WEBSOCKET_CONNECTIONS * 100) if MAX_WEBSOCKET_CONNECTIONS > 0 else 0,
        "subscriptions_usage_percent": (total_subscriptions / MAX_WEBSOCKET_SUBSCRIPTIONS * 100) if MAX_WEBSOCKET_SUBSCRIPTIONS > 0 else 0,
    }
    
    return stats_with_limits


