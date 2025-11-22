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

# Время планового переподключения (23 часа в секундах)
SCHEDULED_RECONNECT_INTERVAL = 23 * 60 * 60  # 82800 секунд

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
    connection_state = {"is_scheduled_reconnect": False}
    
    while True:
        reconnect_attempt += 1
        
        # Сохраняем значение флага перед проверкой reconnect_attempt
        is_scheduled = connection_state["is_scheduled_reconnect"]
        # Сбрасываем флаг сразу, чтобы он не влиял на последующие итерации
        if is_scheduled:
            connection_state["is_scheduled_reconnect"] = False
        
        try:
            # Обрабатываем переподключение (обычное или плановое)
            if reconnect_attempt > 1 or (reconnect_attempt == 1 and is_scheduled):
                # Если это не плановое переподключение, увеличиваем счётчик и логируем
                if not is_scheduled:
                    delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                    _stats[market]["reconnects"] += 1
                    await on_error({
                        "exchange": "binance",
                        "market": market,
                        "connection_id": f"streams-{len(streams)}",
                        "type": "reconnect",
                    })
                    await asyncio.sleep(delay)
                else:
                    # Для планового переподключения не увеличиваем счётчик
                    await asyncio.sleep(1)  # Небольшая задержка перед новым подключением
            
            if _session is None or _session.closed:
                logger.error(f"Binance {market}: сессия не инициализирована или закрыта")
                await asyncio.sleep(5)
                continue
            
            async with _session.ws_connect(url, heartbeat=25) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                
                _stats[market]["active_connections"] += 1
                
                # Создаём задачу для планового переподключения через 23 часа
                scheduled_reconnect_task = asyncio.create_task(
                    _schedule_reconnect(ws, SCHEDULED_RECONNECT_INTERVAL, market, streams, on_error, connection_state)
                )
                
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                payload = json.loads(msg.data)
                                await _handle_kline_message(payload, market, on_candle)
                            except Exception as e:
                                logger.error(f"Ошибка обработки сообщения Binance {market}: {e}")
                                logger.error(f"Payload (первые 200 символов): {msg.data[:200] if len(msg.data) > 200 else msg.data}")
                        
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            logger.debug(f"Binance {market}: WebSocket закрыт (CLOSE)")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.warning(f"Binance {market}: WebSocket ошибка (ERROR)")
                            break
                finally:
                    # Отменяем задачу планового переподключения, если соединение закрылось раньше
                    scheduled_reconnect_task.cancel()
                    try:
                        await scheduled_reconnect_task
                    except asyncio.CancelledError:
                        pass
                
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
    connection_state = {"is_scheduled_reconnect": False}
    
    while True:
        reconnect_attempt += 1
        
        # Сохраняем значение флага перед проверкой reconnect_attempt
        is_scheduled = connection_state["is_scheduled_reconnect"]
        # Сбрасываем флаг сразу, чтобы он не влиял на последующие итерации
        if is_scheduled:
            connection_state["is_scheduled_reconnect"] = False
        
        try:
            # Обрабатываем переподключение (обычное или плановое)
            if reconnect_attempt > 1 or (reconnect_attempt == 1 and is_scheduled):
                # Если это не плановое переподключение, увеличиваем счётчик и логируем
                if not is_scheduled:
                    delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                    _stats[market]["reconnects"] += 1
                    await on_error({
                        "exchange": "binance",
                        "market": market,
                        "connection_id": f"ws-subscribe-{len(streams)}",
                        "type": "reconnect",
                    })
                    await asyncio.sleep(delay)
                else:
                    # Для планового переподключения не увеличиваем счётчик
                    await asyncio.sleep(1)  # Небольшая задержка перед новым подключением
            
            if _session is None or _session.closed:
                logger.error(f"Binance {market}: сессия не инициализирована или закрыта")
                await asyncio.sleep(5)
                continue
            
            url = FAPI_WS_ENDPOINT_WS
            async with _session.ws_connect(url, heartbeat=25) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                
                _stats[market]["active_connections"] += 1
                
                try:
                    # Отправляем подписку через JSON
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": streams,
                        "id": 1
                    }
                    await ws.send_json(subscribe_msg)
                    logger.info(f"Binance {market}: отправлена подписка на {len(streams)} стримов")
                    logger.debug(f"Binance {market}: примеры стримов: {streams[:3] if len(streams) > 0 else 'нет'}")
                    
                    # Ждём подтверждения подписки (максимум 30 секунд)
                    subscription_confirmed = False
                    subscription_timeout = 30.0
                    first_data_received = False
                    timeout_triggered = False
                    
                    # Создаём задачу для планового переподключения через 23 часа
                    scheduled_reconnect_task = asyncio.create_task(
                        _schedule_reconnect(ws, SCHEDULED_RECONNECT_INTERVAL, market, streams, on_error, connection_state)
                    )
                    
                    # Создаём задачу для проверки таймаута подписки
                    async def check_subscription_timeout():
                        nonlocal timeout_triggered
                        await asyncio.sleep(subscription_timeout)
                        if not subscription_confirmed and not first_data_received:
                            timeout_triggered = True
                            logger.warning(f"Binance {market}: таймаут подтверждения подписки без данных ({subscription_timeout}с), переподключение...")
                            if not ws.closed:
                                await ws.close()
                    
                    timeout_task = asyncio.create_task(check_subscription_timeout())
                    
                    try:
                        # Единый цикл для проверки подписки и обработки сообщений
                        async for msg in ws:
                            # Отменяем задачу таймаута, если получили данные или подтверждение
                            if subscription_confirmed or first_data_received:
                                if not timeout_task.done():
                                    timeout_task.cancel()
                            
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    
                                    # Логируем первое сообщение для отладки
                                    if not subscription_confirmed and not first_data_received:
                                        logger.debug(f"Binance {market}: первое сообщение после подписки: {json.dumps(payload)[:200]}")
                                    
                                    # Проверяем ответ на подписку (только если ещё не подтверждена)
                                    if not subscription_confirmed and payload.get("id") == 1:
                                        # Проверяем наличие ошибки (если есть ключ "error" - это ошибка)
                                        if "error" in payload:
                                            # Ошибка подписки
                                            error_msg = payload.get("error", {}).get("msg", "Unknown error")
                                            error_code = payload.get("error", {}).get("code", "Unknown")
                                            logger.error(f"Binance {market}: ошибка подписки (code: {error_code}): {error_msg}")
                                            logger.error(f"Binance {market}: полный ответ: {json.dumps(payload)}")
                                            await on_error({
                                                "exchange": "binance",
                                                "market": market,
                                                "connection_id": f"ws-subscribe-{len(streams)}",
                                                "type": "subscribe_error",
                                                "error": error_msg,
                                                "code": error_code,
                                            })
                                            # Отменяем задачу таймаута перед выходом
                                            if not timeout_task.done():
                                                timeout_task.cancel()
                                            break
                                        else:
                                            # Успешное подтверждение подписки (result может быть null - это нормально)
                                            subscription_confirmed = True
                                            logger.info(f"Binance {market}: подписка подтверждена для {len(streams)} стримов")
                                            # Отменяем задачу таймаута
                                            if not timeout_task.done():
                                                timeout_task.cancel()
                                            # Пропускаем это сообщение, так как это только подтверждение
                                            continue
                                    
                                    # Если это не ответ на подписку, но есть continuous_kline - подписка работает
                                    if not subscription_confirmed and payload.get("e") == "continuous_kline":
                                        subscription_confirmed = True
                                        first_data_received = True
                                        logger.info(f"Binance {market}: подписка работает (получено continuous_kline сообщение)")
                                        # Отменяем задачу таймаута
                                        if not timeout_task.done():
                                            timeout_task.cancel()
                                    elif payload.get("e") == "continuous_kline":
                                        first_data_received = True
                                        # Отменяем задачу таймаута при получении данных
                                        if not timeout_task.done():
                                            timeout_task.cancel()
                                    
                                    # Пропускаем служебные сообщения с id=1 (уже обработанные при подписке)
                                    if payload.get("id") == 1:
                                        continue
                                    
                                    # Обрабатываем continuous_kline сообщения (для futures через /ws)
                                    if market == "linear" and payload.get("e") == "continuous_kline":
                                        await _handle_continuous_kline_message(payload, on_candle)
                                    elif market != "linear":
                                        # Обрабатываем обычные kline сообщения (для spot, но не должно быть в этом worker)
                                        await _handle_kline_message(payload, market, on_candle)
                                        
                                except Exception as e:
                                    logger.error(f"Ошибка обработки сообщения Binance {market}: {e}")
                                    logger.error(f"Payload (первые 200 символов): {msg.data[:200] if len(msg.data) > 200 else msg.data}")
                            
                            elif msg.type == aiohttp.WSMsgType.CLOSE:
                                logger.debug(f"Binance {market}: WebSocket закрыт (CLOSE)")
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.warning(f"Binance {market}: WebSocket ошибка (ERROR)")
                                break
                        
                        # Отменяем задачу таймаута, если она ещё активна
                        if not timeout_task.done():
                            timeout_task.cancel()
                            try:
                                await timeout_task
                            except asyncio.CancelledError:
                                pass
                        
                        # Если вышли из цикла без подтверждения и без данных - переподключаемся
                        if not subscription_confirmed and not first_data_received and not timeout_triggered:
                            logger.warning(f"Binance {market}: подписка не подтверждена и данных не получено, переподключение...")
                            continue
                    finally:
                        # Отменяем задачу планового переподключения, если соединение закрылось раньше
                        scheduled_reconnect_task.cancel()
                        try:
                            await scheduled_reconnect_task
                        except asyncio.CancelledError:
                            pass
                        # Отменяем задачу таймаута в finally, если она ещё активна
                        if not timeout_task.done():
                            timeout_task.cancel()
                            try:
                                await timeout_task
                            except asyncio.CancelledError:
                                pass
                finally:
                    # Уменьшаем счётчик при выходе из соединения (включая случай неудачной подписки)
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


