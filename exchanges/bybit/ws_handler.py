"""
WebSocket обработчик для Bybit
"""
import ssl
import certifi
import asyncio
from typing import Awaitable, Callable, List
import aiohttp
import json
from config import AppConfig
from core.candle_builder import CandleBuilder, Candle
from core.logger import get_logger
from .symbol_fetcher import fetch_symbols

logger = get_logger(__name__)

# Bybit V5 WebSocket endpoints
WS_SPOT = "wss://stream.bybit.com/v5/public/spot"
WS_LINEAR = "wss://stream.bybit.com/v5/public/linear"

# Конфигурация подключения
WS_SYMBOLS_PER_CONNECTION_SPOT = 86
WS_SYMBOLS_PER_CONNECTION_LINEAR = 100
BATCH_SIZE_SPOT = 10
WS_PING_INTERVAL_SEC = 20

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


async def _ws_consumer_with_batches(
    market: str,
    connection_id: str,
    all_symbols: List[str],
    batches: List[tuple],
    session: aiohttp.ClientSession,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
):
    """
    WebSocket consumer для одного соединения с несколькими батчами внутри.
    """
    global _builder
    
    ws_url = WS_SPOT if market == "spot" else WS_LINEAR
    
    reconnect_attempt = 0
    max_reconnect_delay = 60
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        if reconnect_attempt > 1:
            delay = min(2 ** min(reconnect_attempt - 1, 5), max_reconnect_delay)
            _stats[market]["reconnects"] += 1
            await on_error({
                "exchange": "bybit",
                "market": market,
                "connection_id": connection_id,
                "type": "reconnect",
            })
            await asyncio.sleep(delay)
        
        ping_task = None
        connected = False
        
        try:
            ws = await session.ws_connect(ws_url, heartbeat=60, timeout=aiohttp.ClientTimeout(total=180))
            connected = True
            was_connected = True  # Устанавливаем флаг успешного подключения
            _stats[market]["active_connections"] += 1
            
            # Сбрасываем счётчик переподключений после успешного подключения
            reconnect_attempt = 0
            
            # Подписываемся на каждый батч отдельно (лимит Bybit: max 10 topics per subscribe)
            for batch_id, batch_symbols in batches:
                batch_args = [f"publicTrade.{sym}" for sym in batch_symbols]
                subscribe_msg = {"op": "subscribe", "args": batch_args}
                await ws.send_json(subscribe_msg)
                await asyncio.sleep(0.01)  # Небольшая задержка между подписками
            
            # Запускаем heartbeat задачу
            async def ping_task_worker():
                while True:
                    await asyncio.sleep(WS_PING_INTERVAL_SEC)
                    try:
                        # Проверяем, что соединение не закрыто перед отправкой ping
                        if ws.closed:
                            break
                        await ws.send_json({"op": "ping"})
                    except Exception:
                        break
            
            ping_task = asyncio.create_task(ping_task_worker())
            
            # Читаем сообщения
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    if "topic" in data:
                        topic = data["topic"]
                        if topic.startswith("publicTrade."):
                            symbol = topic.replace("publicTrade.", "")
                            trade_list = data.get("data", [])
                            for trade in trade_list:
                                try:
                                    price = float(trade["p"])
                                    qty = float(trade["v"])
                                    trade_ts = int(trade["T"])
                                    
                                    if _builder:
                                        finished = await _builder.add_trade(
                                            exchange="bybit",
                                            market=market,
                                            symbol=symbol,
                                            price=price,
                                            qty=qty,
                                            ts_ms=trade_ts,
                                        )
                                        
                                        if finished is not None:
                                            await on_candle(finished)
                                except Exception as e:
                                    logger.error(f"Ошибка парсинга сделки: {e}")
                    
                    elif "op" in data:
                        op = data["op"]
                        if op == "subscribe":
                            success = data.get("success")
                            if not success:
                                error_msg = data.get("retMsg") or data.get("message") or "Unknown error"
                                logger.error(
                                    f"Ошибка подписки Bybit {connection_id}: {error_msg}",
                                    extra={
                                        "log_to_db": True,
                                        "error_type": "subscribe_error",
                                        "exchange": "bybit",
                                        "market": market,
                                        "connection_id": connection_id,
                                        "error": error_msg,
                                    }
                                )
                        elif op == "pong":
                            # Подтверждение ping - ничего не делаем
                            pass
                
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    logger.debug(f"WebSocket {connection_id} закрыт (CLOSE)")
                    # Переподключение будет подсчитано в начале следующей итерации цикла
                    # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                    break
                
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning(f"WebSocket {connection_id} ошибка (ERROR)")
                    # Переподключение будет подсчитано в начале следующей итерации цикла
                    # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                    break
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка в WS соединении {connection_id}: {e}")
            await on_error({
                "exchange": "bybit",
                "market": market,
                "connection_id": connection_id,
                "error": str(e),
            })
        finally:
            if connected:
                _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                # Сбрасываем флаг подключения при выходе
                was_connected = False
            if ping_task:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
            # Явно закрываем WebSocket, если он ещё открыт
            if 'ws' in locals() and not ws.closed:
                try:
                    await ws.close()
                except Exception:
                    pass


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
    
    # Получаем callback для подсчёта трейдов, если передан
    on_trade = kwargs.get('on_trade', None)
    # Создаём CandleBuilder
    _builder = CandleBuilder(maxlen=config.memory_max_candles_per_symbol, on_trade=on_trade)
    
    # Создаём сессию с SSL сертификатами из certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    _session = aiohttp.ClientSession(connector=connector)
    
    # Проверяем конфигурацию и получаем символы только для включенных рынков
    fetch_spot = config.exchanges.bybit_spot
    fetch_linear = config.exchanges.bybit_linear
    
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
    
    # Запускаем WebSocket соединения для обоих рынков
    _tasks = []
    _spot_tasks = []
    _linear_tasks = []
    
    if fetch_spot and spot_symbols:
        _stats["spot"]["active_symbols"] = len(spot_symbols)
        
        # Создаём соединения для SPOT
        for conn_idx in range(0, len(spot_symbols), WS_SYMBOLS_PER_CONNECTION_SPOT):
            connection_symbols = spot_symbols[conn_idx:conn_idx+WS_SYMBOLS_PER_CONNECTION_SPOT]
            connection_id = f"SPOT#{len(_spot_tasks) + 1}"
            
            # Создаём батчи внутри этого соединения (10 символов на батч для SPOT)
            batches_in_conn = []
            for batch_idx in range(0, len(connection_symbols), BATCH_SIZE_SPOT):
                batch_symbols = connection_symbols[batch_idx:batch_idx+BATCH_SIZE_SPOT]
                batch_id = f"{connection_id}-B{batch_idx//BATCH_SIZE_SPOT + 1}"
                batches_in_conn.append((batch_id, batch_symbols))
            
            task = asyncio.create_task(_ws_consumer_with_batches(
                market="spot",
                connection_id=connection_id,
                all_symbols=connection_symbols,
                batches=batches_in_conn,
                session=_session,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _spot_tasks.append(task)
            await asyncio.sleep(0.1)  # Небольшая задержка между соединениями
    
    if fetch_linear and linear_symbols:
        _stats["linear"]["active_symbols"] = len(linear_symbols)
        
        # Создаём соединения для LINEAR
        for conn_idx in range(0, len(linear_symbols), WS_SYMBOLS_PER_CONNECTION_LINEAR):
            connection_symbols = linear_symbols[conn_idx:conn_idx+WS_SYMBOLS_PER_CONNECTION_LINEAR]
            connection_id = f"LINEAR#{len(_linear_tasks) + 1}"
            
            # Создаём один батч со всеми символами для LINEAR
            batches_in_conn = [(connection_id, connection_symbols)]
            
            task = asyncio.create_task(_ws_consumer_with_batches(
                market="linear",
                connection_id=connection_id,
                all_symbols=connection_symbols,
                batches=batches_in_conn,
                session=_session,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _linear_tasks.append(task)
            await asyncio.sleep(0.1)
    
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
    
    logger.info("Все соединения Bybit остановлены")


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

