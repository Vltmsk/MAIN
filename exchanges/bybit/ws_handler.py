"""
WebSocket обработчик для Bybit
"""
import ssl
import certifi
import asyncio
from typing import Awaitable, Callable, List, Dict, Set
import aiohttp
import json
import socket
from config import AppConfig
from core.candle_builder import CandleBuilder, Candle
from core.logger import get_logger
from core.symbol_cache_logger import report_symbol_cache_update
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
# Символы хранятся в памяти в переменных spot_symbols, linear_symbols и all_symbols
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
# Словарь для отслеживания соединений: connection_id -> (ws, all_symbols, batches, market)
_active_connections: Dict[str, tuple] = {}


async def _ws_consumer_with_batches(
    market: str,
    connection_id: str,
    all_symbols: List[str],  # Изменяемый список символов
    batches: List[tuple],  # Изменяемый список батчей
    session: aiohttp.ClientSession,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
):
    """
    WebSocket consumer для одного соединения с несколькими батчами внутри.
    
    Args:
        market: Тип рынка ("spot" или "linear")
        connection_id: Уникальный идентификатор соединения
        all_symbols: Полный список всех символов
        batches: Список кортежей (batch_id, symbols) - батчи символов для подписки
        session: HTTP сессия для WebSocket соединения
        on_candle: Callback для обработки завершённых свечей
        on_error: Callback для обработки ошибок
    
    Примечание:
        Функция подписывается на каждый батч отдельно из-за лимита Bybit на количество символов
        в одной подписке. Каждый батч обрабатывается в отдельном WebSocket соединении.
    """
    global _builder
    
    ws_url = WS_SPOT if market == "spot" else WS_LINEAR
    
    reconnect_attempt = 0
    max_reconnect_delay = 60
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        # Переподключение считается, если:
        # 1. Это не первая попытка (reconnect_attempt > 1), ИЛИ
        # 2. Это первая попытка, но соединение было установлено ранее (was_connected = True)
        is_reconnect = reconnect_attempt > 1 or was_connected
        
        if is_reconnect:
            # Обновляем список символов перед переподключением
            if _symbol_update_lock:
                async with _symbol_update_lock:
                    fresh_symbols = await fetch_symbols(market)
                    if market == "spot":
                        _active_spot_symbols[:] = fresh_symbols
                    else:
                        _active_linear_symbols[:] = fresh_symbols
                    
                    # Фильтруем all_symbols, оставляя только актуальные символы
                    active_symbols_set = set(fresh_symbols)
                    valid_symbols = [s for s in all_symbols if s in active_symbols_set]
                    
                    removed_count = len(all_symbols) - len(valid_symbols)
                    if removed_count > 0:
                        logger.info(
                            f"Bybit {market} {connection_id}: "
                            f"при переподключении удалено {removed_count} неактуальных символов"
                        )
                    all_symbols[:] = valid_symbols
                    
                    # Пересоздаем batches из валидных символов
                    batches.clear()
                    if market == "spot":
                        for batch_idx in range(0, len(valid_symbols), BATCH_SIZE_SPOT):
                            batch_symbols = valid_symbols[batch_idx:batch_idx+BATCH_SIZE_SPOT]
                            batch_id = f"{connection_id}-B{batch_idx//BATCH_SIZE_SPOT + 1}"
                            batches.append((batch_id, batch_symbols))
                    else:  # linear - все в одном батче
                        batches.append((connection_id, valid_symbols))
            
            # Увеличиваем счётчик реконнектов при любом реконнекте (включая аномальные закрытия)
            _stats[market]["reconnects"] += 1
            logger.info(f"Bybit {market} {connection_id}: переподключение (счётчик: {_stats[market]['reconnects']})")
            
            delay = min(2 ** min(reconnect_attempt - 1, 5), max_reconnect_delay)
            # Счётчик переподключений увеличивается при входе в новый блок ws_connect
            # (см. строку 192), чтобы избежать двойного подсчёта
            
            # Определяем причину переподключения
            reconnect_reason = "normal"
            
            await on_error({
                "exchange": "bybit",
                "market": market,
                "connection_id": connection_id,
                "type": "reconnect",
                "reason": reconnect_reason,
            })
            await asyncio.sleep(delay)
        
        ping_task = None
        connected = False
        
        try:
            ws = await session.ws_connect(ws_url, heartbeat=60, timeout=aiohttp.ClientTimeout(total=180))
            connected = True
            was_connected = True  # Устанавливаем флаг успешного подключения
            
            # Регистрируем соединение для динамических обновлений
            if _symbol_update_lock:
                async with _symbol_update_lock:
                    _active_connections[connection_id] = (ws, all_symbols, batches, market)
            
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
                                
                                # Если ошибка связана с несуществующими символами, удаляем их из списка
                                if isinstance(error_msg, str) and any(phrase in error_msg.lower() for phrase in ["invalid", "not exist", "not found", "doesn't exist", "not available"]):
                                    # Пытаемся извлечь проблемные символы из ответа
                                    problematic_symbols = []
                                    if "req_id" in data:
                                        # Ищем в batches символы, которые могли вызвать ошибку
                                        # Bybit может не указывать конкретные символы, поэтому проверяем последний подписанный батч
                                        if batches:
                                            last_batch = batches[-1]
                                            if isinstance(last_batch, tuple) and len(last_batch) == 2:
                                                problematic_symbols = last_batch[1]  # Берем символы из последнего батча
                                    elif "args" in data:
                                        # Если есть args, извлекаем символы из них
                                        args = data.get("args", [])
                                        for arg in args:
                                            if isinstance(arg, str) and arg.startswith("publicTrade."):
                                                symbol = arg.replace("publicTrade.", "")
                                                problematic_symbols.append(symbol)
                                    
                                    # Если не удалось извлечь конкретные символы, используем все из текущих batches
                                    if not problematic_symbols and batches:
                                        for batch_id, batch_symbols in batches:
                                            problematic_symbols.extend(batch_symbols)
                                    
                                    # Удаляем проблемные символы из all_symbols и пересоздаем batches
                                    if problematic_symbols:
                                        # Создаем set для быстрой проверки
                                        problematic_set = set(problematic_symbols)
                                        removed = [s for s in all_symbols if s in problematic_set]
                                        
                                        # Удаляем проблемные символы из списка
                                        all_symbols[:] = [s for s in all_symbols if s not in problematic_set]
                                        
                                        if removed:
                                            for symbol in removed:
                                                logger.info(
                                                    f"Bybit {market} {connection_id}: "
                                                    f"символ {symbol} будет удален из списка подписки (не существует на бирже)"
                                                )
                                        
                                        if removed:
                                            # Пересоздаем batches из валидных символов
                                            batches.clear()
                                            # Создаем snapshot списка для защиты от изменения во время итерации
                                            all_symbols_snapshot = list(all_symbols)
                                            if market == "spot":
                                                for batch_idx in range(0, len(all_symbols_snapshot), BATCH_SIZE_SPOT):
                                                    batch_symbols = all_symbols_snapshot[batch_idx:batch_idx+BATCH_SIZE_SPOT]
                                                    batch_id = f"{connection_id}-B{batch_idx//BATCH_SIZE_SPOT + 1}"
                                                    batches.append((batch_id, batch_symbols))
                                            else:  # linear - все в одном батче
                                                batches.append((connection_id, all_symbols_snapshot))
                                            
                                            logger.warning(
                                                f"Bybit {market} {connection_id}: "
                                                f"удалены символы из списка подписки: {', '.join(removed[:10])}"
                                                f"{' и еще ' + str(len(removed) - 10) + ' символов' if len(removed) > 10 else ''}"
                                            )
                                            
                                            # Если все символы были удалены, прекращаем работу
                                            if not all_symbols:
                                                logger.warning(
                                                    f"Bybit {market} {connection_id}: "
                                                    f"все символы были удалены, прекращаем работу соединения"
                                                )
                                                break
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
        except (ConnectionResetError, ConnectionError) as e:
            # Обработка ConnectionResetError (WinError 10054) - соединение принудительно закрыто удаленным хостом
            error_msg = f"Соединение принудительно закрыто удаленным хостом: {e}"
            logger.warning(f"Bybit {connection_id}: {error_msg}")
            await on_error({
                "exchange": "bybit",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "error_type": "connection_reset",
            })
        except Exception as e:
            logger.error(f"Ошибка в WS соединении {connection_id}: {e}")
            await on_error({
                "exchange": "bybit",
                "market": market,
                "connection_id": connection_id,
                "error": str(e),
            })
        finally:
            # Удаляем соединение из регистрации
            if _symbol_update_lock:
                async with _symbol_update_lock:
                    _active_connections.pop(connection_id, None)
            
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


