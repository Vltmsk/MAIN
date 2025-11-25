"""
WebSocket обработчик для Bitget
Краткая упрощённая версия для демонстрации стандарта
"""
import ssl
import certifi
import asyncio
import math
import random
from typing import Awaitable, Callable, List
import aiohttp
import json
import socket
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from .symbol_fetcher import fetch_symbols

logger = get_logger(__name__)

BITGET_WS_URL = "wss://ws.bitget.com/v2/ws/public"

# Общие параметры WebSocket
PING_INTERVAL_SEC = 30  # Интервал отправки ping
PING_GRACE_SEC = 120  # Максимальное время ожидания pong

# Параметры подключения
CONNECT_CONCURRENCY = 3  # Максимум параллельных подключений
WS_STAGGER_SEC = 5.0  # Базовая задержка между подключениями WS
WS_STAGGER_JITTER_SEC = 1.2  # Случайная добавка к задержке подключения
SUBSCRIBE_DELAY_PER_WS_SEC = 3.5  # Задержка перед подпиской после подключения
SUBSCRIBE_DELAY_JITTER_SEC = 1.0  # Случайная добавка к задержке подписки

# Параметры подписки
SUBSCRIBE_CHUNK_SIZE = 19  # Размер чанка при подписке на пары
SUBSCRIBE_CHUNK_PAUSE_SEC = 0.30  # Пауза между чанками подписки

# SPOT параметры
BATCH_SIZE = 39  # Количество пар на одно соединение

# Фьючерсы параметры
FUT_BATCH_SIZE = 100  # Количество пар на одно соединение

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


def _safe_float(x) -> float:
    """Безопасное преобразование в float."""
    try:
        return float(x)
    except Exception:
        return math.nan


