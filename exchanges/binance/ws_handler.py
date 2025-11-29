"""
WebSocket обработчик для Binance
Binance предоставляет уже готовые 1-секундные свечи через Kline streams
"""
import ssl
import certifi
import asyncio
from typing import Awaitable, Callable, List, Dict
import aiohttp
import json
import socket
import time
from collections import deque
import random
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from BD.database import db
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

# Периодическая проверка новых символов
SYMBOL_CHECK_INTERVAL_SEC = 300  # 5 минут - интервал проверки новых символов

# Лимиты переподключений
MAX_CONNECTION_ATTEMPTS_PER_WINDOW = 300  # Максимум попыток подключения
CONNECTION_WINDOW_SECONDS = 5 * 60  # Окно времени в секундах (5 минут)

# Глобальные переменные
_builder: CandleBuilder | None = None
_tasks: List[asyncio.Task] = []
_spot_tasks: List[asyncio.Task] = []  # Отдельное отслеживание spot задач
_linear_tasks: List[asyncio.Task] = []  # Отдельное отслеживание linear задач
_session: aiohttp.ClientSession | None = None
# Счетчик попыток подключения с временными метками (для контроля лимита)
_connection_attempts: deque = deque()
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


def _chunk_list(items: List[str], size: int) -> List[List[str]]:
    """Разделить список на чанки."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def _parse_float(x) -> float:
    """Безопасное преобразование в float."""
    try:
        return float(x)
    except Exception:
        return 0.0


async def _check_connection_rate_limit() -> float:
    """
    Проверяет лимит попыток подключения и возвращает необходимую задержку.
    
    Returns:
        Задержка в секундах перед следующим подключением (0 если лимит не превышен)
    """
    global _connection_attempts
    
    current_time = time.time()
    
    # Удаляем старые записи (старше окна времени)
    while _connection_attempts and current_time - _connection_attempts[0] > CONNECTION_WINDOW_SECONDS:
        _connection_attempts.popleft()
    
    # ВСЕГДА добавляем текущую попытку для корректного отслеживания и естественного восстановления
    _connection_attempts.append(current_time)
    
    # Проверяем лимит ПОСЛЕ добавления попытки
    if len(_connection_attempts) > MAX_CONNECTION_ATTEMPTS_PER_WINDOW:
        # Лимит превышен, вычисляем задержку
        oldest_attempt = _connection_attempts[0]
        time_until_window_reset = CONNECTION_WINDOW_SECONDS - (current_time - oldest_attempt)
        # Добавляем небольшую задержку сверх времени до сброса окна
        delay = max(time_until_window_reset + 1, 10)
        logger.warning(
            f"Binance: превышен лимит подключений ({MAX_CONNECTION_ATTEMPTS_PER_WINDOW} за {CONNECTION_WINDOW_SECONDS}с). "
            f"Ожидание {delay:.1f}с перед следующим подключением"
        )
        return delay
    
    # Лимит не превышен
    return 0.0


def _extract_symbols_from_streams(streams: List[str], market: str) -> List[str]:
    """
    Извлекает символы из streams для обновления списка.
    
    Args:
        streams: Список streams (например, ["btcusdt@kline_1s", ...])
        market: Рынок ("spot" или "linear")
        
    Returns:
        Список символов в верхнем регистре (например, ["BTCUSDT", ...])
    """
    symbols = []
    if market == "spot":
        for stream in streams:
            if stream.endswith("@kline_1s"):
                symbol = stream.replace("@kline_1s", "").upper()
                if symbol:
                    symbols.append(symbol)
    else:  # linear
        for stream in streams:
            if "_perpetual@continuousKline_1s" in stream:
                symbol = stream.replace("_perpetual@continuousKline_1s", "").upper()
                if symbol:
                    symbols.append(symbol)
    return symbols


def _validate_streams(streams: List[str], market: str) -> List[str]:
    """
    Валидация стримов перед подпиской.
    Проверяет формат и исключает невалидные стримы.
    
    Args:
        streams: Список стримов для валидации
        market: Рынок (spot или linear)
        
    Returns:
        Отфильтрованный список валидных стримов
    """
    valid_streams = []
    invalid_count = 0
    
    for stream in streams:
        if not isinstance(stream, str) or not stream:
            invalid_count += 1
            logger.warning(f"Binance {market}: пропущен пустой или невалидный стрим: {stream}")
            continue
        
        # Проверяем формат для Spot
        if market == "spot":
            if not stream.endswith("@kline_1s"):
                invalid_count += 1
                logger.warning(f"Binance {market}: невалидный формат стрима (ожидается @kline_1s): {stream}")
                continue
            # Проверяем, что символ не пустой
            symbol_part = stream.replace("@kline_1s", "")
            if not symbol_part:
                invalid_count += 1
                logger.warning(f"Binance {market}: пустой символ в стриме: {stream}")
                continue
        
        # Проверяем формат для Linear
        elif market == "linear":
            if not stream.endswith("@continuousKline_1s"):
                invalid_count += 1
                logger.warning(f"Binance {market}: невалидный формат стрима (ожидается @continuousKline_1s): {stream}")
                continue
            # Проверяем наличие _perpetual
            if "_perpetual@continuousKline_1s" not in stream:
                invalid_count += 1
                logger.warning(f"Binance {market}: невалидный формат стрима (ожидается _perpetual): {stream}")
                continue
            # Проверяем, что символ не пустой
            symbol_part = stream.replace("_perpetual@continuousKline_1s", "")
            if not symbol_part:
                invalid_count += 1
                logger.warning(f"Binance {market}: пустой символ в стриме: {stream}")
                continue
        
        valid_streams.append(stream)
    
    if invalid_count > 0:
        logger.warning(f"Binance {market}: исключено {invalid_count} невалидных стримов из {len(streams)}")
    
    return valid_streams


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
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        
        # Сохраняем значение флага перед проверкой reconnect_attempt
        is_scheduled = connection_state["is_scheduled_reconnect"]
        # Сбрасываем флаг сразу, чтобы он не влиял на последующие итерации
        if is_scheduled:
            connection_state["is_scheduled_reconnect"] = False
        
        try:
            # Обрабатываем переподключение (обычное или плановое)
            # Переподключение считается, если:
            # 1. Это не первая попытка (reconnect_attempt > 1), ИЛИ
            # 2. Это первая попытка, но соединение было установлено ранее (was_connected = True), ИЛИ
            # 3. Это плановое переподключение
            is_reconnect = reconnect_attempt > 1 or was_connected or (reconnect_attempt == 1 and is_scheduled)
            
            if is_reconnect:
                # ВАЖНО: Обновляем список символов перед переподключением
                # Это необходимо, так как биржа может делистировать символы
                if not is_scheduled:  # Обновляем только при обычном переподключении
                    try:
                        logger.info(f"Binance {market}: обновление списка символов перед переподключением...")
                        # Извлекаем символы из streams
                        current_symbols_list = _extract_symbols_from_streams(streams, market)
                        if current_symbols_list:
                            # Получаем актуальный список символов с биржи
                            from .symbol_fetcher import fetch_symbols
                            current_symbols = await fetch_symbols(market)
                            current_symbols_set = set(current_symbols)
                            
                            # Фильтруем символы, оставляя только те, которые есть на бирже
                            valid_symbols = [s for s in current_symbols_list if s in current_symbols_set]
                            removed_count = len(current_symbols_list) - len(valid_symbols)
                            
                            if removed_count > 0:
                                removed_symbols = [s for s in current_symbols_list if s not in current_symbols_set]
                                logger.warning(
                                    f"Binance {market}: "
                                    f"обнаружен делистинг: удалено {removed_count} несуществующих символов из списка подписки: {', '.join(removed_symbols[:10])}"
                                    f"{' и еще ' + str(removed_count - 10) + ' символов' if removed_count > 10 else ''}"
                                )
                                logger.info(
                                    f"Binance {market}: "
                                    f"переподключение из-за делистинга {removed_count} символов"
                                )
                            
                            # Проверяем наличие новых символов (листинг)
                            new_symbols = [s for s in current_symbols_set if s not in current_symbols_list]
                            if new_symbols:
                                logger.info(
                                    f"Binance {market}: "
                                    f"обнаружен листинг: найдено {len(new_symbols)} новых символов: {', '.join(new_symbols[:10])}"
                                    f"{' и еще ' + str(len(new_symbols) - 10) + ' символов' if len(new_symbols) > 10 else ''}"
                                )
                                # Добавляем новые символы в список валидных
                                valid_symbols.extend(new_symbols)
                                logger.info(
                                    f"Binance {market}: "
                                    f"переподключение из-за листинга {len(new_symbols)} символов"
                                )
                            
                            # Пересоздаем streams из валидных символов
                            if market == "spot":
                                streams[:] = [f"{sym.lower()}@kline_1s" for sym in valid_symbols]
                            else:  # linear
                                streams[:] = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in valid_symbols]
                            
                            # Если все символы были удалены, прекращаем работу
                            if not streams:
                                logger.warning(
                                    f"Binance {market}: "
                                    f"все символы были удалены, прекращаем работу соединения"
                                )
                                break
                    except Exception as e:
                        logger.warning(
                            f"Binance {market}: "
                            f"не удалось обновить список символов: {e}, используем текущий список"
                        )
                
                # Если это не плановое переподключение, увеличиваем счётчик и логируем
                if not is_scheduled:
                    delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                    _stats[market]["reconnects"] += 1
                    logger.info(f"Binance {market}: переподключение (счётчик: {_stats[market]['reconnects']})")
                    
                    # Определяем причину переподключения
                    reconnect_reason = "normal"
                    try:
                        current_symbols = await fetch_symbols(market)
                        current_symbols_set = set(current_symbols)
                        current_symbols_list = _extract_symbols_from_streams(streams, market)
                        original_symbols_set = set(current_symbols_list)
                        removed = original_symbols_set - current_symbols_set
                        new = current_symbols_set - original_symbols_set
                        if removed:
                            reconnect_reason = "delisting"
                        elif new:
                            reconnect_reason = "listing"
                    except Exception:
                        pass
                    
                    await on_error({
                        "exchange": "binance",
                        "market": market,
                        "connection_id": f"streams-{len(streams)}",
                        "type": "reconnect",
                        "reason": reconnect_reason,
                    })
                    await asyncio.sleep(delay)
                else:
                    # Для планового переподключения не увеличиваем счётчик
                    await asyncio.sleep(1)  # Небольшая задержка перед новым подключением
            
            if _session is None or _session.closed:
                logger.error(f"Binance {market}: сессия не инициализирована или закрыта")
                await asyncio.sleep(5)
                continue
            
            # Проверяем лимит попыток подключения
            rate_limit_delay = await _check_connection_rate_limit()
            if rate_limit_delay > 0:
                await asyncio.sleep(rate_limit_delay)
                continue
            
            async with _session.ws_connect(url) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                # Устанавливаем флаг успешного подключения
                # Если это было переподключение, was_connected уже был True, оставляем его
                # Если это первое подключение, устанавливаем в True
                was_connected = True
                
                _stats[market]["active_connections"] += 1
                
                # Список streams, которые нужно удалить из-за ошибок подписки
                streams_to_remove = set()
                
                # Создаём задачу для планового переподключения через 23 часа
                scheduled_reconnect_task = asyncio.create_task(
                    _schedule_reconnect(ws, SCHEDULED_RECONNECT_INTERVAL, market, streams, on_error, connection_state)
                )
                
                # Запускаем периодическую проверку новых символов
                async def periodic_symbol_check():
                    """Периодически проверяет новые символы и добавляет их в список streams"""
                    from .symbol_fetcher import fetch_symbols
                    while True:
                        try:
                            await asyncio.sleep(SYMBOL_CHECK_INTERVAL_SEC)
                            
                            # Пропускаем проверку, если соединение не установлено или список пуст
                            if not was_connected or not streams:
                                continue
                            
                            logger.debug(f"Binance {market}: проверка новых символов...")
                            
                            # Получаем актуальный список символов с биржи
                            current_symbols = await fetch_symbols(market)
                            
                            # Синхронизируем с БД и получаем новые/удаленные символы
                            new_symbols, removed_symbols = await db.sync_active_symbols(
                                exchange="binance",
                                market=market,
                                current_symbols=current_symbols
                            )
                            
                            if new_symbols:
                                logger.info(
                                    f"Binance {market}: "
                                    f"обнаружено {len(new_symbols)} новых символов: {', '.join(new_symbols[:10])}"
                                    f"{' и еще ' + str(len(new_symbols) - 10) + ' символов' if len(new_symbols) > 10 else ''}"
                                )
                                
                                # Создаем новые streams для новых символов
                                if market == "spot":
                                    new_streams = [f"{sym.lower()}@kline_1s" for sym in new_symbols]
                                else:  # linear
                                    new_streams = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in new_symbols]
                                
                                # Добавляем новые streams в список
                                streams.extend(new_streams)
                                
                                # Для Binance spot через /stream нужно переподключиться с новым URL
                                # Для Binance linear через /ws можно добавить подписку
                                if market == "linear":
                                    # Подписываемся на новые streams через JSON
                                    subscribe_msg = {
                                        "method": "SUBSCRIBE",
                                        "params": new_streams,
                                        "id": 2  # Используем другой ID для новых подписок
                                    }
                                    try:
                                        if not ws.closed:
                                            await ws.send_json(subscribe_msg)
                                            logger.info(
                                                f"Binance {market}: "
                                                f"подписка на {len(new_streams)} новых streams отправлена"
                                            )
                                    except Exception as e:
                                        logger.warning(
                                            f"Binance {market}: "
                                            f"ошибка при подписке на новые streams: {e}"
                                        )
                                else:
                                    # Для spot нужно переподключиться с новым URL
                                    logger.info(
                                        f"Binance {market}: "
                                        f"обнаружены новые символы, требуется переподключение для добавления {len(new_streams)} streams"
                                    )
                                    # Переподключение произойдет автоматически при следующей итерации
                                
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            logger.warning(
                                f"Binance {market}: "
                                f"ошибка при проверке новых символов: {e}"
                            )
                
                symbol_check_task = asyncio.create_task(periodic_symbol_check())
                
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                payload = json.loads(msg.data)
                                
                                # Проверяем наличие ошибок в payload (Binance может отправлять ошибки в JSON)
                                if isinstance(payload, dict):
                                    # Проверяем наличие поля error
                                    if "error" in payload:
                                        error_info = payload.get("error", {})
                                        error_msg = error_info.get("msg", "Unknown error") if isinstance(error_info, dict) else str(error_info)
                                        error_code = error_info.get("code", "Unknown") if isinstance(error_info, dict) else "Unknown"
                                        
                                        # Если ошибка связана с несуществующими символами, извлекаем проблемные streams
                                        if error_code in [400, 1003] or (isinstance(error_msg, str) and any(phrase in error_msg.lower() for phrase in ["invalid", "not exist", "not found", "doesn't exist"])):
                                            # Пытаемся извлечь проблемные streams из ответа
                                            problematic_streams = []
                                            if "stream" in payload:
                                                problematic_streams = [payload["stream"]]
                                            elif "streams" in payload:
                                                problematic_streams = payload["streams"]
                                            elif isinstance(payload.get("data"), list):
                                                problematic_streams = [item.get("stream") for item in payload["data"] if isinstance(item, dict) and "stream" in item]
                                            
                                            # Если не удалось извлечь, используем все streams (Binance может не указывать конкретные)
                                            if not problematic_streams:
                                                problematic_streams = streams
                                            
                                            for stream in problematic_streams:
                                                if stream and stream in streams:
                                                    streams_to_remove.add(stream)
                                                    logger.info(
                                                        f"Binance {market}: "
                                                        f"стрим {stream} будет удален из списка подписки (не существует на бирже)"
                                                    )
                                        
                                        logger.error(f"Binance {market}: ошибка от сервера (code: {error_code}): {error_msg}")
                                        logger.error(f"Binance {market}: полный ответ: {json.dumps(payload)}")
                                        await on_error({
                                            "exchange": "binance",
                                            "market": market,
                                            "connection_id": f"streams-{len(streams)}",
                                            "type": "server_error",
                                            "error": error_msg,
                                            "code": error_code,
                                        })
                                        
                                        # Удаляем проблемные streams из списка
                                        if streams_to_remove:
                                            removed = [s for s in streams if s in streams_to_remove]
                                            streams[:] = [s for s in streams if s not in streams_to_remove]
                                            if removed:
                                                logger.warning(
                                                    f"Binance {market}: "
                                                    f"удалены стримы из списка подписки: {', '.join(removed[:10])}"
                                                    f"{' и еще ' + str(len(removed) - 10) + ' стримов' if len(removed) > 10 else ''}"
                                                )
                                                streams_to_remove.clear()
                                                
                                                # Если все streams были удалены, прекращаем работу
                                                if not streams:
                                                    logger.warning(
                                                        f"Binance {market}: "
                                                        f"все стримы были удалены, прекращаем работу соединения"
                                                    )
                                                    break
                                        
                                        # Переподключаемся при ошибке от сервера
                                        break
                                    # Проверяем наличие кода ошибки (если есть code и он не 200)
                                    if "code" in payload and payload.get("code") != 200:
                                        error_msg = payload.get("msg", f"Error code: {payload.get('code')}")
                                        logger.error(f"Binance {market}: ошибка от сервера (code: {payload.get('code')}): {error_msg}")
                                        await on_error({
                                            "exchange": "binance",
                                            "market": market,
                                            "connection_id": f"streams-{len(streams)}",
                                            "type": "server_error",
                                            "error": error_msg,
                                            "code": payload.get("code"),
                                        })
                                        # Переподключаемся при ошибке от сервера
                                        break
                                
                                await _handle_kline_message(payload, market, on_candle)
                            except Exception as e:
                                logger.error(f"Ошибка обработки сообщения Binance {market}: {e}")
                                logger.error(f"Payload (первые 200 символов): {msg.data[:200] if len(msg.data) > 200 else msg.data}")
                                # При ошибке обработки сообщения продолжаем работу, не переподключаемся
                        
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            # Логируем закрытие соединения с информацией о причине
                            is_scheduled_close = connection_state.get("is_scheduled_reconnect", False)
                            if is_scheduled_close:
                                logger.info(f"Binance {market}: WebSocket закрыт (CLOSE) - плановое переподключение")
                            else:
                                logger.warning(f"Binance {market}: WebSocket закрыт (CLOSE) - соединение разорвано")
                            # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                            if was_connected and not is_scheduled_close:
                                await on_error({
                                    "exchange": "binance",
                                    "market": market,
                                    "connection_id": f"streams-{len(streams)}",
                                    "type": "reconnect",
                                    "reason": "connection_closed",
                                })
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.warning(f"Binance {market}: WebSocket ошибка (ERROR) - соединение разорвано")
                            # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                            if was_connected:
                                await on_error({
                                    "exchange": "binance",
                                    "market": market,
                                    "connection_id": f"streams-{len(streams)}",
                                    "type": "reconnect",
                                    "reason": "websocket_error",
                                })
                            break
                finally:
                    # Отменяем задачу планового переподключения, если соединение закрылось раньше
                    scheduled_reconnect_task.cancel()
                    if 'symbol_check_task' in locals():
                        symbol_check_task.cancel()
                    try:
                        await scheduled_reconnect_task
                    except asyncio.CancelledError:
                        pass
                    try:
                        if 'symbol_check_task' in locals():
                            await symbol_check_task
                    except asyncio.CancelledError:
                        pass
                
                _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                # ВАЖНО: НЕ сбрасываем was_connected здесь, если соединение было установлено
                # Это нужно для правильного подсчёта переподключений при следующей итерации
                # was_connected будет сброшен только при успешном подключении в следующей итерации
                # (когда reconnect_attempt будет сброшен в 0)
                
        except asyncio.CancelledError:
            break
        except (ConnectionResetError, ConnectionError) as e:
            # Обработка ConnectionResetError (WinError 10054) - соединение принудительно закрыто удаленным хостом
            error_msg = f"Соединение принудительно закрыто удаленным хостом: {e}"
            logger.warning(f"Binance {market}: {error_msg}")
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                _stats[market]["reconnects"] += 1
                logger.info(f"Binance {market}: переподключение из-за разрыва (счётчик: {_stats[market]['reconnects']})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "connection_id": f"streams-{len(streams)}",
                "error": error_msg,
                "error_type": "connection_reset",
            })
            # Небольшая задержка перед переподключением
            await asyncio.sleep(min(2 ** min(reconnect_attempt - 1, 5), 60))
        except Exception as e:
            logger.error(f"Ошибка в WS соединении Binance {market}: {e}")
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                _stats[market]["reconnects"] += 1
                logger.info(f"Binance {market}: переподключение из-за ошибки (счётчик: {_stats[market]['reconnects']})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "error": str(e),
            })
            # Небольшая задержка перед переподключением
            await asyncio.sleep(min(2 ** min(reconnect_attempt - 1, 5), 60))


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
    was_connected = False  # Флаг успешного подключения
    
    # Добавляем небольшую случайную задержку перед первым подключением,
    # чтобы распределить попытки подключения разных worker'ов во времени
    # и избежать одновременных запросов, которые могут привести к rate limiting
    initial_delay = random.uniform(0, 0.5)  # Случайная задержка от 0 до 0.5 секунды
    await asyncio.sleep(initial_delay)
    
    while True:
        reconnect_attempt += 1
        
        # Сохраняем значение флага перед проверкой reconnect_attempt
        is_scheduled = connection_state["is_scheduled_reconnect"]
        # Сбрасываем флаг сразу, чтобы он не влиял на последующие итерации
        if is_scheduled:
            connection_state["is_scheduled_reconnect"] = False
        
        try:
            # Обрабатываем переподключение (обычное или плановое)
            # Переподключение считается, если:
            # 1. Это не первая попытка (reconnect_attempt > 1), ИЛИ
            # 2. Это первая попытка, но соединение было установлено ранее (was_connected = True), ИЛИ
            # 3. Это плановое переподключение
            is_reconnect = reconnect_attempt > 1 or was_connected or (reconnect_attempt == 1 and is_scheduled)
            
            if is_reconnect:
                # ВАЖНО: Обновляем список символов перед переподключением
                # Это необходимо, так как биржа может делистировать символы
                if not is_scheduled:  # Обновляем только при обычном переподключении
                    try:
                        logger.info(f"Binance {market} (subscribe mode): обновление списка символов перед переподключением...")
                        # Извлекаем символы из streams
                        current_symbols_list = _extract_symbols_from_streams(streams, market)
                        if current_symbols_list:
                            # Получаем актуальный список символов с биржи
                            from .symbol_fetcher import fetch_symbols
                            current_symbols = await fetch_symbols(market)
                            current_symbols_set = set(current_symbols)
                            
                            # Фильтруем символы, оставляя только те, которые есть на бирже
                            valid_symbols = [s for s in current_symbols_list if s in current_symbols_set]
                            removed_count = len(current_symbols_list) - len(valid_symbols)
                            
                            if removed_count > 0:
                                removed_symbols = [s for s in current_symbols_list if s not in current_symbols_set]
                                logger.warning(
                                    f"Binance {market} (subscribe mode): "
                                    f"обнаружен делистинг: удалено {removed_count} несуществующих символов из списка подписки: {', '.join(removed_symbols[:10])}"
                                    f"{' и еще ' + str(removed_count - 10) + ' символов' if removed_count > 10 else ''}"
                                )
                                logger.info(
                                    f"Binance {market} (subscribe mode): "
                                    f"переподключение из-за делистинга {removed_count} символов"
                                )
                            
                            # Проверяем наличие новых символов (листинг)
                            new_symbols = [s for s in current_symbols_set if s not in current_symbols_list]
                            if new_symbols:
                                logger.info(
                                    f"Binance {market} (subscribe mode): "
                                    f"обнаружен листинг: найдено {len(new_symbols)} новых символов: {', '.join(new_symbols[:10])}"
                                    f"{' и еще ' + str(len(new_symbols) - 10) + ' символов' if len(new_symbols) > 10 else ''}"
                                )
                                # Добавляем новые символы в список валидных
                                valid_symbols.extend(new_symbols)
                                logger.info(
                                    f"Binance {market} (subscribe mode): "
                                    f"переподключение из-за листинга {len(new_symbols)} символов"
                                )
                            
                            # Пересоздаем streams из валидных символов
                            if market == "spot":
                                streams[:] = [f"{sym.lower()}@kline_1s" for sym in valid_symbols]
                            else:  # linear
                                streams[:] = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in valid_symbols]
                            
                            # Если все символы были удалены, прекращаем работу
                            if not streams:
                                logger.warning(
                                    f"Binance {market} (subscribe mode): "
                                    f"все символы были удалены, прекращаем работу соединения"
                                )
                                break
                    except Exception as e:
                        logger.warning(
                            f"Binance {market} (subscribe mode): "
                            f"не удалось обновить список символов: {e}, используем текущий список"
                        )
                
                # Если это не плановое переподключение, увеличиваем счётчик и логируем
                if not is_scheduled:
                    delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                    # Увеличиваем счётчик переподключений здесь (один раз)
                    _stats[market]["reconnects"] += 1
                    logger.info(f"Binance {market}: переподключение (счётчик: {_stats[market]['reconnects']})")
                    
                    # Определяем причину переподключения
                    reconnect_reason = "normal"
                    try:
                        current_symbols = await fetch_symbols(market)
                        current_symbols_set = set(current_symbols)
                        current_symbols_list = _extract_symbols_from_streams(streams, market)
                        original_symbols_set = set(current_symbols_list)
                        removed = original_symbols_set - current_symbols_set
                        new = current_symbols_set - original_symbols_set
                        if removed:
                            reconnect_reason = "delisting"
                        elif new:
                            reconnect_reason = "listing"
                    except Exception:
                        pass
                    
                    await on_error({
                        "exchange": "binance",
                        "market": market,
                        "connection_id": f"ws-subscribe-{len(streams)}",
                        "type": "reconnect",
                        "reason": reconnect_reason,
                    })
                    await asyncio.sleep(delay)
                else:
                    # Для планового переподключения не увеличиваем счётчик
                    await asyncio.sleep(1)  # Небольшая задержка перед новым подключением
            
            if _session is None or _session.closed:
                logger.error(f"Binance {market}: сессия не инициализирована или закрыта")
                await asyncio.sleep(5)
                continue
            
            # Проверяем лимит попыток подключения
            rate_limit_delay = await _check_connection_rate_limit()
            if rate_limit_delay > 0:
                await asyncio.sleep(rate_limit_delay)
                continue
            
            url = FAPI_WS_ENDPOINT_WS
            
            # Логируем попытку подключения для диагностики
            connection_id_debug = f"linear-chunk-{len(streams)}-streams"
            logger.info(f"Binance {market}: попытка подключения ({connection_id_debug}, попытка {reconnect_attempt})")
            
            async with _session.ws_connect(url) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                # Устанавливаем флаг успешного подключения
                # Если это было переподключение, was_connected уже был True, оставляем его
                # Если это первое подключение, устанавливаем в True
                was_connected = True
                
                logger.info(f"Binance {market}: успешное подключение ({connection_id_debug})")
                _stats[market]["active_connections"] += 1
                
                # Список streams, которые нужно удалить из-за ошибок подписки
                streams_to_remove = set()
                
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
                    
                    # Отслеживаем статус подписки (без таймаута - Binance может обрабатывать подписку долго)
                    # При большом количестве стримов (100+) Binance может обрабатывать подписку с задержкой
                    # Таймаут убран, чтобы дать Binance достаточно времени на обработку подписки
                    subscription_confirmed = False
                    first_data_received = False
                    messages_received = 0  # Счётчик полученных сообщений для отладки
                    
                    # Создаём задачу для планового переподключения через 23 часа
                    scheduled_reconnect_task = asyncio.create_task(
                        _schedule_reconnect(ws, SCHEDULED_RECONNECT_INTERVAL, market, streams, on_error, connection_state)
                    )
                    
                    # Запускаем периодическую проверку новых символов
                    async def periodic_symbol_check_subscribe():
                        """Периодически проверяет новые символы и добавляет их в список streams"""
                        from .symbol_fetcher import fetch_symbols
                        while True:
                            try:
                                await asyncio.sleep(SYMBOL_CHECK_INTERVAL_SEC)
                                
                                # Пропускаем проверку, если соединение не установлено или список пуст
                                if not was_connected or not streams:
                                    continue
                                
                                logger.debug(f"Binance {market} (subscribe mode): проверка новых символов...")
                                
                                # Получаем актуальный список символов с биржи
                                current_symbols = await fetch_symbols(market)
                                
                                # Синхронизируем с БД и получаем новые/удаленные символы
                                new_symbols, removed_symbols = await db.sync_active_symbols(
                                    exchange="binance",
                                    market=market,
                                    current_symbols=current_symbols
                                )
                                
                                if new_symbols:
                                    logger.info(
                                        f"Binance {market} (subscribe mode): "
                                        f"обнаружено {len(new_symbols)} новых символов: {', '.join(new_symbols[:10])}"
                                        f"{' и еще ' + str(len(new_symbols) - 10) + ' символов' if len(new_symbols) > 10 else ''}"
                                    )
                                    
                                    # Создаем новые streams для новых символов
                                    if market == "spot":
                                        new_streams = [f"{sym.lower()}@kline_1s" for sym in new_symbols]
                                    else:  # linear
                                        new_streams = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in new_symbols]
                                    
                                    # Добавляем новые streams в список
                                    streams.extend(new_streams)
                                    
                                    # Подписываемся на новые streams через JSON
                                    subscribe_msg = {
                                        "method": "SUBSCRIBE",
                                        "params": new_streams,
                                        "id": 2  # Используем другой ID для новых подписок
                                    }
                                    try:
                                        if not ws.closed:
                                            await ws.send_json(subscribe_msg)
                                            logger.info(
                                                f"Binance {market} (subscribe mode): "
                                                f"подписка на {len(new_streams)} новых streams отправлена"
                                            )
                                    except Exception as e:
                                        logger.warning(
                                            f"Binance {market} (subscribe mode): "
                                            f"ошибка при подписке на новые streams: {e}"
                                        )
                                    
                            except asyncio.CancelledError:
                                break
                            except Exception as e:
                                logger.warning(
                                    f"Binance {market} (subscribe mode): "
                                    f"ошибка при проверке новых символов: {e}"
                                )
                    
                    symbol_check_task_subscribe = asyncio.create_task(periodic_symbol_check_subscribe())
                    
                    try:
                        # Единый цикл для проверки подписки и обработки сообщений
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    messages_received += 1
                                    
                                    # Логируем первые несколько сообщений для отладки
                                    if messages_received <= 3:
                                        logger.debug(
                                            f"Binance {market}: сообщение #{messages_received} после подписки: "
                                            f"{json.dumps(payload)[:300]}"
                                        )
                                    
                                    # Проверяем ответ на подписку (только если ещё не подтверждена)
                                    if not subscription_confirmed and payload.get("id") == 1:
                                        # Проверяем наличие ошибки (если есть ключ "error" - это ошибка)
                                        if "error" in payload:
                                            # Ошибка подписки
                                            error_info = payload.get("error", {})
                                            error_msg = error_info.get("msg", "Unknown error") if isinstance(error_info, dict) else str(error_info)
                                            error_code = error_info.get("code", "Unknown") if isinstance(error_info, dict) else "Unknown"
                                            
                                            # Извлекаем информацию о проблемных стримах из ответа или используем весь список
                                            problematic_streams = streams
                                            if isinstance(error_info, dict) and "params" in error_info:
                                                problematic_streams = error_info.get("params", streams)
                                            elif isinstance(payload, dict) and "params" in payload:
                                                problematic_streams = payload.get("params", streams)
                                            
                                            # Логируем проблемные символы
                                            logger.error(f"Binance {market}: ошибка подписки (code: {error_code}): {error_msg}")
                                            logger.error(f"Binance {market}: количество проблемных стримов: {len(problematic_streams)}")
                                            if len(problematic_streams) <= 10:
                                                logger.error(f"Binance {market}: проблемные стримы: {problematic_streams}")
                                            else:
                                                logger.error(f"Binance {market}: первые 10 проблемных стримов: {problematic_streams[:10]}")
                                            logger.error(f"Binance {market}: полный ответ: {json.dumps(payload)}")
                                            
                                            # Если ошибка связана с несуществующими символами, добавляем их в список на удаление
                                            # Проверяем типичные коды ошибок для несуществующих символов
                                            if error_code in [400, 1003] or (isinstance(error_msg, str) and any(phrase in error_msg.lower() for phrase in ["invalid", "not exist", "not found", "doesn't exist"])):
                                                for stream in problematic_streams:
                                                    if stream in streams:
                                                        streams_to_remove.add(stream)
                                                        logger.info(
                                                            f"Binance {market}: "
                                                            f"стрим {stream} будет удален из списка подписки (не существует на бирже)"
                                                        )
                                            
                                            await on_error({
                                                "exchange": "binance",
                                                "market": market,
                                                "connection_id": f"ws-subscribe-{len(streams)}",
                                                "type": "subscribe_error",
                                                "error": error_msg,
                                                "code": error_code,
                                                "problematic_streams": problematic_streams[:20],  # Ограничиваем для логирования
                                                "streams_count": len(problematic_streams),
                                            })
                                            
                                            # Удаляем проблемные streams из списка
                                            if streams_to_remove:
                                                removed = [s for s in streams if s in streams_to_remove]
                                                streams[:] = [s for s in streams if s not in streams_to_remove]
                                                if removed:
                                                    logger.warning(
                                                        f"Binance {market}: "
                                                        f"удалены стримы из списка подписки: {', '.join(removed[:10])}"
                                                        f"{' и еще ' + str(len(removed) - 10) + ' стримов' if len(removed) > 10 else ''}"
                                                    )
                                                    streams_to_remove.clear()
                                                    
                                                    # Если все streams были удалены, прекращаем работу
                                                    if not streams:
                                                        logger.warning(
                                                            f"Binance {market}: "
                                                            f"все стримы были удалены, прекращаем работу соединения"
                                                        )
                                                        break
                                            else:
                                                # Если не удалось определить проблемные streams, просто переподключаемся
                                                break
                                        else:
                                            # Успешное подтверждение подписки (result может быть null - это нормально)
                                            subscription_confirmed = True
                                            logger.info(f"Binance {market}: подписка подтверждена для {len(streams)} стримов")
                                            # Пропускаем это сообщение, так как это только подтверждение
                                            continue
                                    
                                    # Если это не ответ на подписку, но есть continuous_kline - подписка работает
                                    if not subscription_confirmed and payload.get("e") == "continuous_kline":
                                        subscription_confirmed = True
                                        first_data_received = True
                                        logger.info(f"Binance {market}: подписка работает (получено continuous_kline сообщение)")
                                    elif payload.get("e") == "continuous_kline":
                                        first_data_received = True
                                    
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
                                # Логируем закрытие соединения с информацией о причине
                                is_scheduled_close = connection_state.get("is_scheduled_reconnect", False)
                                if is_scheduled_close:
                                    logger.info(f"Binance {market}: WebSocket закрыт (CLOSE) - плановое переподключение")
                                else:
                                    logger.warning(f"Binance {market}: WebSocket закрыт (CLOSE) - соединение разорвано")
                                # Счётчик переподключений увеличится в следующей итерации цикла в блоке if is_reconnect
                                if was_connected and not is_scheduled_close:
                                    await on_error({
                                        "exchange": "binance",
                                        "market": market,
                                        "connection_id": f"ws-subscribe-{len(streams)}",
                                        "type": "reconnect",
                                        "reason": "connection_closed",
                                    })
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.warning(f"Binance {market}: WebSocket ошибка (ERROR) - соединение разорвано")
                                # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                                if was_connected:
                                    await on_error({
                                        "exchange": "binance",
                                        "market": market,
                                        "connection_id": f"ws-subscribe-{len(streams)}",
                                        "type": "reconnect",
                                        "reason": "websocket_error",
                                    })
                                break
                        
                        # Если вышли из цикла без подтверждения и без данных - переподключаемся
                        if not subscription_confirmed and not first_data_received:
                            logger.warning(
                                f"Binance {market}: подписка не подтверждена и данных не получено "
                                f"(получено сообщений: {messages_received}), переподключение..."
                            )
                            # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                            # Но нужно сохранить was_connected, чтобы счётчик увеличился
                            if was_connected:
                                await on_error({
                                    "exchange": "binance",
                                    "market": market,
                                    "connection_id": f"ws-subscribe-{len(streams)}",
                                    "type": "reconnect",
                                    "reason": "subscription_not_confirmed",
                                })
                            # Не сбрасываем was_connected здесь, чтобы счётчик увеличился при следующей итерации
                            continue
                    finally:
                        # Отменяем задачу планового переподключения, если соединение закрылось раньше
                        scheduled_reconnect_task.cancel()
                        if 'symbol_check_task_subscribe' in locals():
                            symbol_check_task_subscribe.cancel()
                        try:
                            await scheduled_reconnect_task
                        except asyncio.CancelledError:
                            pass
                        try:
                            if 'symbol_check_task_subscribe' in locals():
                                await symbol_check_task_subscribe
                        except asyncio.CancelledError:
                            pass
                finally:
                    # Уменьшаем счётчик при выходе из соединения (включая случай неудачной подписки)
                    _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                    # ВАЖНО: НЕ сбрасываем was_connected здесь, если соединение было установлено
                    # Это нужно для правильного подсчёта переподключений при следующей итерации
                    # was_connected будет сброшен только при успешном подключении в следующей итерации
                    # (когда reconnect_attempt будет сброшен в 0)
        
        except asyncio.CancelledError:
            break
        except (ConnectionResetError, ConnectionError) as e:
            # Обработка ConnectionResetError (WinError 10054) - соединение принудительно закрыто удаленным хостом
            error_msg = f"Соединение принудительно закрыто удаленным хостом: {e}"
            logger.warning(f"Binance {market} (subscribe mode): {error_msg}")
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                _stats[market]["reconnects"] += 1
                logger.info(f"Binance {market}: переподключение из-за разрыва (счётчик: {_stats[market]['reconnects']})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "connection_id": f"ws-subscribe-{len(streams)}",
                "error": error_msg,
                "error_type": "connection_reset",
            })
            # Небольшая задержка перед переподключением
            await asyncio.sleep(min(2 ** min(reconnect_attempt - 1, 5), 60))
        except Exception as e:
            logger.error(f"Ошибка в WS соединении Binance {market} (subscribe mode): {e}")
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                _stats[market]["reconnects"] += 1
                logger.info(f"Binance {market}: переподключение из-за ошибки (счётчик: {_stats[market]['reconnects']})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "error": str(e),
            })
            # Небольшая задержка перед переподключением
            await asyncio.sleep(min(2 ** min(reconnect_attempt - 1, 5), 60))


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
    # Проверяем наличие ошибок в payload перед обработкой
    if isinstance(payload, dict):
        # Проверяем наличие поля error
        if "error" in payload:
            error_info = payload.get("error", {})
            error_msg = error_info.get("msg", "Unknown error") if isinstance(error_info, dict) else str(error_info)
            error_code = error_info.get("code", "Unknown") if isinstance(error_info, dict) else "Unknown"
            logger.warning(f"Binance {market}: ошибка в сообщении kline (code: {error_code}): {error_msg}")
            return
        # Проверяем наличие кода ошибки (если есть code и он не 200)
        if "code" in payload and payload.get("code") != 200:
            error_msg = payload.get("msg", f"Error code: {payload.get('code')}")
            logger.warning(f"Binance {market}: ошибка в сообщении kline (code: {payload.get('code')}): {error_msg}")
            return
    
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
    _builder = CandleBuilder(
        maxlen=config.memory_max_candles_per_symbol,
        on_trade=on_trade,
        on_candle=on_candle,
    )
    
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
    
    # Сохраняем символы в БД при запуске
    if spot_symbols:
        await db.upsert_active_symbols("binance", "spot", spot_symbols)
        logger.info(f"Binance spot: сохранено {len(spot_symbols)} символов в БД")
    if linear_symbols:
        await db.upsert_active_symbols("binance", "linear", linear_symbols)
        logger.info(f"Binance linear: сохранено {len(linear_symbols)} символов в БД")
    
    _tasks = []
    _spot_tasks = []
    _linear_tasks = []
    
    # Запускаем SPOT
    if fetch_spot and spot_symbols:
        _stats["spot"]["active_symbols"] = len(spot_symbols)
        
        # Строим streams для SPOT: "btcusdt@kline_1s"
        spot_streams = [f"{sym.lower()}@kline_1s" for sym in spot_symbols]
        # Валидируем стримы перед подпиской
        spot_streams = _validate_streams(spot_streams, "spot")
        spot_chunks = _chunk_list(spot_streams, STREAMS_PER_CONNECTION)
        
        logger.info(f"Binance spot: запущено {len(spot_chunks)} соединений для {len(spot_streams)} валидных стримов (из {len(spot_symbols)} символов)")
        
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
        # Валидируем стримы перед подпиской
        linear_streams = _validate_streams(linear_streams, "linear")
        linear_chunks = _chunk_list(linear_streams, STREAMS_PER_CONNECTION)
        
        logger.info(f"Binance linear: запущено {len(linear_chunks)} соединений для {len(linear_streams)} валидных стримов (из {len(linear_symbols)} символов)")
        
        for i, chunk in enumerate(linear_chunks):
            task = asyncio.create_task(_ws_connection_worker_subscribe(
                streams=chunk,
                market="linear",
                on_candle=on_candle,
                on_error=on_error,
            ))
            _tasks.append(task)
            _linear_tasks.append(task)
            
            # Добавляем задержку между запуском задач, чтобы избежать одновременных подключений
            # и превышения rate limit (распределяем попытки подключения во времени)
            if i < len(linear_chunks) - 1:  # Не ждём после последней задачи
                await asyncio.sleep(1.0)  # 1 секунда между запусками для более равномерного распределения
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
    global _tasks, _spot_tasks, _linear_tasks, _builder, _session, _connection_attempts
    
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
    _connection_attempts.clear()
    
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
    # Это гарантирует, что количество активных соединений соответствует реальным активным задачам
    _stats["spot"]["active_connections"] = len([t for t in _spot_tasks if not t.done()])
    _stats["linear"]["active_connections"] = len([t for t in _linear_tasks if not t.done()])
    
    return _stats.copy()

