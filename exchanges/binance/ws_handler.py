"""
WebSocket обработчик для Binance
Binance предоставляет уже готовые 1-секундные свечи через Kline streams
"""
import ssl
import certifi
import asyncio
from typing import Awaitable, Callable, List, Dict, Set
import aiohttp
import json
import socket
import time
from collections import deque
import random
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from core.symbol_cache_logger import report_symbol_cache_update
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

# Критичные коды ошибок, требующие переподключения
# Остальные ошибки (400, 1003, 429, 502, 503, 504) обрабатываются без переподключения
CRITICAL_ERROR_CODES = [
    401,   # Unauthorized - ошибка авторизации
    403,   # Forbidden - доступ запрещён
    1002,  # Invalid opcode - ошибка протокола WebSocket
    1011,  # Internal error - внутренняя ошибка сервера
    500,   # Internal Server Error - критичная ошибка сервера
]

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
# Символы хранятся в памяти в переменных spot_symbols, linear_symbols и streams
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
_stats_lock: asyncio.Lock | None = None
# Словарь для отслеживания соединений: connection_id -> (ws, streams_list, market)
_active_connections: Dict[str, tuple] = {}


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


def _symbol_to_stream(symbol: str, market: str) -> str:
    """
    Преобразует символ в stream формат для Binance.
    
    Args:
        symbol: Символ в верхнем регистре (например, "BTCUSDT")
        market: Рынок ("spot" или "linear")
        
    Returns:
        Stream строка (например, "btcusdt@kline_1s" или "btcusdt_perpetual@continuousKline_1s")
    """
    symbol_lower = symbol.lower()
    if market == "spot":
        return f"{symbol_lower}@kline_1s"
    else:  # linear
        return f"{symbol_lower}_perpetual@continuousKline_1s"


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
    connection_id: str = None,
):
    """
    WebSocket worker для одного соединения с множественными стримами.
    
    Args:
        streams: Список streams для подписки
        market: Тип рынка ("spot" или "linear")
        url: URL для WebSocket соединения
        on_candle: Callback для обработки свечей
        on_error: Callback для обработки ошибок
        connection_id: Уникальный идентификатор соединения (например, "WS-1")
    """
    if connection_id is None:
        connection_id = f"streams-{len(streams)}"
    
    reconnect_attempt = 0
    connection_state = {"is_scheduled_reconnect": False, "reconnect_reason": None}
    was_connected = False  # Флаг успешного подключения
    current_ws = None  # Текущее WebSocket соединение для динамических подписок
    
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
                # Обновляем список символов перед переподключением
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        # Сохраняем старый список ПЕРЕД получением нового
                        if market == "spot":
                            old_symbols = _active_spot_symbols.copy()
                        else:
                            old_symbols = _active_linear_symbols.copy()
                        
                        fresh_symbols = await fetch_symbols(market)
                        
                        # Сравниваем старый и новый списки для обнаружения реальных листингов
                        old_symbols_set = set(old_symbols)
                        fresh_symbols_set = set(fresh_symbols)
                        added_symbols = fresh_symbols_set - old_symbols_set
                        
                        # Обновляем глобальный список
                        if market == "spot":
                            _active_spot_symbols[:] = fresh_symbols
                        else:
                            _active_linear_symbols[:] = fresh_symbols
                        
                        # Логируем обнаружение листингов только если действительно есть новые символы
                        if added_symbols:
                            added_list = sorted(list(added_symbols))
                            added_names = added_list[:10]
                            added_count = len(added_list)
                            logger.info(
                                f"Binance {market}: обновление списка символов перед переподключением..."
                            )
                            logger.info(
                                f"Binance {market}: обнаружен листинг: найдено {added_count} новых символов: "
                                f"{', '.join(added_names)}{f' и еще {added_count - 10} символов' if added_count > 10 else ''}"
                            )
                            logger.info(
                                f"Binance {market}: переподключение из-за листинга {added_count} символов"
                            )
                        
                        # Фильтруем streams, оставляя только актуальные символы
                        active_symbols_set = set(fresh_symbols)
                        valid_streams = []
                        for stream in streams:
                            symbol = _extract_symbols_from_streams([stream], market)
                            if symbol and symbol[0] in active_symbols_set:
                                valid_streams.append(stream)
                        
                        removed_count = len(streams) - len(valid_streams)
                        if removed_count > 0:
                            logger.info(
                                f"Binance {market} [{connection_id}]: "
                                f"при переподключении удалено {removed_count} неактуальных стримов"
                            )
                        streams[:] = valid_streams
                
                # Если это не плановое переподключение, увеличиваем счётчик и логируем
                if not is_scheduled:
                    delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                    if _stats_lock:
                        async with _stats_lock:
                            _stats[market]["reconnects"] += 1
                            reconnect_count = _stats[market]["reconnects"]
                    
                    # Получаем причину переподключения из connection_state
                    reconnect_reason = connection_state.get("reconnect_reason", "неизвестная причина")
                    
                    logger.info(f"Binance {market} [{connection_id}]: переподключение (счётчик: {reconnect_count}, причина: {reconnect_reason})")
                    
                    await on_error({
                        "exchange": "binance",
                        "market": market,
                        "connection_id": connection_id,
                        "type": "reconnect",
                        "reason": reconnect_reason,
                    })
                    # Сбрасываем причину после использования
                    connection_state["reconnect_reason"] = None
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
            
            async with _session.ws_connect(url, heartbeat=25) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                # Устанавливаем флаг успешного подключения
                # Если это было переподключение, was_connected уже был True, оставляем его
                # Если это первое подключение, устанавливаем в True
                was_connected = True
                
                logger.info(f"Binance {market} [{connection_id}]: успешное подключение ({len(streams)} streams)")
                if _stats_lock:
                    async with _stats_lock:
                        _stats[market]["active_connections"] += 1
                
                # Список streams, которые нужно удалить из-за ошибок подписки
                streams_to_remove = set()
                
                # Создаём задачу для планового переподключения через 23 часа
                scheduled_reconnect_task = asyncio.create_task(
                    _schedule_reconnect(ws, SCHEDULED_RECONNECT_INTERVAL, market, streams, on_error, connection_state)
                )
                
                
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
                                        
                                        # Проверяем, является ли ошибка критичной
                                        is_critical = error_code in CRITICAL_ERROR_CODES if isinstance(error_code, int) else False
                                        
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
                                                        f"Binance {market} [{connection_id}]: "
                                                        f"стрим {stream} будет удален из списка подписки (не существует на бирже)"
                                                    )
                                        
                                        # Логируем ошибку
                                        if is_critical:
                                            logger.error(f"Binance {market} [{connection_id}]: критичная ошибка от сервера (code: {error_code}): {error_msg}")
                                        else:
                                            logger.warning(f"Binance {market} [{connection_id}]: некритичная ошибка от сервера (code: {error_code}): {error_msg}")
                                        
                                        logger.debug(f"Binance {market} [{connection_id}]: полный ответ: {json.dumps(payload)}")
                                        await on_error({
                                            "exchange": "binance",
                                            "market": market,
                                            "connection_id": connection_id,
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
                                                    f"Binance {market} [{connection_id}]: "
                                                    f"удалены стримы из списка подписки: {', '.join(removed[:10])}"
                                                    f"{' и еще ' + str(len(removed) - 10) + ' стримов' if len(removed) > 10 else ''}"
                                                )
                                                streams_to_remove.clear()
                                                
                                                # Если все streams были удалены, прекращаем работу
                                                if not streams:
                                                    logger.warning(
                                                        f"Binance {market} [{connection_id}]: "
                                                        f"все стримы были удалены, прекращаем работу соединения"
                                                    )
                                                    break
                                        
                                        # Переподключаемся только при критичных ошибках
                                        if is_critical:
                                            connection_state["reconnect_reason"] = f"критичная ошибка от сервера (code: {error_code}): {error_msg}"
                                            logger.warning(f"Binance {market} [{connection_id}]: переподключение из-за критичной ошибки")
                                            break
                                        else:
                                            # Некритичная ошибка - продолжаем работу
                                            continue
                                    
                                    # Проверяем наличие кода ошибки (если есть code и он не 200)
                                    if "code" in payload and payload.get("code") != 200:
                                        error_code = payload.get("code")
                                        error_msg = payload.get("msg", f"Error code: {error_code}")
                                        
                                        # Проверяем, является ли ошибка критичной
                                        is_critical = error_code in CRITICAL_ERROR_CODES if isinstance(error_code, int) else False
                                        
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
                                                        f"Binance {market} [{connection_id}]: "
                                                        f"стрим {stream} будет удален из списка подписки (не существует на бирже)"
                                                    )
                                        
                                        if is_critical:
                                            logger.error(f"Binance {market} [{connection_id}]: критичная ошибка от сервера (code: {error_code}): {error_msg}")
                                        else:
                                            logger.warning(f"Binance {market} [{connection_id}]: некритичная ошибка от сервера (code: {error_code}): {error_msg}")
                                        
                                        logger.debug(f"Binance {market} [{connection_id}]: полный ответ: {json.dumps(payload)}")
                                        await on_error({
                                            "exchange": "binance",
                                            "market": market,
                                            "connection_id": connection_id,
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
                                                    f"Binance {market} [{connection_id}]: "
                                                    f"удалены стримы из списка подписки: {', '.join(removed[:10])}"
                                                    f"{' и еще ' + str(len(removed) - 10) + ' стримов' if len(removed) > 10 else ''}"
                                                )
                                                streams_to_remove.clear()
                                                
                                                # Если все streams были удалены, прекращаем работу
                                                if not streams:
                                                    logger.warning(
                                                        f"Binance {market} [{connection_id}]: "
                                                        f"все стримы были удалены, прекращаем работу соединения"
                                                    )
                                                    break
                                        
                                        # Переподключаемся только при критичных ошибках
                                        if is_critical:
                                            connection_state["reconnect_reason"] = f"критичная ошибка от сервера (code: {error_code}): {error_msg}"
                                            logger.warning(f"Binance {market} [{connection_id}]: переподключение из-за критичной ошибки")
                                            break
                                        else:
                                            # Некритичная ошибка - продолжаем работу
                                            continue
                                
                                await _handle_kline_message(payload, market, on_candle)
                            except Exception as e:
                                logger.error(f"Ошибка обработки сообщения Binance {market} [{connection_id}]: {e}")
                                logger.error(f"Binance {market} [{connection_id}]: Payload (первые 200 символов): {msg.data[:200] if len(msg.data) > 200 else msg.data}")
                                # При ошибке обработки сообщения продолжаем работу, не переподключаемся
                        
                        elif msg.type == aiohttp.WSMsgType.PING:
                            # Явно отвечаем на ping от сервера Binance
                            # Binance отправляет ping каждые 20 секунд (spot) или 3 минуты (linear)
                            # Таймаут разрыва: 1 минута (spot) или 10 минут (linear) без pong
                            try:
                                await ws.pong()
                            except Exception as e:
                                logger.warning(f"Binance {market} [{connection_id}]: ошибка при отправке pong: {e}")
                        
                        elif msg.type == aiohttp.WSMsgType.PONG:
                            # Получен pong от сервера - соединение активно
                            # Логируем только для отладки (можно убрать в production)
                            pass
                        
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            # Логируем закрытие соединения с информацией о причине
                            is_scheduled_close = connection_state.get("is_scheduled_reconnect", False)
                            if is_scheduled_close:
                                logger.info(f"Binance {market} [{connection_id}]: WebSocket закрыт (CLOSE) - плановое переподключение")
                            else:
                                # Извлекаем код закрытия и причину
                                close_code = None
                                close_reason = None
                                try:
                                    if hasattr(msg, 'data') and msg.data:
                                        close_code = msg.data
                                    if hasattr(msg, 'extra') and msg.extra:
                                        if 'close_reason' in msg.extra:
                                            close_reason = str(msg.extra['close_reason'])
                                except Exception:
                                    pass
                                
                                # Маппинг кодов закрытия WebSocket на понятные сообщения
                                close_code_messages = {
                                    1000: "Нормальное закрытие",
                                    1001: "Удаленная сторона ушла",
                                    1002: "Ошибка протокола",
                                    1003: "Неподдерживаемый тип данных",
                                    1006: "Аномальное закрытие (без кода)",
                                    1007: "Невалидные данные",
                                    1008: "Нарушение политики",
                                    1009: "Сообщение слишком большое",
                                    1010: "Ошибка расширения",
                                    1011: "Внутренняя ошибка сервера",
                                    1012: "Сервис перезапускается",
                                    1013: "Попробуйте позже",
                                    1014: "Плохой шлюз",
                                    1015: "Ошибка TLS handshake",
                                }
                                
                                close_code_msg = close_code_messages.get(close_code, f"Неизвестный код: {close_code}") if close_code else "Код не указан"
                                
                                # Сохраняем причину переподключения
                                reason_text = f"соединение закрыто (код: {close_code}, {close_code_msg})"
                                if close_reason:
                                    reason_text += f", причина: {close_reason}"
                                connection_state["reconnect_reason"] = reason_text
                                
                                logger.warning(
                                    f"Binance {market} [{connection_id}]: WebSocket закрыт (CLOSE) - соединение разорвано, "
                                    f"код: {close_code} ({close_code_msg})"
                                    + (f", причина: {close_reason}" if close_reason else "")
                                )
                            # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                            if was_connected and not is_scheduled_close:
                                await on_error({
                                    "exchange": "binance",
                                    "market": market,
                                    "connection_id": connection_id,
                                    "type": "reconnect",
                                    "reason": "connection_closed",
                                    "close_code": close_code,
                                    "close_reason": close_reason,
                                })
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            # Получаем детали ошибки из WebSocket
                            error_details = None
                            try:
                                if hasattr(ws, 'exception') and ws.exception():
                                    error_details = str(ws.exception())
                            except Exception:
                                pass
                            
                            error_msg = f"WebSocket ошибка (ERROR) - соединение разорвано"
                            if error_details:
                                error_msg += f", детали: {error_details}"
                            
                            # Сохраняем причину переподключения
                            reason_text = f"WebSocket ошибка"
                            if error_details:
                                reason_text += f": {error_details}"
                            connection_state["reconnect_reason"] = reason_text
                            
                            logger.warning(f"Binance {market} [{connection_id}]: {error_msg}")
                            # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                            if was_connected:
                                await on_error({
                                    "exchange": "binance",
                                    "market": market,
                                    "connection_id": connection_id,
                                    "type": "reconnect",
                                    "reason": "websocket_error",
                                    "error_details": error_details,
                                })
                            break
                finally:
                    # Отменяем задачу планового переподключения, если соединение закрылось раньше
                    scheduled_reconnect_task.cancel()
                    try:
                        await scheduled_reconnect_task
                    except asyncio.CancelledError:
                        pass
                
                # Удаляем соединение из регистрации
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        _active_connections.pop(connection_id, None)
                current_ws = None
                
                if _stats_lock:
                    async with _stats_lock:
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
            logger.warning(f"Binance {market} [{connection_id}]: {error_msg}")
            # Сохраняем причину переподключения
            connection_state["reconnect_reason"] = f"разрыв соединения: {e}"
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                if _stats_lock:
                    async with _stats_lock:
                        _stats[market]["reconnects"] += 1
                        reconnect_count = _stats[market]["reconnects"]
                logger.info(f"Binance {market} [{connection_id}]: переподключение из-за разрыва (счётчик: {reconnect_count})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "error_type": "connection_reset",
            })
            # Небольшая задержка перед переподключением
            await asyncio.sleep(min(2 ** min(reconnect_attempt - 1, 5), 60))
        except Exception as e:
            logger.error(f"Ошибка в WS соединении Binance {market} [{connection_id}]: {e}", exc_info=True)
            # Сохраняем причину переподключения
            connection_state["reconnect_reason"] = f"исключение: {type(e).__name__}: {e}"
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                if _stats_lock:
                    async with _stats_lock:
                        _stats[market]["reconnects"] += 1
                        reconnect_count = _stats[market]["reconnects"]
                logger.info(f"Binance {market} [{connection_id}]: переподключение из-за ошибки (счётчик: {reconnect_count})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "connection_id": connection_id,
                "error": str(e),
                "error_type": type(e).__name__,
            })
            # Небольшая задержка перед переподключением
            await asyncio.sleep(min(2 ** min(reconnect_attempt - 1, 5), 60))


