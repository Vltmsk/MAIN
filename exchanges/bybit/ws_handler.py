"""
WebSocket обработчик для Bybit
"""
import ssl
import certifi
import asyncio
from typing import Awaitable, Callable, List, Dict
import aiohttp
import json
import socket
from config import AppConfig
from core.candle_builder import CandleBuilder, Candle
from core.logger import get_logger
from BD.database import db
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

# Периодическая проверка новых символов
SYMBOL_CHECK_INTERVAL_SEC = 300  # 5 минут - интервал проверки новых символов

# Глобальные переменные
_builder: CandleBuilder | None = None
_tasks: List[asyncio.Task] = []
_spot_tasks: List[asyncio.Task] = []  # Отдельное отслеживание spot задач
_linear_tasks: List[asyncio.Task] = []  # Отдельное отслеживание linear задач
_session: aiohttp.ClientSession | None = None
# Хранилище изначально полученных символов для каждого рынка (для правильной проверки новых символов)
# _initial_symbols больше не используется - символы хранятся в БД
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
            # Увеличиваем счётчик реконнектов при любом реконнекте (включая аномальные закрытия)
            _stats[market]["reconnects"] += 1
            logger.info(f"Bybit {market} {connection_id}: переподключение (счётчик: {_stats[market]['reconnects']})")
            
            # ВАЖНО: Обновляем список символов перед переподключением
            # Это необходимо, так как биржа может делистировать символы
            try:
                logger.info(f"Bybit {market} {connection_id}: обновление списка символов перед переподключением...")
                from .symbol_fetcher import fetch_symbols
                current_symbols = await fetch_symbols(market)
                current_symbols_set = set(current_symbols)
                
                # Фильтруем список символов, оставляя только те, которые есть на бирже
                original_count = len(all_symbols)
                original_symbols_set = set(all_symbols)
                all_symbols[:] = [s for s in all_symbols if s in current_symbols_set]
                removed_count = original_count - len(all_symbols)
                
                if removed_count > 0:
                    removed_symbols = list(original_symbols_set - current_symbols_set)
                    logger.warning(
                        f"Bybit {market} {connection_id}: "
                        f"обнаружен делистинг: удалено {removed_count} несуществующих символов из списка подписки: {', '.join(removed_symbols[:10])}"
                        f"{' и еще ' + str(removed_count - 10) + ' символов' if removed_count > 10 else ''}"
                    )
                    logger.info(
                        f"Bybit {market} {connection_id}: "
                        f"переподключение из-за делистинга {removed_count} символов"
                    )
                
                # Проверяем наличие новых символов (листинг)
                new_symbols = [s for s in current_symbols_set if s not in all_symbols]
                if new_symbols:
                    logger.info(
                        f"Bybit {market} {connection_id}: "
                        f"обнаружен листинг: найдено {len(new_symbols)} новых символов: {', '.join(new_symbols[:10])}"
                        f"{' и еще ' + str(len(new_symbols) - 10) + ' символов' if len(new_symbols) > 10 else ''}"
                    )
                    # Добавляем новые символы в список
                    all_symbols.extend(new_symbols)
                    logger.info(
                        f"Bybit {market} {connection_id}: "
                        f"переподключение из-за листинга {len(new_symbols)} символов (новые символы будут добавлены при подписке)"
                    )
                
                # Пересоздаем batches из валидных символов
                # Bybit лимит: max 10 topics per subscribe для spot
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
                
                # Если все символы были удалены, прекращаем работу
                if not all_symbols:
                    logger.warning(
                        f"Bybit {market} {connection_id}: "
                        f"все символы были удалены, прекращаем работу соединения"
                    )
                    break
                    
            except Exception as e:
                logger.warning(
                    f"Bybit {market} {connection_id}: "
                    f"не удалось обновить список символов: {e}, используем текущий список"
                )
            
            delay = min(2 ** min(reconnect_attempt - 1, 5), max_reconnect_delay)
            # Счётчик переподключений увеличивается при входе в новый блок ws_connect
            # (см. строку 192), чтобы избежать двойного подсчёта
            
            # Определяем причину переподключения
            reconnect_reason = "normal"
            try:
                current_symbols = await fetch_symbols(market)
                current_symbols_set = set(current_symbols)
                original_symbols_set = set(all_symbols)
                removed = original_symbols_set - current_symbols_set
                new = current_symbols_set - original_symbols_set
                if removed:
                    reconnect_reason = "delisting"
                elif new:
                    reconnect_reason = "listing"
            except Exception:
                pass
            
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
            
            # Запускаем периодическую проверку новых символов
            async def periodic_symbol_check():
                """Периодически проверяет новые символы и добавляет их в список подписки"""
                from .symbol_fetcher import fetch_symbols
                while True:
                    try:
                        await asyncio.sleep(SYMBOL_CHECK_INTERVAL_SEC)
                        
                        # Пропускаем проверку, если соединение не установлено или список пуст
                        if not was_connected or not all_symbols or ws.closed:
                            continue
                        
                        logger.debug(f"Bybit {market} {connection_id}: проверка новых символов...")
                        
                        # Получаем актуальный список символов с биржи
                        current_symbols = await fetch_symbols(market)
                        
                        # Синхронизируем с БД и получаем новые/удаленные символы
                        new_symbols, removed_symbols = await db.sync_active_symbols(
                            exchange="bybit",
                            market=market,
                            current_symbols=current_symbols
                        )
                        
                        if new_symbols:
                            logger.info(
                                f"Bybit {market} {connection_id}: "
                                f"обнаружено {len(new_symbols)} новых символов: {', '.join(new_symbols[:10])}"
                                f"{' и еще ' + str(len(new_symbols) - 10) + ' символов' if len(new_symbols) > 10 else ''}"
                            )
                            
                            # Добавляем новые символы в список
                            all_symbols.extend(new_symbols)
                            
                            # Подписываемся на новые символы без переподключения
                            # Разбиваем новые символы на батчи (лимит Bybit: max 10 topics per subscribe)
                            new_symbols_batches = []
                            if market == "spot":
                                for batch_idx in range(0, len(new_symbols), BATCH_SIZE_SPOT):
                                    batch_symbols = new_symbols[batch_idx:batch_idx+BATCH_SIZE_SPOT]
                                    new_symbols_batches.append(batch_symbols)
                            else:  # linear - все новые символы в одном батче
                                new_symbols_batches.append(new_symbols)
                            
                            # Подписываемся на новые батчи
                            for batch_symbols in new_symbols_batches:
                                batch_args = [f"publicTrade.{sym}" for sym in batch_symbols]
                                subscribe_msg = {"op": "subscribe", "args": batch_args}
                                try:
                                    if not ws.closed:
                                        await ws.send_json(subscribe_msg)
                                        await asyncio.sleep(0.01)  # Небольшая задержка между подписками
                                except Exception as e:
                                    logger.warning(
                                        f"Bybit {market} {connection_id}: "
                                        f"ошибка при подписке на новые символы: {e}"
                                    )
                                    break
                            
                            # Пересоздаем batches из всех символов (включая новые) для будущих переподключений
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
                            
                            logger.info(
                                f"Bybit {market} {connection_id}: "
                                f"подписка на {len(new_symbols)} новых символов отправлена"
                            )
                            
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.warning(
                            f"Bybit {market} {connection_id}: "
                            f"ошибка при проверке новых символов: {e}"
                        )
            
            symbol_check_task = asyncio.create_task(periodic_symbol_check())
            
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
    _builder = CandleBuilder(
        maxlen=config.memory_max_candles_per_symbol,
        on_trade=on_trade,
        on_candle=on_candle,
    )
    
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
    
    # Сохраняем изначально полученные символы для правильной проверки новых символов
    # Сохраняем символы в БД при запуске
    if spot_symbols:
        await db.upsert_active_symbols("bybit", "spot", spot_symbols)
        logger.info(f"Bybit spot: сохранено {len(spot_symbols)} символов в БД")
    if linear_symbols:
        await db.upsert_active_symbols("bybit", "linear", linear_symbols)
        logger.info(f"Bybit linear: сохранено {len(linear_symbols)} символов в БД")
    
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