async def _ws_batch_worker(
    batch_id: int,
    symbols: List[str],
    market: str,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
):
    """
    WebSocket worker для одного батча символов.
    """
    reconnect_attempt = 0
    first_message_for_symbol = {}  # Отслеживаем первое сообщение для каждого символа
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        was_reconnecting = False
        
        try:
            if reconnect_attempt > 1:
                was_reconnecting = True
                # Очищаем словарь при реконнекте, чтобы получить первое сообщение для каждого символа
                # Это необходимо, так как биржа отправляет исторические данные при реконнекте
                first_message_for_symbol.clear()
                delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                _stats[market]["reconnects"] += 1
                await on_error({
                    "exchange": "bitget",
                    "market": market,
                    "connection_id": f"batch-{batch_id}",
                    "type": "reconnect",
                })
                await asyncio.sleep(delay)
            
            # Проверяем, что сессия инициализирована и не закрыта
            if _session is None or _session.closed:
                logger.error(f"Bitget {market} batch-{batch_id}: сессия не инициализирована или закрыта")
                await asyncio.sleep(5)
                continue
            
            async with _session.ws_connect(
                BITGET_WS_URL,
                heartbeat=None,
                timeout=30,
                receive_timeout=PING_GRACE_SEC,
                autoclose=True,
                autoping=False,
                max_msg_size=0
            ) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                was_connected = True  # Устанавливаем флаг успешного подключения
                
                _stats[market]["active_connections"] += 1
                
                # Задержка перед подпиской после подключения
                subscribe_delay = SUBSCRIBE_DELAY_PER_WS_SEC + random.uniform(0, SUBSCRIBE_DELAY_JITTER_SEC)
                await asyncio.sleep(subscribe_delay)
                
                # Подписываемся по чанкам
                inst_type = "SPOT" if market == "spot" else "USDT-FUTURES"
                
                # Словарь для отслеживания подтверждений подписки
                subscription_confirmations = {}
                
                # Разбиваем символы на чанки для подписки
                for chunk_start in range(0, len(symbols), SUBSCRIBE_CHUNK_SIZE):
                    chunk = symbols[chunk_start:chunk_start + SUBSCRIBE_CHUNK_SIZE]
                    args = [{"instType": inst_type, "channel": "trade", "instId": s} for s in chunk]
                    subscribe_msg = {"op": "subscribe", "args": args}
                    await ws.send_json(subscribe_msg)
                    
                    # Сохраняем информацию о подписке для проверки подтверждения
                    for symbol in chunk:
                        subscription_confirmations[symbol] = False
                    
                    # Пауза между чанками (кроме последнего)
                    if chunk_start + SUBSCRIBE_CHUNK_SIZE < len(symbols):
                        await asyncio.sleep(SUBSCRIBE_CHUNK_PAUSE_SEC)
                
                # Запускаем heartbeat
                async def heartbeat_loop():
                    while True:
                        try:
                            await asyncio.sleep(PING_INTERVAL_SEC)
                            await ws.send_str("ping")
                        except Exception:
                            break
                
                heartbeat_task = asyncio.create_task(heartbeat_loop())
                
                # Счётчик таймаутов для отслеживания проблем с соединением
                timeout_count = 0
                max_timeouts_before_reconnect = 3  # Максимум таймаутов перед реконнектом
                
                try:
                    # Читаем сообщения
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.receive(), timeout=PING_GRACE_SEC)
                            # Сбрасываем счётчик таймаутов при успешном получении сообщения
                            timeout_count = 0
                        except asyncio.TimeoutError:
                            timeout_count += 1
                            if timeout_count >= max_timeouts_before_reconnect:
                                logger.warning(
                                    f"Bitget {market} batch-{batch_id}: "
                                    f"превышен лимит таймаутов ({max_timeouts_before_reconnect}), "
                                    f"переподключение..."
                                )
                                # Переподключение будет подсчитано в начале следующей итерации цикла
                                # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                                break
                            continue
                        
                        if msg.type == aiohttp.WSMsgType.CLOSED:
                            close_code = getattr(msg, 'data', None)
                            logger.warning(
                                f"Bitget {market} batch-{batch_id}: WebSocket закрыт (CLOSED), "
                                f"код: {close_code}"
                            )
                            # Переподключение будет подсчитано в начале следующей итерации цикла
                            # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                            break
                        
                        if msg.type == aiohttp.WSMsgType.ERROR:
                            error_data = getattr(msg, 'data', None)
                            logger.error(
                                f"Bitget {market} batch-{batch_id}: WebSocket ошибка (ERROR), "
                                f"данные: {error_data}"
                            )
                            # Переподключение будет подсчитано в начале следующей итерации цикла
                            # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                            break
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            txt = msg.data
                            if isinstance(txt, str) and txt.strip().lower() == "pong":
                                continue
                            
                            try:
                                data = json.loads(txt)
                            except Exception:
                                continue
                            
                            # Проверяем подтверждение подписки
                            if data.get("event") == "subscribe" or data.get("op") == "subscribe":
                                code = data.get("code")
                                # Проверяем, успешна ли подписка
                                # code может быть "0", 0, или отсутствовать (тогда считаем успешной)
                                is_success = (
                                    code == "0" or 
                                    code == 0 or 
                                    code is None  # Если code отсутствует, но есть event/op=subscribe, считаем успешной
                                )
                                
                                if is_success:
                                    # Подписка успешна
                                    args_list = data.get("arg", [])
                                    if isinstance(args_list, list):
                                        for arg_item in args_list:
                                            if isinstance(arg_item, dict):
                                                inst_id = arg_item.get("instId")
                                                if inst_id:
                                                    subscription_confirmations[inst_id] = True
                                    elif isinstance(args_list, dict):
                                        inst_id = args_list.get("instId")
                                        if inst_id:
                                            subscription_confirmations[inst_id] = True
                                else:
                                    # Ошибка подписки
                                    error_code = code if code is not None else "нет кода"
                                    error_msg = data.get("msg", "Unknown error")
                                    # Получаем информацию о символе для более детального логирования
                                    args_list = data.get("arg", [])
                                    symbol_info = "unknown"
                                    if isinstance(args_list, list) and args_list:
                                        symbol_info = ", ".join([arg.get("instId", "?") for arg in args_list if isinstance(arg, dict)])
                                    elif isinstance(args_list, dict):
                                        symbol_info = args_list.get("instId", "unknown")
                                    
                                    logger.warning(
                                        f"Bitget {market} batch-{batch_id}: "
                                        f"ошибка подписки на {symbol_info}: code={error_code}, msg={error_msg}, "
                                        f"полный ответ: {json.dumps(data, ensure_ascii=False)}"
                                    )
                            
                            # Обрабатываем trades
                            arg = data.get("arg")
                            rows = data.get("data")
                            if arg and rows and isinstance(rows, list) and arg.get("channel") == "trade":
                                sym = arg.get("instId")
                                
                                # Отмечаем, что подписка работает (получили данные)
                                if sym:
                                    subscription_confirmations[sym] = True
                                
                                # Проверяем, это первое сообщение для символа
                                if sym and sym not in first_message_for_symbol:
                                    first_message_for_symbol[sym] = True
                                    # Пропускаем первое сообщение (это исторические данные)
                                    continue
                                
                                for tr in rows:
                                    if not isinstance(tr, dict):
                                        continue
                                    
                                    px = _safe_float(tr.get("px") or tr.get("price"))
                                    sz = _safe_float(tr.get("sz") or tr.get("size"))
                                    ts_raw = tr.get("ts") or tr.get("timestamp")
                                    # Используем truthiness проверку вместо is not None, чтобы обработать пустые строки
                                    ts_ms = int(ts_raw) if ts_raw else 0
                                    
                                    # Проверяем валидность данных: цена не NaN, размер > 0, timestamp > 0
                                    if (not math.isnan(px) and not math.isnan(sz) and 
                                        sz > 0.0 and ts_ms > 0):
                                        if _builder:
                                            finished = await _builder.add_trade(
                                                exchange="bitget",
                                                market=market,
                                                symbol=sym,
                                                price=px,
                                                qty=sz,  # Убрали abs(), т.к. уже проверяем sz > 0.0
                                                ts_ms=ts_ms,
                                            )
                                            if finished is not None:
                                                await on_candle(finished)
                
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                
                _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                # Сбрасываем флаг подключения при выходе из контекста WebSocket
                was_connected = False
                
        except asyncio.CancelledError:
            break
        except (ConnectionResetError, ConnectionError) as e:
            # Обработка ConnectionResetError (WinError 10054) - соединение принудительно закрыто удаленным хостом
            error_msg = f"Соединение принудительно закрыто удаленным хостом: {e}"
            logger.warning(f"Bitget {market} batch-{batch_id}: {error_msg}")
            await on_error({
                "exchange": "bitget",
                "market": market,
                "connection_id": f"batch-{batch_id}",
                "error": error_msg,
                "error_type": "connection_reset",
            })
        except Exception as e:
            # Если это была попытка реконнекта, ошибка уже залогирована через on_error выше
            # Не логируем повторно, просто переходим к следующей итерации
            if not was_reconnecting:
                # Если это первая попытка или другая ошибка, логируем
                logger.error(f"Ошибка в WS соединении Bitget {batch_id}: {e}")
                await on_error({
                    "exchange": "bitget",
                    "market": market,
                    "batch_id": batch_id,
                    "error": str(e),
                })
            # При ошибке соединения просто переходим к следующей итерации (реконнект)