async def _ws_connection_worker_subscribe(
    streams: List[str],
    market: str,
    on_candle: Callable[[Candle], Awaitable[None]],
    on_error: Callable[[dict], Awaitable[None]],
    connection_id: str = None,
):
    """
    WebSocket worker для Futures с подпиской через JSON (wss://fstream.binance.com/ws).
    Отличается от /stream тем, что требует явной подписки через JSON.
    
    Args:
        streams: Список streams для подписки
        market: Тип рынка ("spot" или "linear")
        on_candle: Callback для обработки свечей
        on_error: Callback для обработки ошибок
        connection_id: Уникальный идентификатор соединения (например, "WS-1")
    """
    if connection_id is None:
        connection_id = f"ws-subscribe-{len(streams)}"
    
    reconnect_attempt = 0
    connection_state = {"is_scheduled_reconnect": False, "reconnect_reason": None}
    was_connected = False  # Флаг успешного подключения
    current_ws = None  # Текущее WebSocket соединение для динамических подписок
    
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
                # Обновляем список символов перед переподключением
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        # Сохраняем старый список ПЕРЕД получением нового
                        if market == "spot":
                            old_symbols = _active_spot_symbols.copy()
                        else:
                            old_symbols = _active_linear_symbols.copy()
                        
                        fresh_symbols = await fetch_symbols(market)
                        
                        # Сравниваем старый и новый списки для обнаружения реальных листингов
                        old_symbols_set = set(old_symbols)
                        fresh_symbols_set = set(fresh_symbols)
                        added_symbols = fresh_symbols_set - old_symbols_set
                        
                        # Обновляем глобальный список
                        if market == "spot":
                            _active_spot_symbols[:] = fresh_symbols
                        else:
                            _active_linear_symbols[:] = fresh_symbols
                        
                        # Логируем обнаружение листингов только если действительно есть новые символы
                        if added_symbols:
                            added_list = sorted(list(added_symbols))
                            added_names = added_list[:10]
                            added_count = len(added_list)
                            logger.info(
                                f"Binance {market} (subscribe mode): обновление списка символов перед переподключением..."
                            )
                            logger.info(
                                f"Binance {market} (subscribe mode): обнаружен листинг: найдено {added_count} новых символов: "
                                f"{', '.join(added_names)}{f' и еще {added_count - 10} символов' if added_count > 10 else ''}"
                            )
                            logger.info(
                                f"Binance {market} (subscribe mode): переподключение из-за листинга {added_count} символов"
                            )
                        
                        # Фильтруем streams, оставляя только актуальные символы
                        active_symbols_set = set(fresh_symbols)
                        valid_streams = []
                        for stream in streams:
                            symbol = _extract_symbols_from_streams([stream], market)
                            if symbol and symbol[0] in active_symbols_set:
                                valid_streams.append(stream)
                        
                        removed_count = len(streams) - len(valid_streams)
                        if removed_count > 0:
                            logger.info(
                                f"Binance {market} [{connection_id}]: "
                                f"при переподключении удалено {removed_count} неактуальных стримов"
                            )
                        streams[:] = valid_streams
                
                # Если это не плановое переподключение, увеличиваем счётчик и логируем
                if not is_scheduled:
                    delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                    # Увеличиваем счётчик переподключений здесь (один раз)
                    if _stats_lock:
                        async with _stats_lock:
                            _stats[market]["reconnects"] += 1
                            reconnect_count = _stats[market]["reconnects"]
                    
                    # Получаем причину переподключения из connection_state
                    reconnect_reason = connection_state.get("reconnect_reason", "неизвестная причина")
                    
                    logger.info(f"Binance {market} [{connection_id}]: переподключение (счётчик: {reconnect_count}, причина: {reconnect_reason})")
                    
                    await on_error({
                        "exchange": "binance",
                        "market": market,
                        "connection_id": connection_id,
                        "type": "reconnect",
                        "reason": reconnect_reason,
                    })
                    # Сбрасываем причину после использования
                    connection_state["reconnect_reason"] = None
                    await asyncio.sleep(delay)
                else:
                    # Для планового переподключения не увеличиваем счётчик
                    await asyncio.sleep(1)  # Небольшая задержка перед новым подключением
            
            if _session is None or _session.closed:
                logger.error(f"Binance {market} [{connection_id}]: сессия не инициализирована или закрыта")
                await asyncio.sleep(5)
                continue
            
            # Проверяем лимит попыток подключения
            rate_limit_delay = await _check_connection_rate_limit()
            if rate_limit_delay > 0:
                await asyncio.sleep(rate_limit_delay)
                continue
            
            url = FAPI_WS_ENDPOINT_WS
            
            # Логируем попытку подключения для диагностики
            logger.info(f"Binance {market} [{connection_id}]: попытка подключения (попытка {reconnect_attempt})")
            
            async with _session.ws_connect(url, heartbeat=25) as ws:
                # Сбрасываем счётчик после успешного подключения
                reconnect_attempt = 0
                # Устанавливаем флаг успешного подключения
                # Если это было переподключение, was_connected уже был True, оставляем его
                # Если это первое подключение, устанавливаем в True
                was_connected = True
                current_ws = ws
                
                # Регистрируем соединение для динамических обновлений
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        _active_connections[connection_id] = (ws, streams, market)
                
                logger.info(f"Binance {market} [{connection_id}]: успешное подключение ({len(streams)} streams)")
                if _stats_lock:
                    async with _stats_lock:
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
                    logger.info(f"Binance {market} [{connection_id}]: отправлена подписка на {len(streams)} стримов")
                    logger.debug(f"Binance {market} [{connection_id}]: примеры стримов: {streams[:3] if len(streams) > 0 else 'нет'}")
                    
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
                                            f"Binance {market} [{connection_id}]: сообщение #{messages_received} после подписки: "
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
                                            
                                            # Проверяем, является ли ошибка критичной
                                            is_critical = error_code in CRITICAL_ERROR_CODES if isinstance(error_code, int) else False
                                            
                                            # Извлекаем информацию о проблемных стримах из ответа или используем весь список
                                            problematic_streams = streams
                                            if isinstance(error_info, dict) and "params" in error_info:
                                                problematic_streams = error_info.get("params", streams)
                                            elif isinstance(payload, dict) and "params" in payload:
                                                problematic_streams = payload.get("params", streams)
                                            
                                            # Логируем проблемные символы
                                            if is_critical:
                                                logger.error(f"Binance {market} [{connection_id}]: критичная ошибка подписки (code: {error_code}): {error_msg}")
                                            else:
                                                logger.warning(f"Binance {market} [{connection_id}]: некритичная ошибка подписки (code: {error_code}): {error_msg}")
                                            
                                            logger.warning(f"Binance {market} [{connection_id}]: количество проблемных стримов: {len(problematic_streams)}")
                                            if len(problematic_streams) <= 10:
                                                logger.debug(f"Binance {market} [{connection_id}]: проблемные стримы: {problematic_streams}")
                                            else:
                                                logger.debug(f"Binance {market} [{connection_id}]: первые 10 проблемных стримов: {problematic_streams[:10]}")
                                            logger.debug(f"Binance {market} [{connection_id}]: полный ответ: {json.dumps(payload)}")
                                            
                                            # Если ошибка связана с несуществующими символами, добавляем их в список на удаление
                                            # Проверяем типичные коды ошибок для несуществующих символов
                                            if error_code in [400, 1003] or (isinstance(error_msg, str) and any(phrase in error_msg.lower() for phrase in ["invalid", "not exist", "not found", "doesn't exist"])):
                                                for stream in problematic_streams:
                                                    if stream in streams:
                                                        streams_to_remove.add(stream)
                                                        logger.info(
                                                            f"Binance {market} [{connection_id}]: "
                                                            f"стрим {stream} будет удален из списка подписки (не существует на бирже)"
                                                        )
                                            
                                            await on_error({
                                                "exchange": "binance",
                                                "market": market,
                                                "connection_id": connection_id,
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
                                                        f"Binance {market} [{connection_id}]: "
                                                        f"удалены стримы из списка подписки: {', '.join(removed[:10])}"
                                                        f"{' и еще ' + str(len(removed) - 10) + ' стримов' if len(removed) > 10 else ''}"
                                                    )
                                                    streams_to_remove.clear()
                                                    
                                                    # Если все streams были удалены, прекращаем работу
                                                    if not streams:
                                                        logger.warning(
                                                            f"Binance {market} [{connection_id}]: "
                                                            f"все стримы были удалены, прекращаем работу соединения"
                                                        )
                                                        break
                                            
                                            # Переподключаемся только при критичных ошибках
                                            if is_critical:
                                                connection_state["reconnect_reason"] = f"критичная ошибка подписки (code: {error_code}): {error_msg}"
                                                logger.warning(f"Binance {market} [{connection_id}]: переподключение из-за критичной ошибки подписки")
                                                break
                                            else:
                                                # Некритичная ошибка - продолжаем работу, пытаемся обработать остальные сообщения
                                                # Если это ошибка несуществующих символов, они уже удалены, продолжаем
                                                continue
                                        else:
                                            # Успешное подтверждение подписки (result может быть null - это нормально)
                                            subscription_confirmed = True
                                            logger.info(f"Binance {market} [{connection_id}]: подписка подтверждена для {len(streams)} стримов")
                                            # Пропускаем это сообщение, так как это только подтверждение
                                            continue
                                    
                                    # Если это не ответ на подписку, но есть continuous_kline - подписка работает
                                    if not subscription_confirmed and payload.get("e") == "continuous_kline":
                                        subscription_confirmed = True
                                        first_data_received = True
                                        logger.info(f"Binance {market} [{connection_id}]: подписка работает (получено continuous_kline сообщение)")
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
                                    logger.error(f"Ошибка обработки сообщения Binance {market} [{connection_id}]: {e}")
                                    logger.error(f"Binance {market} [{connection_id}]: Payload (первые 200 символов): {msg.data[:200] if len(msg.data) > 200 else msg.data}")
                            
                            elif msg.type == aiohttp.WSMsgType.PING:
                                # Явно отвечаем на ping от сервера Binance
                                # Binance отправляет ping каждые 20 секунд (spot) или 3 минуты (linear)
                                # Таймаут разрыва: 1 минута (spot) или 10 минут (linear) без pong
                                try:
                                    await ws.pong()
                                except Exception as e:
                                    logger.warning(f"Binance {market} [{connection_id}]: ошибка при отправке pong: {e}")
                            
                            elif msg.type == aiohttp.WSMsgType.PONG:
                                # Получен pong от сервера - соединение активно
                                # Логируем только для отладки (можно убрать в production)
                                pass
                            
                            elif msg.type == aiohttp.WSMsgType.CLOSE:
                                # Логируем закрытие соединения с информацией о причине
                                is_scheduled_close = connection_state.get("is_scheduled_reconnect", False)
                                if is_scheduled_close:
                                    logger.info(f"Binance {market} [{connection_id}]: WebSocket закрыт (CLOSE) - плановое переподключение")
                                else:
                                    # Извлекаем код закрытия и причину
                                    close_code = None
                                    close_reason = None
                                    try:
                                        if hasattr(msg, 'data') and msg.data:
                                            close_code = msg.data
                                        if hasattr(msg, 'extra') and msg.extra:
                                            if 'close_reason' in msg.extra:
                                                close_reason = str(msg.extra['close_reason'])
                                    except Exception:
                                        pass
                                    
                                    # Маппинг кодов закрытия WebSocket на понятные сообщения
                                    close_code_messages = {
                                        1000: "Нормальное закрытие",
                                        1001: "Удаленная сторона ушла",
                                        1002: "Ошибка протокола",
                                        1003: "Неподдерживаемый тип данных",
                                        1006: "Аномальное закрытие (без кода)",
                                        1007: "Невалидные данные",
                                        1008: "Нарушение политики",
                                        1009: "Сообщение слишком большое",
                                        1010: "Ошибка расширения",
                                        1011: "Внутренняя ошибка сервера",
                                        1012: "Сервис перезапускается",
                                        1013: "Попробуйте позже",
                                        1014: "Плохой шлюз",
                                        1015: "Ошибка TLS handshake",
                                    }
                                    
                                    close_code_msg = close_code_messages.get(close_code, f"Неизвестный код: {close_code}") if close_code else "Код не указан"
                                    
                                    # Сохраняем причину переподключения
                                    reason_text = f"соединение закрыто (код: {close_code}, {close_code_msg})"
                                    if close_reason:
                                        reason_text += f", причина: {close_reason}"
                                    connection_state["reconnect_reason"] = reason_text
                                    
                                    logger.warning(
                                        f"Binance {market} [{connection_id}]: WebSocket закрыт (CLOSE) - соединение разорвано, "
                                        f"код: {close_code} ({close_code_msg})"
                                        + (f", причина: {close_reason}" if close_reason else "")
                                    )
                                # Счётчик переподключений увеличится в следующей итерации цикла в блоке if is_reconnect
                                if was_connected and not is_scheduled_close:
                                    await on_error({
                                        "exchange": "binance",
                                        "market": market,
                                        "connection_id": connection_id,
                                        "type": "reconnect",
                                        "reason": "connection_closed",
                                        "close_code": close_code,
                                        "close_reason": close_reason,
                                    })
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                # Получаем детали ошибки из WebSocket
                                error_details = None
                                try:
                                    if hasattr(ws, 'exception') and ws.exception():
                                        error_details = str(ws.exception())
                                except Exception:
                                    pass
                                
                                error_msg = f"WebSocket ошибка (ERROR) - соединение разорвано"
                                if error_details:
                                    error_msg += f", детали: {error_details}"
                                
                                # Сохраняем причину переподключения
                                reason_text = f"WebSocket ошибка"
                                if error_details:
                                    reason_text += f": {error_details}"
                                connection_state["reconnect_reason"] = reason_text
                                
                                logger.warning(f"Binance {market} [{connection_id}]: {error_msg}")
                                # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                                if was_connected:
                                    await on_error({
                                        "exchange": "binance",
                                        "market": market,
                                        "connection_id": connection_id,
                                        "type": "reconnect",
                                        "reason": "websocket_error",
                                        "error_details": error_details,
                                    })
                                break
                        
                        # Если вышли из цикла без подтверждения и без данных - переподключаемся
                        # Проверяем ws.closed перед проверкой подписки
                        if ws.closed:
                            logger.warning(
                                f"Binance {market} [{connection_id}]: соединение закрыто до подтверждения подписки"
                            )
                            connection_state["reconnect_reason"] = "соединение закрыто до подтверждения подписки"
                        elif not subscription_confirmed and not first_data_received:
                            logger.warning(
                                f"Binance {market}: подписка не подтверждена и данных не получено "
                                f"(получено сообщений: {messages_received}), переподключение..."
                            )
                            # Сохраняем причину переподключения
                            connection_state["reconnect_reason"] = f"подписка не подтверждена (получено сообщений: {messages_received})"
                            # Счётчик реконнектов увеличивается в блоке if is_reconnect: при следующей итерации
                            # Но нужно сохранить was_connected, чтобы счётчик увеличился
                            if was_connected:
                                await on_error({
                                    "exchange": "binance",
                                    "market": market,
                                    "connection_id": connection_id,
                                    "type": "reconnect",
                                    "reason": "subscription_not_confirmed",
                                })
                            # Не сбрасываем was_connected здесь, чтобы счётчик увеличился при следующей итерации
                            continue
                    finally:
                        # Отменяем задачу планового переподключения, если соединение закрылось раньше
                        scheduled_reconnect_task.cancel()
                        try:
                            await scheduled_reconnect_task
                        except asyncio.CancelledError:
                            pass
                finally:
                    # Удаляем соединение из регистрации
                    if _symbol_update_lock:
                        async with _symbol_update_lock:
                            _active_connections.pop(connection_id, None)
                    current_ws = None
                    
                    # Уменьшаем счётчик при выходе из соединения (включая случай неудачной подписки)
                    if _stats_lock:
                        async with _stats_lock:
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
            logger.warning(f"Binance {market} [{connection_id}]: {error_msg}")
            # Сохраняем причину переподключения
            connection_state["reconnect_reason"] = f"разрыв соединения: {e}"
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                if _stats_lock:
                    async with _stats_lock:
                        _stats[market]["reconnects"] += 1
                        reconnect_count = _stats[market]["reconnects"]
                logger.info(f"Binance {market} [{connection_id}]: переподключение из-за разрыва (счётчик: {reconnect_count})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "connection_id": connection_id,
                "error": error_msg,
                "error_type": "connection_reset",
            })
            # Небольшая задержка перед переподключением
            await asyncio.sleep(min(2 ** min(reconnect_attempt - 1, 5), 60))
        except Exception as e:
            logger.error(f"Ошибка в WS соединении Binance {market} [{connection_id}]: {e}", exc_info=True)
            # Сохраняем причину переподключения
            connection_state["reconnect_reason"] = f"исключение: {type(e).__name__}: {e}"
            # Если было подключение, увеличиваем счётчик переподключений
            if was_connected:
                if _stats_lock:
                    async with _stats_lock:
                        _stats[market]["reconnects"] += 1
                        reconnect_count = _stats[market]["reconnects"]
                logger.info(f"Binance {market} [{connection_id}]: переподключение из-за ошибки (счётчик: {reconnect_count})")
            await on_error({
                "exchange": "binance",
                "market": market,
                "connection_id": connection_id,
                "error": str(e),
                "error_type": type(e).__name__,
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
    global _tasks, _spot_tasks, _linear_tasks
    
    # Ждём 5 минут перед первым обновлением
    await asyncio.sleep(300)
    
    while True:
        try:
            # Запрашиваем актуальный список символов
            new_symbols = await fetch_symbols(market)
            new_symbols_set = set(new_symbols)
            
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
                    exchange="Binance",
                    market=market,
                    has_changes=has_changes,
                    removed_count=len(removed_symbols),
                    added_count=len(added_symbols),
                    total_symbols=len(new_symbols)
                )
                
                # Обрабатываем удаленные символы
                for symbol in removed_symbols:
                    stream = _symbol_to_stream(symbol, market)
                    
                    # Находим все соединения, содержащие этот stream
                    # Создаем копию словаря для безопасной итерации
                    connections_to_update = []
                    for conn_id, (ws, streams_list, conn_market) in list(_active_connections.items()):
                        if conn_market == market and stream in streams_list:
                            connections_to_update.append((conn_id, ws, streams_list))
                    
                    # Удаляем stream из всех соединений
                    for conn_id, ws, streams_list in connections_to_update:
                        if stream in streams_list:
                            # Создаем новый список вместо модификации существующего
                            new_streams = [s for s in streams_list if s != stream]
                            # Обновляем кортеж в словаре
                            if _symbol_update_lock:
                                async with _symbol_update_lock:
                                    _active_connections[conn_id] = (ws, new_streams, market)
                            
                            logger.info(
                                f"Binance {market}: символ {symbol} удален с биржи, "
                                f"отписываемся от {conn_id}"
                            )
                            
                            # Для spot соединений нужно переподключиться (URL содержит streams)
                            # Для linear можно отправить UNSUBSCRIBE через JSON
                            if market == "linear":
                                # Проверяем ws.closed непосредственно перед отправкой
                                if not ws.closed:
                                    try:
                                        unsubscribe_msg = {
                                            "method": "UNSUBSCRIBE",
                                            "params": [stream],
                                            "id": 2
                                        }
                                        await ws.send_json(unsubscribe_msg)
                                    except Exception as e:
                                        logger.warning(
                                            f"Binance {market} [{conn_id}]: "
                                            f"ошибка при отписке от {stream}: {e}"
                                        )
                                else:
                                    logger.debug(
                                        f"Binance {market} [{conn_id}]: "
                                        f"соединение закрыто, пропускаем отписку от {stream}"
                                    )
                
                # Обрабатываем новые символы
                for symbol in added_symbols:
                    stream = _symbol_to_stream(symbol, market)
                    
                    # Находим соединение с наименьшим количеством streams (но меньше лимита)
                    # Создаем копию словаря для безопасной итерации
                    best_connection = None
                    best_conn_id = None
                    best_streams = None
                    min_count = STREAMS_PER_CONNECTION
                    
                    for conn_id, (ws, streams_list, conn_market) in list(_active_connections.items()):
                        if conn_market == market and len(streams_list) < STREAMS_PER_CONNECTION:
                            if len(streams_list) < min_count:
                                min_count = len(streams_list)
                                best_connection = ws
                                best_conn_id = conn_id
                                best_streams = streams_list
                    
                    if best_connection:
                        # Проверяем ws.closed непосредственно перед отправкой
                        if not best_connection.closed:
                            # Создаем новый список вместо модификации существующего
                            new_streams = best_streams + [stream]
                            # Обновляем кортеж в словаре
                            if _symbol_update_lock:
                                async with _symbol_update_lock:
                                    _active_connections[best_conn_id] = (best_connection, new_streams, market)
                            
                            # Для spot нужно переподключиться (URL содержит streams)
                            # Для linear отправляем SUBSCRIBE через JSON
                            if market == "linear":
                                try:
                                    subscribe_msg = {
                                        "method": "SUBSCRIBE",
                                        "params": [stream],
                                        "id": 3
                                    }
                                    await best_connection.send_json(subscribe_msg)
                                    logger.info(
                                        f"Binance {market}: новый символ {symbol} добавлен, "
                                        f"подписываемся в {best_conn_id}"
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"Binance {market} [{best_conn_id}]: "
                                        f"ошибка при подписке на {stream}: {e}"
                                    )
                                    # Удаляем stream из списка при ошибке (создаем новый список)
                                    if _symbol_update_lock:
                                        async with _symbol_update_lock:
                                            updated_streams = [s for s in new_streams if s != stream]
                                            _active_connections[best_conn_id] = (best_connection, updated_streams, market)
                            else:
                                # Для spot нужно переподключиться
                                logger.info(
                                    f"Binance {market}: новый символ {symbol} добавлен, "
                                    f"требуется переподключение {best_conn_id}"
                                )
                        else:
                            logger.debug(
                                f"Binance {market} [{best_conn_id}]: "
                                f"соединение закрыто, пропускаем подписку на {stream}"
                            )
                    else:
                        # Все соединения заполнены или нет соединений - создаем новое
                        logger.info(
                            f"Binance {market}: новый символ {symbol} добавлен, "
                            f"создаем новое соединение"
                        )
                        # Создаем новое соединение для нового символа
                        # Собираем все новые символы, которые не поместились
                        # Создаем копию словаря для безопасной итерации
                        existing_streams = set()
                        for _, streams_list, m in list(_active_connections.values()):
                            if m == market:
                                existing_streams.update(streams_list)
                        new_symbols_to_add = [s for s in added_symbols if _symbol_to_stream(s, market) not in existing_streams]
                        
                        if new_symbols_to_add:
                            # Создаем streams для новых символов
                            new_streams = [_symbol_to_stream(s, market) for s in new_symbols_to_add]
                            new_streams = _validate_streams(new_streams, market)
                            
                            if new_streams:
                                # Разбиваем на чанки
                                new_chunks = _chunk_list(new_streams, STREAMS_PER_CONNECTION)
                                
                                # Создаем новые соединения
                                for i, chunk in enumerate(new_chunks):
                                    if market == "spot":
                                        connection_id = f"SPOT-WS-{len(_spot_tasks) + i + 1}"
                                        url = f"{SPOT_WS_ENDPOINT}?streams={'/'.join(chunk)}"
                                        task = asyncio.create_task(_ws_connection_worker(
                                            streams=chunk,
                                            market="spot",
                                            url=url,
                                            on_candle=on_candle,
                                            on_error=on_error,
                                            connection_id=connection_id,
                                        ))
                                        _tasks.append(task)
                                        _spot_tasks.append(task)
                                    else:  # linear
                                        connection_id = f"LINEAR-WS-{len(_linear_tasks) + i + 1}"
                                        task = asyncio.create_task(_ws_connection_worker_subscribe(
                                            streams=chunk,
                                            market="linear",
                                            on_candle=on_candle,
                                            on_error=on_error,
                                            connection_id=connection_id,
                                        ))
                                        _tasks.append(task)
                                        _linear_tasks.append(task)
                                    
                                    logger.info(
                                        f"Binance {market}: создано новое соединение {connection_id} "
                                        f"для {len(chunk)} символов"
                                    )
        
        except Exception as e:
            logger.error(f"Ошибка при обновлении символов Binance {market}: {e}", exc_info=True)
        
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
    
    # Инициализируем lock если еще не инициализирован
    global _symbol_update_lock, _stats_lock
    if _symbol_update_lock is None:
        _symbol_update_lock = asyncio.Lock()
    if _stats_lock is None:
        _stats_lock = asyncio.Lock()
    
    # Инициализируем глобальные списки символов
    async with _symbol_update_lock:
        _active_spot_symbols[:] = spot_symbols
        _active_linear_symbols[:] = linear_symbols
    
    _tasks = []
    _spot_tasks = []
    _linear_tasks = []
    
    # Запускаем SPOT
    if fetch_spot and spot_symbols:
        if _stats_lock:
            async with _stats_lock:
                _stats["spot"]["active_symbols"] = len(spot_symbols)
        
        # Строим streams для SPOT: "btcusdt@kline_1s"
        spot_streams = [f"{sym.lower()}@kline_1s" for sym in spot_symbols]
        # Валидируем стримы перед подпиской
        spot_streams = _validate_streams(spot_streams, "spot")
        spot_chunks = _chunk_list(spot_streams, STREAMS_PER_CONNECTION)
        
        logger.info(f"Binance spot: запущено {len(spot_chunks)} соединений для {len(spot_streams)} валидных стримов (из {len(spot_symbols)} символов)")
        
        for i, chunk in enumerate(spot_chunks):
            connection_id = f"SPOT-WS-{i+1}"
            url = f"{SPOT_WS_ENDPOINT}?streams={'/'.join(chunk)}"
            task = asyncio.create_task(_ws_connection_worker(
                streams=chunk,
                market="spot",
                url=url,
                on_candle=on_candle,
                on_error=on_error,
                connection_id=connection_id,
            ))
            _tasks.append(task)
            _spot_tasks.append(task)
    
    # Запускаем LINEAR
    if fetch_linear and linear_symbols:
        if _stats_lock:
            async with _stats_lock:
                _stats["linear"]["active_symbols"] = len(linear_symbols)
        
        # Строим streams для LINEAR: "btcusdt_perpetual@continuousKline_1s" (как в официальной документации Binance для continuous kline)
        linear_streams = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in linear_symbols]
        # Валидируем стримы перед подпиской
        linear_streams = _validate_streams(linear_streams, "linear")
        linear_chunks = _chunk_list(linear_streams, STREAMS_PER_CONNECTION)
        
        logger.info(f"Binance linear: запущено {len(linear_chunks)} соединений для {len(linear_streams)} валидных стримов (из {len(linear_symbols)} символов)")
        
        for i, chunk in enumerate(linear_chunks):
            connection_id = f"LINEAR-WS-{i+1}"
            task = asyncio.create_task(_ws_connection_worker_subscribe(
                streams=chunk,
                market="linear",
                on_candle=on_candle,
                on_error=on_error,
                connection_id=connection_id,
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
        if _stats_lock:
            async with _stats_lock:
                _stats["linear"]["active_symbols"] = 0
                _stats["linear"]["active_connections"] = 0
                _stats["linear"]["reconnects"] = 0
    
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
    
    if _stats_lock:
        async with _stats_lock:
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
    async def _update_stats():
        if _stats_lock:
            async with _stats_lock:
                _stats["spot"]["active_connections"] = len([t for t in _spot_tasks if not t.done()])
                _stats["linear"]["active_connections"] = len([t for t in _linear_tasks if not t.done()])
                return _stats.copy()
        else:
            _stats["spot"]["active_connections"] = len([t for t in _spot_tasks if not t.done()])
            _stats["linear"]["active_connections"] = len([t for t in _linear_tasks if not t.done()])
            return _stats.copy()
    
    # Пытаемся выполнить обновление с использованием lock
    try:
        # Пытаемся получить текущий event loop
        try:
            loop = asyncio.get_running_loop()
            # Если loop запущен, создаем задачу в новом потоке
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _update_stats())
                return future.result(timeout=1.0)
        except RuntimeError:
            # Если loop не запущен, используем asyncio.run
            return asyncio.run(_update_stats())
    except Exception:
        # Fallback: обновляем без lock если что-то пошло не так
        _stats["spot"]["active_connections"] = len([t for t in _spot_tasks if not t.done()])
        _stats["linear"]["active_connections"] = len([t for t in _linear_tasks if not t.done()])
        return _stats.copy()