async def _schedule_reconnect(
    ws: aiohttp.ClientWebSocketResponse,
    reconnect_interval: float,
    market: str,
    streams: List[str],
    on_error: Callable[[dict], Awaitable[None]],
    connection_state: dict,
):
    """
    Задача для планового переподключения через указанный интервал.
    Закрывает соединение по истечении времени, что вызывает переподключение.
    Плановые переподключения не учитываются в счётчике reconnects.
    
    Args:
        ws: WebSocket соединение
        reconnect_interval: Интервал в секундах до переподключения (23 часа)
        market: Рынок (spot/linear)
        streams: Список стримов
        on_error: Callback для обработки ошибок
        connection_state: Словарь для хранения состояния соединения
    """
    try:
        await asyncio.sleep(reconnect_interval)
        
        # Устанавливаем флаг планового переподключения
        connection_state["is_scheduled_reconnect"] = True
        
        # Логируем плановое переподключение
        connection_id = f"streams-{len(streams)}" if market == "spot" else f"ws-subscribe-{len(streams)}"
        await on_error({
            "exchange": "binance",
            "market": market,
            "connection_id": connection_id,
            "type": "scheduled_reconnect",
        })
        
        # Закрываем соединение для планового переподключения
        # Это вызовет выход из async for msg in ws: и переподключение
        if not ws.closed:
            await ws.close()
            
    except asyncio.CancelledError:
        # Задача была отменена (соединение закрылось по другой причине)
        pass
    except Exception as e:
        logger.error(f"Ошибка в задаче планового переподключения Binance {market}: {e}")


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
    # Возвращаем статистику без перезаписи active_connections,
    # так как она обновляется в worker'ах при реальных подключениях/отключениях
    # Количество незавершенных задач может не соответствовать реальным соединениям
    # (задача может быть активна, но соединение в процессе переподключения)
    return _stats.copy()