async def _update_symbols_periodically(
    market: str,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
    config: AppConfig,
    session: aiohttp.ClientSession,
):
    """
    Периодически обновляет список символов и управляет подписками.
    
    Args:
        market: Тип рынка ("spot" или "linear")
        on_candle: Callback для обработки свечей
        on_error: Callback для обработки ошибок
        config: Конфигурация приложения
        session: HTTP сессия для WebSocket соединения
    """
    global _tasks, _spot_tasks, _linear_tasks
    
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
                    exchange="Bybit",
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
                    for conn_id, (ws, all_syms, batches_list, conn_market) in _active_connections.items():
                        if conn_market == market and symbol in all_syms:
                            connections_to_update.append((conn_id, ws, all_syms, batches_list))
                    
                    # Удаляем символ из всех соединений и отписываемся
                    for conn_id, ws, all_syms, batches_list in connections_to_update:
                        if symbol in all_syms:
                            all_syms.remove(symbol)
                            logger.info(
                                f"Bybit {market}: символ {symbol} удален с биржи, "
                                f"отписываемся от {conn_id}"
                            )
                            
                            # Находим батч, содержащий символ, и удаляем его
                            for batch_id, batch_symbols in batches_list:
                                if symbol in batch_symbols:
                                    batch_symbols.remove(symbol)
                                    # Отправляем unsubscribe
                                    if not ws.closed:
                                        try:
                                            unsubscribe_msg = {
                                                "op": "unsubscribe",
                                                "args": [f"publicTrade.{symbol}"]
                                            }
                                            await ws.send_json(unsubscribe_msg)
                                        except Exception as e:
                                            logger.warning(
                                                f"Bybit {market} [{conn_id}]: "
                                                f"ошибка при отписке от {symbol}: {e}"
                                            )
                                    break
                            
                            # Пересоздаем batches если нужно
                            if market == "spot":
                                batches_list.clear()
                                for batch_idx in range(0, len(all_syms), BATCH_SIZE_SPOT):
                                    batch_symbols = all_syms[batch_idx:batch_idx+BATCH_SIZE_SPOT]
                                    batch_id = f"{conn_id}-B{batch_idx//BATCH_SIZE_SPOT + 1}"
                                    batches_list.append((batch_id, batch_symbols))
                            else:
                                batches_list.clear()
                                batches_list.append((conn_id, all_syms))
                
                # Обрабатываем новые символы
                for symbol in added_symbols:
                    # Находим соединение с наименьшим количеством символов (но меньше лимита)
                    best_connection = None
                    best_conn_id = None
                    best_all_symbols = None
                    best_batches = None
                    min_count = WS_SYMBOLS_PER_CONNECTION_SPOT if market == "spot" else WS_SYMBOLS_PER_CONNECTION_LINEAR
                    
                    for conn_id, (ws, all_syms, batches_list, conn_market) in _active_connections.items():
                        if conn_market == market:
                            limit = WS_SYMBOLS_PER_CONNECTION_SPOT if market == "spot" else WS_SYMBOLS_PER_CONNECTION_LINEAR
                            if len(all_syms) < limit:
                                if len(all_syms) < min_count:
                                    min_count = len(all_syms)
                                    best_connection = ws
                                    best_conn_id = conn_id
                                    best_all_symbols = all_syms
                                    best_batches = batches_list
                    
                    if best_connection and not best_connection.closed:
                        # Добавляем символ в существующее соединение
                        best_all_symbols.append(symbol)
                        
                        # Добавляем в последний батч или создаем новый
                        if market == "spot":
                            # Для spot добавляем в последний батч или создаем новый
                            if best_batches:
                                last_batch_id, last_batch_symbols = best_batches[-1]
                                if len(last_batch_symbols) < BATCH_SIZE_SPOT:
                                    last_batch_symbols.append(symbol)
                                else:
                                    # Создаем новый батч
                                    new_batch_id = f"{best_conn_id}-B{len(best_batches) + 1}"
                                    best_batches.append((new_batch_id, [symbol]))
                            else:
                                best_batches.append((best_conn_id, [symbol]))
                        else:
                            # Для linear добавляем в единственный батч
                            if best_batches:
                                _, batch_symbols = best_batches[0]
                                batch_symbols.append(symbol)
                            else:
                                best_batches.append((best_conn_id, [symbol]))
                        
                        # Отправляем subscribe
                        try:
                            subscribe_msg = {
                                "op": "subscribe",
                                "args": [f"publicTrade.{symbol}"]
                            }
                            await best_connection.send_json(subscribe_msg)
                            logger.info(
                                f"Bybit {market}: новый символ {symbol} добавлен, "
                                f"подписываемся в {best_conn_id}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Bybit {market} [{best_conn_id}]: "
                                f"ошибка при подписке на {symbol}: {e}"
                            )
                            # Удаляем символ из списка при ошибке
                            if symbol in best_all_symbols:
                                best_all_symbols.remove(symbol)
                    else:
                        # Все соединения заполнены или нет соединений - создаем новое
                        logger.info(
                            f"Bybit {market}: новый символ {symbol} добавлен, "
                            f"создаем новое соединение"
                        )
                        # Собираем все новые символы, которые не поместились
                        new_symbols_to_add = [s for s in added_symbols if s not in [
                            sym for _, all_syms, _, m in _active_connections.values() 
                            if m == market for sym in all_syms
                        ]]
                        
                        if new_symbols_to_add:
                            # Разбиваем на соединения
                            symbols_per_conn = WS_SYMBOLS_PER_CONNECTION_SPOT if market == "spot" else WS_SYMBOLS_PER_CONNECTION_LINEAR
                            for i in range(0, len(new_symbols_to_add), symbols_per_conn):
                                connection_symbols = new_symbols_to_add[i:i+symbols_per_conn]
                                connection_symbols = list(connection_symbols)
                                connection_id = f"{market.upper()}#{len(_spot_tasks if market == 'spot' else _linear_tasks) + i // symbols_per_conn + 1}"
                                
                                # Создаем batches
                                all_syms = connection_symbols
                                batches_in_conn = []
                                if market == "spot":
                                    for batch_idx in range(0, len(all_syms), BATCH_SIZE_SPOT):
                                        batch_symbols = all_syms[batch_idx:batch_idx+BATCH_SIZE_SPOT]
                                        batch_id = f"{connection_id}-B{batch_idx//BATCH_SIZE_SPOT + 1}"
                                        batches_in_conn.append((batch_id, batch_symbols))
                                else:
                                    batches_in_conn.append((connection_id, all_syms))
                                
                                # Создаем новое соединение
                                task = asyncio.create_task(_ws_consumer_with_batches(
                                    market=market,
                                    connection_id=connection_id,
                                    all_symbols=all_syms,
                                    batches=batches_in_conn,
                                    session=session,
                                    on_candle=on_candle,
                                    on_error=on_error,
                                ))
                                _tasks.append(task)
                                if market == "spot":
                                    _spot_tasks.append(task)
                                else:
                                    _linear_tasks.append(task)
                                
                                logger.info(
                                    f"Bybit {market}: создано новое соединение {connection_id} "
                                    f"для {len(connection_symbols)} символов"
                                )
        
        except Exception as e:
            logger.error(f"Ошибка при обновлении символов Bybit {market}: {e}", exc_info=True)
        
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
    _builder = CandleBuilder(
        maxlen=config.memory_max_candles_per_symbol,
        on_trade=on_trade,
        on_candle=on_candle,
    )
    
    # Создаём сессию с SSL сертификатами из certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    _session = aiohttp.ClientSession(connector=connector)
    
    # Инициализируем lock если еще не инициализирован
    global _symbol_update_lock
    if _symbol_update_lock is None:
        _symbol_update_lock = asyncio.Lock()
    
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
    
    # Инициализируем глобальные списки символов
    async with _symbol_update_lock:
        _active_spot_symbols[:] = spot_symbols
        _active_linear_symbols[:] = linear_symbols
    
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
            
            # Создаем изменяемый список для батча (чтобы можно было обновлять при реконнекте)
            all_symbols = list(connection_symbols)
            
            # Создаём батчи внутри этого соединения (10 символов на батч для SPOT)
            batches_in_conn = []
            # Создаем snapshot списка для защиты от изменения во время итерации
            all_symbols_snapshot = list(all_symbols)
            for batch_idx in range(0, len(all_symbols_snapshot), BATCH_SIZE_SPOT):
                batch_symbols = all_symbols_snapshot[batch_idx:batch_idx+BATCH_SIZE_SPOT]
                batch_id = f"{connection_id}-B{batch_idx//BATCH_SIZE_SPOT + 1}"
                batches_in_conn.append((batch_id, batch_symbols))
            
            task = asyncio.create_task(_ws_consumer_with_batches(
                market="spot",
                connection_id=connection_id,
                all_symbols=all_symbols,
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
            
            # Создаем изменяемый список для батча (чтобы можно было обновлять при реконнекте)
            all_symbols = list(connection_symbols)
            
            # Создаём один батч со всеми символами для LINEAR
            batches_in_conn = [(connection_id, all_symbols)]
            
            task = asyncio.create_task(_ws_consumer_with_batches(
                market="linear",
                connection_id=connection_id,
                all_symbols=all_symbols,
                batches=batches_in_conn,
                session=_session,
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _linear_tasks.append(task)
            await asyncio.sleep(0.1)
    
    # Запускаем задачи периодического обновления символов
    if fetch_spot:
        update_task_spot = asyncio.create_task(
            _update_symbols_periodically("spot", on_candle, on_error, config, _session)
        )
        _tasks.append(update_task_spot)
    
    if fetch_linear:
        update_task_linear = asyncio.create_task(
            _update_symbols_periodically("linear", on_candle, on_error, config, _session)
        )
        _tasks.append(update_task_linear)
    
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

