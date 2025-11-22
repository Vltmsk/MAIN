"""
WebSocket обработчик для Gate.io
Адаптация существующего Gate к стандарту NEWEX.md
"""
import ssl
import certifi
import asyncio
import time
import sys
from typing import Awaitable, Callable, List
import websockets
import json
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from .symbol_fetcher import fetch_symbols

logger = get_logger(__name__)

# Gate.io WebSocket URLs
SPOT_WS_URL = "wss://api.gateio.ws/ws/v4/"
LINEAR_WS_URL = "wss://fx-ws.gateio.ws/v4/ws/usdt"

# Конфигурация
# Лимиты символов на одно соединение (соединения создаются автоматически)
SPOT_SYMBOLS_PER_CONNECTION = 135
LINEAR_SYMBOLS_PER_CONNECTION = 100
DELAY_BETWEEN_WS = 1
DELAY_BETWEEN_SUBSCRIBE = 0.5
HEARTBEAT_INTERVAL = 30
RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 300
BACKOFF_MULTIPLIER = 2

# Глобальные переменные
_builder: CandleBuilder | None = None
_tasks: List[asyncio.Task] = []
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


def _safe_float(x) -> float:
    """Безопасное преобразование в float."""
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(x) -> int:
    """Безопасное преобразование в int."""
    try:
        return int(float(x))
    except (ValueError, TypeError):
        return 0


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
    import random
    
    ws_url = SPOT_WS_URL if market == "spot" else LINEAR_WS_URL
    reconnect_delay = RECONNECT_DELAY
    reconnect_attempt = 0
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        is_reconnect = reconnect_attempt > 1
        
        try:
            if is_reconnect:
                _stats[market]["reconnects"] += 1
                await on_error({
                    "exchange": "gate",
                    "market": market,
                    "connection_id": connection_id,
                    "type": "reconnect",
                })
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * BACKOFF_MULTIPLIER + random.uniform(0, 5), MAX_RECONNECT_DELAY)
            
            # Настройка SSL для websockets
            # На Windows отключаем проверку SSL-сертификатов (аналогично другим биржам)
            # На Linux/Mac используем сертификаты из certifi
            if sys.platform == "win32":
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            else:
                ssl_context = ssl.create_default_context(cafile=certifi.where())
            
            async with websockets.connect(
                ws_url,
                ping_interval=None,  # Отключаем автоматические ping, используем ручные JSON ping
                ping_timeout=None,
                close_timeout=10,
                ssl=ssl_context,
            ) as websocket:
                # Сбрасываем счётчики после успешного подключения
                reconnect_attempt = 0
                reconnect_delay = RECONNECT_DELAY
                was_connected = True  # Устанавливаем флаг успешного подключения
                
                _stats[market]["active_connections"] += 1
                
                # Задача для отправки ping сообщений
                ping_channel = "spot.ping" if market == "spot" else "futures.ping"
                
                async def ping_loop():
                    """Отправляет JSON ping сообщения для поддержания соединения"""
                    # Отправляем первый ping сразу после подключения
                    try:
                        ping_msg = {
                            "time": int(time.time()),
                            "channel": ping_channel,
                        }
                        await websocket.send(json.dumps(ping_msg))
                    except (websockets.exceptions.ConnectionClosed, Exception):
                        # Если соединение уже закрыто или ошибка, прекращаем ping loop
                        return
                    
                    # Затем отправляем ping каждые HEARTBEAT_INTERVAL секунд
                    while True:
                        try:
                            await asyncio.sleep(HEARTBEAT_INTERVAL)
                            ping_msg = {
                                "time": int(time.time()),
                                "channel": ping_channel,
                            }
                            await websocket.send(json.dumps(ping_msg))
                        except (websockets.exceptions.ConnectionClosed, Exception):
                            # Соединение закрыто или ошибка - прекращаем ping loop
                            break
                
                ping_task = asyncio.create_task(ping_loop())
                
                try:
                    # Отправляем подписки
                    for i, symbol in enumerate(symbols):
                        if market == "spot":
                            subscribe_msg = {
                                "time": int(time.time()),
                                "channel": "spot.trades",
                                "event": "subscribe",
                                "payload": [symbol],
                            }
                        else:
                            subscribe_msg = {
                                "time": int(time.time()),
                                "channel": "futures.trades",
                                "event": "subscribe",
                                "payload": [symbol],
                            }
                        
                        await websocket.send(json.dumps(subscribe_msg))
                        
                        # Задержка между подписками
                        if i < len(symbols) - 1:
                            await asyncio.sleep(DELAY_BETWEEN_SUBSCRIBE)
                    
                    # Читаем сообщения
                    while True:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=120)
                            try:
                                message_dict = json.loads(message)
                            except json.JSONDecodeError as e:
                                logger.warning(f"Gate {connection_id}: ошибка парсинга JSON сообщения: {e}")
                                logger.debug(f"Gate {connection_id}: сообщение (первые 200 символов): {message[:200] if len(message) > 200 else message}")
                                continue
                            
                            # Обработка pong
                            if message_dict.get("channel") in ["spot.pong", "futures.pong"]:
                                continue
                            
                            # Обработка сделок
                            channel = message_dict.get("channel", "")
                            if "trades" in channel:
                                trade_result = message_dict.get("result")
                                
                                if not trade_result:
                                    continue
                                
                                # SPOT: trade_result это объект
                                if isinstance(trade_result, dict) and "currency_pair" in trade_result:
                                    symbol = trade_result.get("currency_pair")
                                    create_time_ms = trade_result.get("create_time_ms")
                                    if isinstance(create_time_ms, str):
                                        timestamp = _safe_int(create_time_ms)
                                    elif isinstance(create_time_ms, (int, float)):
                                        timestamp = int(create_time_ms)
                                    else:
                                        create_time = trade_result.get("create_time", 0)
                                        timestamp = int(create_time * 1000) if create_time > 0 else 0
                                    
                                    price_str = trade_result.get("price", "0")
                                    amount_str = trade_result.get("amount", "0")
                                    price = _safe_float(price_str) if price_str else 0.0
                                    amount = _safe_float(amount_str) if amount_str else 0.0
                                    
                                    if _builder and price > 0 and amount > 0:
                                        finished = await _builder.add_trade(
                                            exchange="gate",
                                            market=market,
                                            symbol=symbol,
                                            price=price,
                                            qty=amount,
                                            ts_ms=timestamp,
                                        )
                                        if finished is not None:
                                            await on_candle(finished)
                                
                                # LINEAR: trade_result это массив
                                elif isinstance(trade_result, list):
                                    for trade in trade_result:
                                        if not isinstance(trade, dict):
                                            continue
                                        
                                        symbol = trade.get("contract") or trade.get("symbol")
                                        create_time_ms = trade.get("create_time_ms")
                                        if isinstance(create_time_ms, str):
                                            timestamp = _safe_int(create_time_ms)
                                        elif isinstance(create_time_ms, (int, float)):
                                            timestamp = int(create_time_ms)
                                        else:
                                            create_time = trade.get("create_time", 0)
                                            timestamp = int(create_time * 1000) if create_time > 0 else 0
                                        
                                        price_str = trade.get("price", "0")
                                        size = _safe_int(trade.get("size", 0))
                                        price = _safe_float(price_str) if price_str else 0.0
                                        amount = abs(size)
                                        
                                        if _builder and price > 0 and amount > 0:
                                            finished = await _builder.add_trade(
                                                exchange="gate",
                                                market=market,
                                                symbol=symbol,
                                                price=price,
                                                qty=amount,
                                                ts_ms=timestamp,
                                            )
                                            if finished is not None:
                                                await on_candle(finished)
                        
                        except asyncio.TimeoutError:
                            # При таймауте продолжаем чтение (ping отправляется отдельной задачей)
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            # Переподключение будет подсчитано в начале следующей итерации цикла
                            # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                            break
                finally:
                    # Отменяем задачу ping при выходе
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass
                    # Декрементируем счётчик соединений только если он был увеличен
                    _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                    # Сбрасываем флаг подключения при выходе из контекста WebSocket
                    was_connected = False
        
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка в WS соединении Gate {connection_id}: {e}")
            await on_error({
                "exchange": "gate",
                "market": market,
                "connection_id": connection_id,
                "error": str(e),
            })
            # Не декрементируем здесь, так как соединение могло не быть установлено
            # или уже было декрементировано в finally блоке