async def start(
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
    config: AppConfig,
    **kwargs  # Для совместимости с возможными дополнительными параметрами
) -> List[asyncio.Task]:
    """
    Запускает WebSocket клиенты для spot и linear рынков.
    """
    global _builder, _tasks, _spot_tasks, _linear_tasks, _session
    
    # Получаем callback для подсчёта трейдов, если передан
    on_trade = kwargs.get('on_trade', None)
    # Создаём сессию с SSL сертификатами из certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    _session = aiohttp.ClientSession(connector=connector)
    _builder = CandleBuilder(
        maxlen=config.memory_max_candles_per_symbol,
        on_trade=on_trade,
        on_candle=on_candle,
    )
    
    # Проверяем конфигурацию и получаем символы только для включенных рынков
    fetch_spot = config.exchanges.bitget_spot
    fetch_linear = config.exchanges.bitget_linear
    
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
    batch_id = 1
    
    # Семафор для ограничения параллельных подключений
    semaphore = asyncio.Semaphore(CONNECT_CONCURRENCY)
    
    # Функция для запуска батча с ограничением конкуренции
    async def _create_connection_task(
        batch_id: int,
        symbols_batch: List[str],
        market: str,
    ):
        """Создает задачу подключения с учетом лимита конкуренции"""
        async with semaphore:
            task = asyncio.create_task(_ws_batch_worker(
                batch_id=batch_id,
                symbols=symbols_batch,
                market=market,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            # Отдельно отслеживаем задачи по рынкам для статистики
            if market == "spot":
                _spot_tasks.append(task)
            else:
                _linear_tasks.append(task)
    
    # Запускаем SPOT с ограничением параллельности и задержками
    if fetch_spot and spot_symbols:
        _stats["spot"]["active_symbols"] = len(spot_symbols)
        
        for i in range(0, len(spot_symbols), BATCH_SIZE):
            symbols_batch = spot_symbols[i:i+BATCH_SIZE]
            
            # Запускаем подключение (семафор ограничит параллельность)
            await _create_connection_task(batch_id, symbols_batch, "spot")
            batch_id += 1
            
            # Задержка между подключениями (кроме последнего)
            if i + BATCH_SIZE < len(spot_symbols):
                stagger_delay = WS_STAGGER_SEC + random.uniform(0, WS_STAGGER_JITTER_SEC)
                await asyncio.sleep(stagger_delay)
    
    # Запускаем LINEAR с ограничением параллельности и задержками
    if fetch_linear and linear_symbols:
        _stats["linear"]["active_symbols"] = len(linear_symbols)
        
        for i in range(0, len(linear_symbols), FUT_BATCH_SIZE):
            symbols_batch = linear_symbols[i:i+FUT_BATCH_SIZE]
            
            # Запускаем подключение (семафор ограничит параллельность)
            await _create_connection_task(batch_id, symbols_batch, "linear")
            batch_id += 1
            
            # Задержка между подключениями (кроме последнего)
            if i + FUT_BATCH_SIZE < len(linear_symbols):
                stagger_delay = WS_STAGGER_SEC + random.uniform(0, WS_STAGGER_JITTER_SEC)
                await asyncio.sleep(stagger_delay)
    
    return list(_tasks)


async def stop(tasks: List[asyncio.Task]) -> None:
    """Останавливает все WebSocket соединения."""
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
    
    logger.info("Все соединения Bitget остановлены")


def get_statistics() -> dict:
    """Возвращает статистику."""
    # Обновляем статистику активных соединений на основе отдельных списков задач
    _stats["spot"]["active_connections"] = len([t for t in _spot_tasks if not t.done()])
    _stats["linear"]["active_connections"] = len([t for t in _linear_tasks if not t.done()])
    return _stats

