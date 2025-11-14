"""
WebSocket обработчик для Binance
Binance предоставляет уже готовые 1-секундные свечи через Kline streams
"""
import ssl
import certifi
import asyncio
from typing import Awaitable, Callable, List
import aiohttp
import json
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from .symbol_fetcher import fetch_symbols

logger = get_logger(__name__)

# Binance WebSocket endpoints
SPOT_WS_ENDPOINT = "wss://stream.binance.com:9443/stream"
FAPI_WS_ENDPOINT = "wss://fstream.binance.com/stream"  # Для combined streams (spot только)
FAPI_WS_ENDPOINT_WS = "wss://fstream.binance.com/ws"  # Для подписки через JSON (futures)

# Лимит потоков на одно WS-подключение
STREAMS_PER_CONNECTION = 150

# Глобальные переменные
_builder: CandleBuilder | None = None
_tasks: List[asyncio.Task] = []
_spot_tasks: List[asyncio.Task] = []  # Отдельное отслеживание spot задач
_linear_tasks: List[asyncio.Task] = []  # Отдельное отслеживание linear задач
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


def _chunk_list(items: List[str], size: int) -> List[List[str]]:
    """Разделить список на чанки."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def _parse_float(x) -> float:
    """Безопасное преобразование в float."""
    try:
        return float(x)
    except Exception:
        return 0.0


async def _ws_connection_worker(
    streams: List[str],
    market: str,
    url: str,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
):
    """
    WebSocket worker для одного соединения с множественными стримами.
    """
    reconnect_attempt = 0
    
    while True:
        reconnect_attempt += 1
        
        try:
            if reconnect_attempt > 1:
                delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                _stats[market]["reconnects"] += 1
                await on_error({
                    "exchange": "binance",
                    "market": market,
                    "connection_id": f"streams-{len(streams)}",
                    "type": "reconnect",
                })
                await asyncio.sleep(delay)
            
            async with _session.ws_connect(url, heartbeat=25) as ws:
                _stats[market]["active_connections"] += 1
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            payload = json.loads(msg.data)
                            await _handle_kline_message(payload, market, on_candle)
                        except Exception as e:
                            logger.error(f"Ошибка обработки сообщения Binance {market}: {e}")
                            logger.error(f"Payload (первые 200 символов): {msg.data[:200] if len(msg.data) > 200 else msg.data}")
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        break
                    
                _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка в WS соединении Binance {market}: {e}")
            await on_error({
                "exchange": "binance",
                "market": market,
                "error": str(e),
            })


async def _ws_connection_worker_subscribe(
    streams: List[str],
    market: str,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
):
    """
    WebSocket worker для Futures с подпиской через JSON (wss://fstream.binance.com/ws).
    Отличается от /stream тем, что требует явной подписки через JSON.
    """
    reconnect_attempt = 0
    
    while True:
        reconnect_attempt += 1
        
        try:
            if reconnect_attempt > 1:
                delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                _stats[market]["reconnects"] += 1
                await on_error({
                    "exchange": "binance",
                    "market": market,
                    "connection_id": f"ws-subscribe-{len(streams)}",
                    "type": "reconnect",
                })
                await asyncio.sleep(delay)
            
            url = FAPI_WS_ENDPOINT_WS
            async with _session.ws_connect(url, heartbeat=25) as ws:
                _stats[market]["active_connections"] += 1
                
                # Отправляем подписку через JSON
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": streams,
                    "id": 1
                }
                await ws.send_json(subscribe_msg)
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            payload = json.loads(msg.data)
                            
                            # Проверяем, это сообщение подписки или данные
                            if "result" in payload or "id" in payload:
                                continue
                            
                            # Обрабатываем continuous_kline сообщения (для futures через /ws)
                            if market == "linear" and payload.get("e") == "continuous_kline":
                                await _handle_continuous_kline_message(payload, on_candle)
                            else:
                                # Обрабатываем обычные kline сообщения (для spot)
                                await _handle_kline_message(payload, market, on_candle)
                        except Exception as e:
                            logger.error(f"Ошибка обработки сообщения Binance {market}: {e}")
                            logger.error(f"Payload (первые 200 символов): {msg.data[:200] if len(msg.data) > 200 else msg.data}")
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        break
                
                _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
        
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка в WS соединении Binance {market} (subscribe mode): {e}")
            await on_error({
                "exchange": "binance",
                "market": market,
                "error": str(e),
            })


async def _handle_continuous_kline_message(payload: dict, on_candle: Callable[[Candle], Awaitable[None]]):
    """
    Обработка Continuous Kline сообщения от Binance Futures через /ws.
    
    Формат payload: { "e": "continuous_kline", "E": 123456789, "ps": "BTCUSDT", "ct": "PERPETUAL", "k": {...} }
    Формат k: { 
        "t": 1234567890000,  # open time
        "T": 1234567890999,  # close time
        "i": "1s",
        "o": "50000",  # open
        "h": "51000",  # high
        "l": "49000",  # low
        "c": "50500",  # close
        "x": True,  # is closed
        "q": "1000.5"  # volume (quote asset)
    }
    """
    # Проверяем тип события
    if payload.get("e") != "continuous_kline":
        return
    
    # Получаем символ из поля ps (pair)
    symbol = payload.get("ps", "").upper()
    if not symbol:
        return
    
    # Получаем данные свечи
    k = payload.get("k")
    if not isinstance(k, dict):
        return
    
    # Только закрытые 1s свечи
    if not k.get("x", False):
        return
    
    # Парсим свечу
    try:
        open_price = _parse_float(k.get("o"))
        high = _parse_float(k.get("h"))
        low = _parse_float(k.get("l"))
        close = _parse_float(k.get("c"))
        volume_quote = _parse_float(k.get("q"))
        
        # Timestamp закрытия свечи
        close_time = int(k.get("T", 0))
        
        if close_time <= 0:
            return
        
        # Создаём Candle из данных Binance
        volume_base = volume_quote / close if close > 0 else 0
        
        candle = Candle(
            ts_ms=close_time,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume_base,
            market="linear",
            exchange="binance",
            symbol=symbol,
        )
        
        await on_candle(candle)
        
    except Exception as e:
        logger.error(f"Ошибка парсинга continuous kline свечи Binance linear для {symbol}: {e}")
        logger.debug(f"Данные kline: {k}")


async def _handle_kline_message(payload: dict, market: str, on_candle: Callable[[Candle], Awaitable[None]]):
    """
    Обработка Kline сообщения от Binance.
    
    Формат payload: { "stream": "btcusdt@kline_1s", "data": {...} }
    Формат data: { "e": "kline", "E": 123456789, "s": "BTCUSDT", "k": {...} }
    Формат k: { 
        "t": 1234567890000,  # open time
        "T": 1234567890999,  # close time
        "s": "BTCUSDT",
        "i": "1s",
        "o": "50000",  # open
        "h": "51000",  # high
        "l": "49000",  # low
        "c": "50500",  # close
        "x": True,  # is closed
        "q": "1000.5"  # volume (quote asset)
    }
    """
    # Проверяем, что это сообщение от kline стрима (spot или futures)
    stream = payload.get("stream", "")
    if not stream.endswith("@kline_1s"):
        return
    
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    
    k = data.get("k")
    if not isinstance(k, dict):
        return
    
    # Только закрытые 1s свечи
    if not k.get("x", False):
        return
    
    symbol = k.get("s", "").upper()
    if not symbol:
        return
    
    # Парсим свечу
    try:
        open_price = _parse_float(k.get("o"))
        high = _parse_float(k.get("h"))
        low = _parse_float(k.get("l"))
        close = _parse_float(k.get("c"))
        volume_quote = _parse_float(k.get("q"))
        
        # Timestamp закрытия свечи
        close_time = int(k.get("T", 0))
        
        if close_time <= 0:
            return
        
        # Создаём Candle из данных Binance
        # Для volume используем базовую валюту: volume_quote / close_price
        volume_base = volume_quote / close if close > 0 else 0
        
        candle = Candle(
            ts_ms=close_time,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume_base,
            market=market,
            exchange="binance",
            symbol=symbol,
        )
        
        await on_candle(candle)
        
    except Exception as e:
        logger.error(f"Ошибка парсинга свечи Binance {market} для {symbol}: {e}")
        logger.debug(f"Данные kline: {k}")


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
    # Для Binance трейды не обрабатываются через CandleBuilder (свечи уже готовые),
    # но callback может быть полезен для других целей
    on_trade = kwargs.get('on_trade', None)
    # CandleBuilder не нужен для Binance (свечи уже готовые)
    # Но создадим для совместимости
    _builder = CandleBuilder(maxlen=config.memory_max_candles_per_symbol, on_trade=on_trade)
    
    # Проверяем конфигурацию и получаем символы только для включенных рынков
    fetch_spot = config.exchanges.binance_spot
    fetch_linear = config.exchanges.binance_linear
    
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
        
        # Строим streams для SPOT: "btcusdt@kline_1s"
        spot_streams = [f"{sym.lower()}@kline_1s" for sym in spot_symbols]
        spot_chunks = _chunk_list(spot_streams, STREAMS_PER_CONNECTION)
        
        logger.info(f"Binance spot: запущено {len(spot_chunks)} соединений для {len(spot_symbols)} символов")
        
        for chunk in spot_chunks:
            url = f"{SPOT_WS_ENDPOINT}?streams={'/'.join(chunk)}"
            task = asyncio.create_task(_ws_connection_worker(
                streams=chunk,
                market="spot",
                url=url,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _spot_tasks.append(task)
    
    # Запускаем LINEAR
    if fetch_linear and linear_symbols:
        _stats["linear"]["active_symbols"] = len(linear_symbols)
        
        # Строим streams для LINEAR: "btcusdt_perpetual@continuousKline_1s" (как в официальной документации Binance для continuous kline)
        linear_streams = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in linear_symbols]
        linear_chunks = _chunk_list(linear_streams, STREAMS_PER_CONNECTION)
        
        logger.info(f"Binance linear: запущено {len(linear_chunks)} соединений для {len(linear_symbols)} символов")
        
        for i, chunk in enumerate(linear_chunks):
            task = asyncio.create_task(_ws_connection_worker_subscribe(
                streams=chunk,
                market="linear",
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _linear_tasks.append(task)
    elif fetch_linear:
        logger.warning("Binance linear: включен в конфигурации, но символов не получено")
    elif linear_symbols:
        logger.warning(f"Binance linear: получено {len(linear_symbols)} символов, но рынок отключен в конфигурации")
    else:
        # Инициализируем статистику для linear, даже если символов нет
        _stats["linear"]["active_symbols"] = 0
        _stats["linear"]["active_connections"] = 0
        _stats["linear"]["reconnects"] = 0
    
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
    
    logger.info("Все соединения Binance остановлены")


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