async def start(
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
    config: AppConfig,
    **kwargs  # Для совместимости с возможными дополнительными параметрами
) -> List[asyncio.Task]:
    """
    Запускает WebSocket клиенты для spot и linear рынков.
    """
    global _builder, _tasks
    
    # Получаем callback для подсчёта трейдов, если передан
    on_trade = kwargs.get('on_trade', None)
    _builder = CandleBuilder(maxlen=config.memory_max_candles_per_symbol, on_trade=on_trade)
    
    _tasks = []
    
    # Проверяем конфигурацию и получаем символы только для включенных рынков
    fetch_spot = config.exchanges.gate_spot
    fetch_linear = config.exchanges.gate_linear
    
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
    
    # Запускаем SPOT
    if fetch_spot and spot_symbols:
        _stats["spot"]["active_symbols"] = len(spot_symbols)
        
        # Автоматически создаём столько соединений, сколько нужно
        for i in range(0, len(spot_symbols), SPOT_SYMBOLS_PER_CONNECTION):
            chunk = spot_symbols[i:i + SPOT_SYMBOLS_PER_CONNECTION]
            connection_id = f"SPOT#{i // SPOT_SYMBOLS_PER_CONNECTION}"
            task = asyncio.create_task(_ws_connection_worker(
                symbols=chunk,
                market="spot",
                connection_id=connection_id,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            await asyncio.sleep(DELAY_BETWEEN_WS)
    
    # Запускаем LINEAR
    if fetch_linear and linear_symbols:
        _stats["linear"]["active_symbols"] = len(linear_symbols)
        
        # Автоматически создаём столько соединений, сколько нужно
        for i in range(0, len(linear_symbols), LINEAR_SYMBOLS_PER_CONNECTION):
            chunk = linear_symbols[i:i + LINEAR_SYMBOLS_PER_CONNECTION]
            connection_id = f"LINEAR#{i // LINEAR_SYMBOLS_PER_CONNECTION}"
            task = asyncio.create_task(_ws_connection_worker(
                symbols=chunk,
                market="linear",
                connection_id=connection_id,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            await asyncio.sleep(DELAY_BETWEEN_WS)
    
    return list(_tasks)


async def stop(tasks: List[asyncio.Task]) -> None:
    """Останавливает все WebSocket соединения."""
    global _tasks, _builder
    
    for t in tasks:
        t.cancel()
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    _stats["spot"]["active_connections"] = 0
    _stats["linear"]["active_connections"] = 0
    _builder = None
    
    logger.info("Все соединения Gate остановлены")


def get_statistics() -> dict:
    """Возвращает статистику."""
    return _stats

