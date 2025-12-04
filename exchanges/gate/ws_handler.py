"""
WebSocket обработчик для Gate.io
Адаптация существующего Gate к стандарту NEWEX.md
"""
import ssl
import certifi
import asyncio
import time
import sys
from typing import Awaitable, Callable, List, Dict, Set
import websockets
import json
import socket
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from core.symbol_cache_logger import report_symbol_cache_update
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
# Символы хранятся в памяти в переменных spot_symbols, linear_symbols и symbols
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

# Глобальные переменные для хранения актуальных списков символов
_active_spot_symbols: List[str] = []
_active_linear_symbols: List[str] = []
_symbol_update_lock: asyncio.Lock | None = None
# Словарь для отслеживания соединений: connection_id -> (websocket, symbols_list, market)
_active_connections: Dict[str, tuple] = {}


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
    
    Args:
        symbols: Список символов для подписки
        market: Тип рынка ("spot" или "linear")
        connection_id: Уникальный идентификатор соединения
        on_candle: Callback для обработки завершённых свечей
        on_error: Callback для обработки ошибок
    
    Примечание:
        Функция содержит логику автоматического переподключения при обрыве соединения,
        обработку ошибок, отправку ping сообщений для поддержания соединения.
    """
    import random
    
    ws_url = SPOT_WS_URL if market == "spot" else LINEAR_WS_URL
    reconnect_delay = RECONNECT_DELAY
    reconnect_attempt = 0
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        # Переподключение считается, если:
        # 1. Это не первая попытка (reconnect_attempt > 1), ИЛИ
        # 2. Это первая попытка, но соединение было установлено ранее (was_connected = True)
        is_reconnect = reconnect_attempt > 1 or was_connected
        
        try:
            if is_reconnect:
                # Обновляем список символов перед переподключением
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        fresh_symbols = await fetch_symbols(market)
                        if market == "spot":
                            _active_spot_symbols[:] = fresh_symbols
                        else:
                            _active_linear_symbols[:] = fresh_symbols
                        
                        # Фильтруем symbols, оставляя только актуальные символы
                        active_symbols_set = set(fresh_symbols)
                        valid_symbols = [s for s in symbols if s in active_symbols_set]
                        
                        removed_count = len(symbols) - len(valid_symbols)
                        if removed_count > 0:
                            logger.info(
                                f"Gate {market} {connection_id}: "
                                f"при переподключении удалено {removed_count} неактуальных символов"
                            )
                        symbols[:] = valid_symbols
                
                # Увеличиваем счётчик реконнектов при любом реконнекте (включая аномальные закрытия)
                _stats[market]["reconnects"] += 1
                logger.info(f"Gate {connection_id}: переподключение (счётчик: {_stats[market]['reconnects']})")
                
                # Счётчик переподключений увеличивается при входе в новый блок async with
                # (см. строку 211), чтобы избежать двойного подсчёта
                
                # Определяем причину переподключения
                reconnect_reason = "normal"
                
                await on_error({
                    "exchange": "gate",
                    "market": market,
                    "connection_id": connection_id,
                    "type": "reconnect",
                    "reason": reconnect_reason,
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
                
                # Регистрируем соединение для динамических обновлений
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        _active_connections[connection_id] = (websocket, symbols, market)
                
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
                    # Создаем snapshot списка для защиты от изменения во время итерации
                    symbols_snapshot = list(symbols)
                    for i, symbol in enumerate(symbols_snapshot):
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
                        if i < len(symbols_snapshot) - 1:
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
                            
                            # Обработка ошибок подписки
                            if message_dict.get("event") == "error" or message_dict.get("error"):
                                error_msg = message_dict.get("error") or message_dict.get("message") or "Unknown error"
                                logger.error(f"Gate {connection_id}: ошибка подписки: {error_msg}")
                                
                                # Если ошибка связана с несуществующими символами, удаляем их
                                if isinstance(error_msg, str) and any(phrase in error_msg.lower() for phrase in ["invalid", "not exist", "not found", "doesn't exist", "not available"]):
                                    # Пытаемся извлечь проблемный символ из payload или channel
                                    problematic_symbols = []
                                    payload = message_dict.get("payload")
                                    if payload:
                                        if isinstance(payload, list):
                                            problematic_symbols = payload
                                        elif isinstance(payload, str):
                                            problematic_symbols = [payload]
                                    
                                    # Если не удалось извлечь, проверяем последний подписанный символ
                                    if not problematic_symbols and symbols:
                                        problematic_symbols = [symbols[-1]]  # Берем последний подписанный символ
                                    
                                    # Удаляем проблемные символы
                                    if problematic_symbols:
                                        removed = []
                                        for symbol in problematic_symbols:
                                            if symbol in symbols:
                                                symbols.remove(symbol)
                                                removed.append(symbol)
                                                logger.info(
                                                    f"Gate {connection_id}: "
                                                    f"символ {symbol} будет удален из списка подписки (не существует на бирже)"
                                                )
                                        
                                        if removed:
                                            logger.warning(
                                                f"Gate {connection_id}: "
                                                f"удалены символы из списка подписки: {', '.join(removed)}"
                                            )
                                            
                                            # Если все символы были удалены, прекращаем работу
                                            if not symbols:
                                                logger.warning(
                                                    f"Gate {connection_id}: "
                                                    f"все символы были удалены, прекращаем работу соединения"
                                                )
                                                break
                                
                                await on_error({
                                    "exchange": "gate",
                                    "market": market,
                                    "connection_id": connection_id,
                                    "type": "subscribe_error",
                                    "error": error_msg,
                                })
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
                                        size = _safe_float(trade.get("size", "0"))  # size уже в USDT для фьючерсов Gate.io
                                        price = _safe_float(price_str) if price_str else 0.0
                                        # Для фьючерсов Gate.io: size в USDT, нужно делить на цену для получения базовой валюты
                                        amount = abs(size) / price if price > 0 else 0.0
                                        
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
                    # Удаляем соединение из регистрации
                    if _symbol_update_lock:
                        async with _symbol_update_lock:
                            _active_connections.pop(connection_id, None)
                    
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
        except (ConnectionResetError, ConnectionError) as e:
            # Обработка ConnectionResetError (WinError 10054) - соединение принудительно закрыто удаленным хостом
            error_msg = f"Соединение принудительно закрыто удаленным хостом: {e}"
            logger.warning(f"Gate {connection_id}: {error_msg}")
            await on_error({
                "exchange": "gate",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "error_type": "connection_reset",
            })
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


async def _update_symbols_periodically(
    market: str,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
    config: AppConfig,
):
    """
    Периодически обновляет список символов и управляет подписками.
    
    Args:
        market: Тип рынка ("spot" или "linear")
        on_candle: Callback для обработки свечей
        on_error: Callback для обработки ошибок
        config: Конфигурация приложения
    """
    global _tasks
    
    # Ждём 5 минут перед первым обновлением
    await asyncio.sleep(300)
    
    while True:
        try:
            # Запрашиваем актуальный список символов
            new_symbols = await fetch_symbols(market)
            new_symbols_set = set(new_symbols)
            
            if not _symbol_update_lock:
                await asyncio.sleep(300)
                continue
            
            async with _symbol_update_lock:
                # Получаем старый список
                if market == "spot":
                    old_symbols = _active_spot_symbols.copy()
                    _active_spot_symbols[:] = new_symbols
                else:
                    old_symbols = _active_linear_symbols.copy()
                    _active_linear_symbols[:] = new_symbols
                
                old_symbols_set = set(old_symbols)
                
                # Находим удаленные и новые символы
                removed_symbols = old_symbols_set - new_symbols_set
                added_symbols = new_symbols_set - old_symbols_set
                
                # Логируем обновление кэша символов через централизованный логгер
                has_changes = bool(removed_symbols or added_symbols)
                await report_symbol_cache_update(
                    exchange="Gate",
                    market=market,
                    has_changes=has_changes,
                    removed_count=len(removed_symbols),
                    added_count=len(added_symbols),
                    total_symbols=len(new_symbols)
                )
                
                # Обрабатываем удаленные символы
                for symbol in removed_symbols:
                    # Находим все соединения, содержащие этот символ
                    connections_to_update = []
                    for conn_id, (websocket, symbols_list, conn_market) in _active_connections.items():
                        if conn_market == market and symbol in symbols_list:
                            connections_to_update.append((conn_id, websocket, symbols_list))
                    
                    # Удаляем символ из всех соединений и отписываемся
                    for conn_id, websocket, symbols_list in connections_to_update:
                        if symbol in symbols_list:
                            symbols_list.remove(symbol)
                            logger.info(
                                f"Gate {market}: символ {symbol} удален с биржи, "
                                f"отписываемся от {conn_id}"
                            )
                            
                            # Отправляем unsubscribe
                            try:
                                channel = "spot.trades" if market == "spot" else "futures.trades"
                                unsubscribe_msg = {
                                    "time": int(time.time()),
                                    "channel": channel,
                                    "event": "unsubscribe",
                                    "payload": [symbol],
                                }
                                await websocket.send(json.dumps(unsubscribe_msg))
                            except (websockets.exceptions.ConnectionClosed, Exception) as e:
                                logger.warning(
                                    f"Gate {market} [{conn_id}]: "
                                    f"ошибка при отписке от {symbol}: {e}"
                                )
                
                # Обрабатываем новые символы
                for symbol in added_symbols:
                    # Находим соединение с наименьшим количеством символов (но меньше лимита)
                    best_connection = None
                    best_conn_id = None
                    best_symbols = None
                    min_count = SPOT_SYMBOLS_PER_CONNECTION if market == "spot" else LINEAR_SYMBOLS_PER_CONNECTION
                    
                    for conn_id, (websocket, symbols_list, conn_market) in _active_connections.items():
                        if conn_market == market:
                            limit = SPOT_SYMBOLS_PER_CONNECTION if market == "spot" else LINEAR_SYMBOLS_PER_CONNECTION
                            if len(symbols_list) < limit:
                                if len(symbols_list) < min_count:
                                    min_count = len(symbols_list)
                                    best_connection = websocket
                                    best_conn_id = conn_id
                                    best_symbols = symbols_list
                    
                    if best_connection:
                        # Добавляем символ в существующее соединение
                        best_symbols.append(symbol)
                        
                        # Отправляем subscribe
                        try:
                            channel = "spot.trades" if market == "spot" else "futures.trades"
                            subscribe_msg = {
                                "time": int(time.time()),
                                "channel": channel,
                                "event": "subscribe",
                                "payload": [symbol],
                            }
                            await best_connection.send(json.dumps(subscribe_msg))
                            logger.info(
                                f"Gate {market}: новый символ {symbol} добавлен, "
                                f"подписываемся в {best_conn_id}"
                            )
                        except (websockets.exceptions.ConnectionClosed, Exception) as e:
                            logger.warning(
                                f"Gate {market} [{best_conn_id}]: "
                                f"ошибка при подписке на {symbol}: {e}"
                            )
                            # Удаляем символ из списка при ошибке
                            if symbol in best_symbols:
                                best_symbols.remove(symbol)
                    else:
                        # Все соединения заполнены или нет соединений - создаем новое
                        logger.info(
                            f"Gate {market}: новый символ {symbol} добавлен, "
                            f"создаем новое соединение"
                        )
                        # Собираем все новые символы, которые не поместились
                        new_symbols_to_add = [s for s in added_symbols if s not in [
                            sym for _, symbols_list, m in _active_connections.values() 
                            if m == market for sym in symbols_list
                        ]]
                        
                        if new_symbols_to_add:
                            # Разбиваем на соединения
                            symbols_per_conn = SPOT_SYMBOLS_PER_CONNECTION if market == "spot" else LINEAR_SYMBOLS_PER_CONNECTION
                            for i in range(0, len(new_symbols_to_add), symbols_per_conn):
                                symbols_batch = new_symbols_to_add[i:i+symbols_per_conn]
                                symbols_batch = list(symbols_batch)
                                connection_id = f"{market.upper()}-WS-{len(_tasks) + i // symbols_per_conn + 1}"
                                
                                # Создаем новое соединение
                                task = asyncio.create_task(_ws_connection_worker(
                                    symbols=symbols_batch,
                                    market=market,
                                    connection_id=connection_id,
                                    on_candle=on_candle,
                                    on_error=on_error,
                                ))
                                _tasks.append(task)
                                
                                logger.info(
                                    f"Gate {market}: создано новое соединение {connection_id} "
                                    f"для {len(symbols_batch)} символов"
                                )
        
        except Exception as e:
            logger.error(f"Ошибка при обновлении символов Gate {market}: {e}", exc_info=True)
        
        # Ждём 5 минут до следующего обновления
        await asyncio.sleep(300)


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
    _builder = CandleBuilder(
        maxlen=config.memory_max_candles_per_symbol,
        on_trade=on_trade,
        on_candle=on_candle,
    )
    
    _tasks = []
    
    # Инициализируем lock если еще не инициализирован
    global _symbol_update_lock
    if _symbol_update_lock is None:
        _symbol_update_lock = asyncio.Lock()
    
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
    
    # Инициализируем глобальные списки символов
    async with _symbol_update_lock:
        _active_spot_symbols[:] = spot_symbols
        _active_linear_symbols[:] = linear_symbols
    
    # Запускаем SPOT
    if fetch_spot and spot_symbols:
        _stats["spot"]["active_symbols"] = len(spot_symbols)
        
        # Автоматически создаём столько соединений, сколько нужно
        for i in range(0, len(spot_symbols), SPOT_SYMBOLS_PER_CONNECTION):
            chunk = spot_symbols[i:i + SPOT_SYMBOLS_PER_CONNECTION]
            # Создаем изменяемый список для батча (чтобы можно было обновлять при реконнекте)
            symbols_batch = list(chunk)
            connection_id = f"SPOT#{i // SPOT_SYMBOLS_PER_CONNECTION}"
            task = asyncio.create_task(_ws_connection_worker(
                symbols=symbols_batch,
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
            # Создаем изменяемый список для батча (чтобы можно было обновлять при реконнекте)
            symbols_batch = list(chunk)
            connection_id = f"LINEAR#{i // LINEAR_SYMBOLS_PER_CONNECTION}"
            task = asyncio.create_task(_ws_connection_worker(
                symbols=symbols_batch,
                market="linear",
                connection_id=connection_id,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            await asyncio.sleep(DELAY_BETWEEN_WS)
    
    # Запускаем задачи периодического обновления символов
    if fetch_spot:
        update_task_spot = asyncio.create_task(
            _update_symbols_periodically("spot", on_candle, on_error, config)
        )
        _tasks.append(update_task_spot)
    
    if fetch_linear:
        update_task_linear = asyncio.create_task(
            _update_symbols_periodically("linear", on_candle, on_error, config)
        )
        _tasks.append(update_task_linear)
    
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

