"""
WebSocket обработчик для Hyperliquid
"""
import ssl
import certifi
import asyncio
import math
import re
from typing import Awaitable, Callable, List
import aiohttp
import json
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from .symbol_fetcher import fetch_symbols

logger = get_logger(__name__)

# Hyperliquid WebSocket endpoint
HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"

# Конфигурация подключения
SPOT_SYMBOLS_PER_CONNECTION = 50
LINEAR_SYMBOLS_PER_CONNECTION = 50
PING_INTERVAL_SEC = 30
RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60

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
    },
    "linear": {
        "active_connections": 0,
        "active_symbols": 0,
        "reconnects": 0,
    },
}


def _parse_float(x) -> float:
    """Безопасное преобразование в float."""
    try:
        return float(x)
    except Exception:
        return 0.0


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
    # Оставляем как есть, но убираем "@" для нормализации
    if symbol.startswith("@"):
        # Для "@index" используем как есть, но можно преобразовать
        # В трейдах coin будет приходить уже нормализованным
        return symbol.replace("@", "")
    
    # Если символ содержит "/", извлекаем базовую валюту
    if "/" in symbol:
        parts = symbol.split("/")
        if len(parts) >= 2:
            base = parts[0]
            quote = parts[1].split(":")[0] if ":" in parts[1] else parts[1]
            return f"{base}{quote}"
    
    # Если это просто базовая валюта, добавляем USDC
    if not symbol.endswith("USDC") and not symbol.endswith("USDT"):
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
                            # Hyperliquid использует JSON формат: {"method": "ping"}
                            ping_msg = {"method": "ping"}
                            await ws.send_json(ping_msg)
                        except Exception:
                            break
                
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
                                            if timestamp > 0 and timestamp < 10000000000:
                                                timestamp = timestamp * 1000
                                            
                                            # Нормализуем символ
                                            normalized_symbol = _normalize_symbol(symbol)
                                            
                                            if price > 0 and size > 0 and normalized_symbol:
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
                            break
                        
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            break
                
                finally:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass
                
                _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
        
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
    _builder = CandleBuilder(maxlen=config.memory_max_candles_per_symbol, on_trade=on_trade)
    
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
    
    # Запускаем SPOT
    if fetch_spot and spot_symbols:
        _stats["spot"]["active_symbols"] = len(spot_symbols)
        
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
    """
    # Обновляем статистику активных соединений на основе отдельных списков задач
    _stats["spot"]["active_connections"] = len([t for t in _spot_tasks if not t.done()])
    _stats["linear"]["active_connections"] = len([t for t in _linear_tasks if not t.done()])
    
    return _stats


