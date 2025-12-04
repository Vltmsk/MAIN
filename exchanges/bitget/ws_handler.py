"""
WebSocket обработчик для Bitget
Краткая упрощённая версия для демонстрации стандарта
"""
import ssl
import certifi
import asyncio
import math
import random
from typing import Awaitable, Callable, List, Dict, Set
import aiohttp
import json
import socket
from config import AppConfig
from core.candle_builder import Candle, CandleBuilder
from core.logger import get_logger
from core.symbol_cache_logger import report_symbol_cache_update
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
FUT_BATCH_SIZE = 49  # Количество пар на одно соединение

# Глобальные переменные
_builder: CandleBuilder | None = None
_tasks: List[asyncio.Task] = []
# Символы хранятся в памяти в переменных spot_symbols, linear_symbols и symbols
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

# Глобальные переменные для хранения актуальных списков символов
_active_spot_symbols: List[str] = []
_active_linear_symbols: List[str] = []
_symbol_update_lock: asyncio.Lock | None = None
# Словарь для отслеживания соединений: connection_id -> (ws, symbols_list, market)
_active_connections: Dict[str, tuple] = {}


def _safe_float(x) -> float:
    """
    Безопасное преобразование в float.
    
    Args:
        x: Значение для преобразования
    
    Returns:
        float: Преобразованное значение или math.nan при ошибке
    
    Примечание:
        В отличие от других файлов (например, gate/ws_handler.py), при ошибке возвращается
        math.nan, а не 0.0. Это важно для корректной обработки некорректных данных.
    """
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
    
    Args:
        batch_id: Уникальный идентификатор батча
        symbols: Список символов для подписки в этом батче (может обновляться)
        market: Тип рынка ("spot" или "linear")
        on_candle: Callback для обработки завершённых свечей
        on_error: Callback для обработки ошибок
    
    Примечание:
        Функция отслеживает первое сообщение для каждого символа (first_message_for_symbol)
        и игнорирует его, так как оно может содержать устаревшие данные.
        При реконнекте словарь first_message_for_symbol очищается.
        Перед переподключением список символов обновляется с биржи.
    """
    reconnect_attempt = 0
    first_message_for_symbol = {}  # Отслеживаем первое сообщение для каждого символа
    was_connected = False  # Флаг успешного подключения
    
    while True:
        reconnect_attempt += 1
        was_reconnecting = False
        
        try:
            # Переподключение считается, если:
            # 1. Это не первая попытка (reconnect_attempt > 1), ИЛИ
            # 2. Это первая попытка, но соединение было установлено ранее (was_connected = True)
            is_reconnect = reconnect_attempt > 1 or was_connected
            
            if is_reconnect:
                # Обновляем список символов перед переподключением
                if _symbol_update_lock:
                    try:
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
                                    f"Bitget {market} batch-{batch_id}: "
                                    f"при переподключении удалено {removed_count} неактуальных символов"
                                )
                            symbols[:] = valid_symbols
                    except Exception as e:
                        logger.warning(f"Bitget {market} batch-{batch_id}: ошибка при обновлении символов перед реконнектом: {e}")
                
                was_reconnecting = True
                # Увеличиваем счётчик реконнектов при любом реконнекте (включая аномальные закрытия)
                # Безопасная инициализация и проверка типов
                try:
                    if market not in _stats:
                        logger.error(f"Bitget: неизвестный market '{market}', инициализируем статистику")
                        _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                    
                    # Безопасная проверка и инициализация reconnects
                    if not isinstance(_stats[market], dict):
                        logger.error(f"Bitget {market}: '_stats[{market}]' имеет неверный тип, переинициализируем")
                        _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                    
                    if "reconnects" not in _stats[market] or not isinstance(_stats[market]["reconnects"], int):
                        logger.warning(f"Bitget {market}: 'reconnects' имеет неверный тип или отсутствует, сбрасываем")
                        _stats[market]["reconnects"] = 0
                    
                    _stats[market]["reconnects"] += 1
                    logger.info(f"Bitget {market} batch-{batch_id}: переподключение (счётчик: {_stats[market]['reconnects']})")
                except Exception as e:
                    logger.error(f"Bitget {market} batch-{batch_id}: ошибка при обновлении счётчика реконнектов: {e}", exc_info=True)
                    # Принудительно инициализируем статистику при ошибке и увеличиваем счётчик
                    try:
                        if market not in _stats or not isinstance(_stats[market], dict):
                            _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                        # Увеличиваем счётчик даже при ошибке, чтобы не потерять информацию о переподключении
                        if "reconnects" not in _stats[market] or not isinstance(_stats[market]["reconnects"], int):
                            _stats[market]["reconnects"] = 0
                        _stats[market]["reconnects"] += 1
                        logger.info(f"Bitget {market} batch-{batch_id}: переподключение (счётчик после ошибки: {_stats[market]['reconnects']})")
                    except Exception as e2:
                        logger.error(f"Bitget {market} batch-{batch_id}: критическая ошибка при инициализации статистики: {e2}", exc_info=True)
                
                # Очищаем словарь при реконнекте, чтобы получить первое сообщение для каждого символа
                # Это необходимо, так как биржа отправляет исторические данные при реконнекте
                first_message_for_symbol.clear()
                
                delay = min(2 ** min(reconnect_attempt - 1, 5), 60)
                
                # Определяем причину переподключения
                reconnect_reason = "normal"
                
                # Вызываем on_error с обработкой ошибок, чтобы не прервать переподключение
                try:
                    await on_error({
                        "exchange": "bitget",
                        "market": market,
                        "connection_id": f"batch-{batch_id}",
                        "type": "reconnect",
                        "reason": reconnect_reason,
                    })
                except Exception as e:
                    logger.error(f"Bitget {market} batch-{batch_id}: ошибка в on_error при реконнекте: {e}")
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
                
                # Регистрируем соединение для динамических обновлений
                connection_id = f"batch-{batch_id}"
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        _active_connections[connection_id] = (ws, symbols, market)
                
                # Безопасная инициализация и проверка типов
                try:
                    if market not in _stats:
                        logger.error(f"Bitget: неизвестный market '{market}', инициализируем статистику")
                        _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                    
                    # Безопасная проверка и инициализация active_connections
                    if not isinstance(_stats[market], dict):
                        logger.error(f"Bitget {market}: '_stats[{market}]' имеет неверный тип, переинициализируем")
                        _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                    
                    if "active_connections" not in _stats[market] or not isinstance(_stats[market]["active_connections"], int):
                        logger.warning(f"Bitget {market}: 'active_connections' имеет неверный тип или отсутствует, сбрасываем")
                        _stats[market]["active_connections"] = 0
                    
                    _stats[market]["active_connections"] += 1
                except Exception as e:
                    logger.error(f"Bitget {market} batch-{batch_id}: ошибка при обновлении счётчика активных соединений: {e}", exc_info=True)
                    # Принудительно инициализируем статистику при ошибке
                    try:
                        _stats[market] = {"active_connections": 1, "active_symbols": 0, "reconnects": 0}
                    except Exception:
                        pass
                
                # Задержка перед подпиской после подключения
                subscribe_delay = SUBSCRIBE_DELAY_PER_WS_SEC + random.uniform(0, SUBSCRIBE_DELAY_JITTER_SEC)
                await asyncio.sleep(subscribe_delay)
                
                # Подписываемся по чанкам
                inst_type = "SPOT" if market == "spot" else "USDT-FUTURES"
                
                # Словарь для отслеживания подтверждений подписки
                subscription_confirmations = {}
                
                # Список символов, которые нужно удалить из списка из-за ошибок подписки
                symbols_to_remove = set()
                
                # Разбиваем символы на чанки для подписки
                # Создаем snapshot списка для защиты от изменения во время итерации
                symbols_snapshot = list(symbols)
                for chunk_start in range(0, len(symbols_snapshot), SUBSCRIBE_CHUNK_SIZE):
                    chunk = symbols_snapshot[chunk_start:chunk_start + SUBSCRIBE_CHUNK_SIZE]
                    args = [{"instType": inst_type, "channel": "trade", "instId": s} for s in chunk]
                    subscribe_msg = {"op": "subscribe", "args": args}
                    await ws.send_json(subscribe_msg)
                    
                    # Сохраняем информацию о подписке для проверки подтверждения
                    for symbol in chunk:
                        subscription_confirmations[symbol] = False
                    
                    # Пауза между чанками (кроме последнего)
                    if chunk_start + SUBSCRIBE_CHUNK_SIZE < len(symbols_snapshot):
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
                            # В aiohttp код закрытия может быть доступен через ws.close_code
                            # Также проверяем другие возможные источники
                            close_code = None
                            close_reason = None
                            
                            # Пытаемся получить код закрытия из WebSocket объекта
                            try:
                                if hasattr(ws, 'close_code'):
                                    close_code = ws.close_code
                            except Exception:
                                pass
                            
                            # Если не получили код из ws, пробуем получить из сообщения
                            if close_code is None:
                                try:
                                    # В некоторых версиях aiohttp код может быть в msg.data
                                    if hasattr(msg, 'data') and isinstance(msg.data, (int, str)):
                                        try:
                                            close_code = int(msg.data)
                                        except (ValueError, TypeError):
                                            pass
                                except Exception:
                                    pass
                            
                            # Пытаемся получить причину закрытия из исключения, если оно есть
                            try:
                                if hasattr(msg, 'exception') and msg.exception:
                                    close_reason = str(msg.exception)
                                # Также проверяем, есть ли причина в extra
                                if hasattr(msg, 'extra') and isinstance(msg.extra, dict):
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
                            
                            close_code_msg = close_code_messages.get(close_code, f"Неизвестный код: {close_code}")
                            
                            error_info = {
                                "exchange": "bitget",
                                "market": market,
                                "connection_id": f"batch-{batch_id}",
                                "type": "websocket_closed",
                                "close_code": close_code,
                                "close_code_message": close_code_msg,
                                "close_reason": close_reason,
                            }
                            
                            logger.warning(
                                f"Bitget {market} batch-{batch_id}: WebSocket закрыт (CLOSED), "
                                f"код: {close_code} ({close_code_msg})"
                                + (f", причина: {close_reason}" if close_reason else "")
                            )
                            
                            # Вызываем on_error с обработкой ошибок, чтобы не прервать переподключение
                            try:
                                await on_error(error_info)
                            except Exception as e:
                                logger.error(f"Bitget {market} batch-{batch_id}: ошибка в on_error при закрытии WebSocket: {e}")
                            
                            # Переподключение будет подсчитано в начале следующей итерации цикла
                            # чтобы избежать двойного подсчета (здесь и при reconnect_attempt > 1)
                            break
                        
                        if msg.type == aiohttp.WSMsgType.ERROR:
                            error_data = getattr(msg, 'data', None)
                            error_exception = None
                            
                            # Пытаемся получить исключение из сообщения
                            try:
                                if hasattr(msg, 'exception') and msg.exception:
                                    error_exception = str(msg.exception)
                            except Exception:
                                pass
                            
                            error_info = {
                                "exchange": "bitget",
                                "market": market,
                                "connection_id": f"batch-{batch_id}",
                                "type": "websocket_error",
                                "error_data": str(error_data) if error_data else None,
                                "error_exception": error_exception,
                            }
                            
                            logger.error(
                                f"Bitget {market} batch-{batch_id}: WebSocket ошибка (ERROR), "
                                f"данные: {error_data}"
                                + (f", исключение: {error_exception}" if error_exception else "")
                            )
                            
                            # Вызываем on_error с обработкой ошибок, чтобы не прервать переподключение
                            try:
                                await on_error(error_info)
                            except Exception as e:
                                logger.error(f"Bitget {market} batch-{batch_id}: ошибка в on_error при WebSocket ошибке: {e}")
                            
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
                            
                            # Обрабатываем общие ошибки из JSON сообщений
                            # Bitget может отправлять ошибки в формате: {"code": <код>, "msg": "<сообщение>", ...}
                            # Исключаем ошибки подписки, так как они обрабатываются отдельно ниже
                            if isinstance(data, dict):
                                # Пропускаем обработку, если это сообщение о подписке (обрабатывается отдельно)
                                if data.get("event") == "subscribe" or data.get("op") == "subscribe":
                                    pass  # Будет обработано ниже
                                else:
                                    error_code = data.get("code")
                                    error_msg = data.get("msg")
                                    
                                    # Проверяем, является ли это сообщением об ошибке
                                    # Коды ошибок Bitget: 400, 401, 403, 404, 429, 500 и другие
                                    # Успешные операции обычно имеют code = "0" или 0, или отсутствует code
                                    is_error = (
                                        error_code is not None and 
                                        error_code != "0" and 
                                        error_code != 0 and
                                        error_msg is not None
                                    )
                                    
                                    if is_error:
                                        # Маппинг HTTP кодов ошибок Bitget на понятные сообщения
                                        error_code_messages = {
                                            400: "Неверный формат запроса (Bad Request)",
                                            401: "Неверный API ключ (Unauthorized)",
                                            403: "Нет доступа к запрашиваемому ресурсу (Forbidden)",
                                            404: "Запрос не найден (Not Found)",
                                            429: "Слишком много запросов, превышен лимит (Too Many Requests)",
                                            500: "Внутренняя ошибка сервера (Internal Server Error)",
                                        }
                                        
                                        error_code_msg = error_code_messages.get(
                                            error_code if isinstance(error_code, int) else None,
                                            f"Код ошибки: {error_code}"
                                        )
                                        
                                        # Определяем тип ошибки для более детальной обработки
                                        error_type = "server_error"
                                        if error_code == 429:
                                            error_type = "rate_limit"
                                        elif error_code in [401, 403]:
                                            error_type = "authentication_error"
                                        elif error_code == 400:
                                            error_type = "bad_request"
                                        
                                        error_info = {
                                            "exchange": "bitget",
                                            "market": market,
                                            "connection_id": f"batch-{batch_id}",
                                            "type": error_type,
                                            "error_code": error_code,
                                            "error_code_message": error_code_msg,
                                            "error_msg": error_msg,
                                            "full_response": json.dumps(data, ensure_ascii=False),
                                        }
                                        
                                        logger.error(
                                            f"Bitget {market} batch-{batch_id}: "
                                            f"ошибка от сервера: {error_code_msg} (code: {error_code}), "
                                            f"msg: {error_msg}"
                                        )
                                        
                                        # Вызываем on_error с обработкой ошибок, чтобы не прервать переподключение
                                        try:
                                            await on_error(error_info)
                                        except Exception as e:
                                            logger.error(f"Bitget {market} batch-{batch_id}: ошибка в on_error при ошибке сервера: {e}")
                                        
                                        # Для ошибок rate limit (429) делаем паузу перед переподключением
                                        if error_code == 429:
                                            logger.warning(
                                                f"Bitget {market} batch-{batch_id}: "
                                                f"превышен лимит запросов, ожидание 60 секунд перед переподключением..."
                                            )
                                            await asyncio.sleep(60)
                                            break
                                        
                                        # Для критических ошибок (401, 403) также делаем переподключение
                                        if error_code in [401, 403]:
                                            logger.warning(
                                                f"Bitget {market} batch-{batch_id}: "
                                                f"ошибка аутентификации/доступа, переподключение..."
                                            )
                                            break
                                        
                                        # Для других ошибок продолжаем работу, но логируем
                                        continue
                            
                            # Проверяем подтверждение подписки (обрабатываем только если это сообщение о подписке)
                            if isinstance(data, dict) and (data.get("event") == "subscribe" or data.get("op") == "subscribe"):
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
                                    
                                    # Маппинг специфичных кодов ошибок Bitget для подписки
                                    subscription_error_messages = {
                                        30001: "Символ не существует",
                                        30002: "Неверный формат запроса",
                                        30003: "Неверный тип инструмента",
                                        30004: "Неверный канал",
                                        30005: "Превышен лимит подписок",
                                        400: "Неверный формат запроса (Bad Request)",
                                        401: "Неверный API ключ (Unauthorized)",
                                        403: "Нет доступа к запрашиваемому ресурсу (Forbidden)",
                                        404: "Запрос не найден (Not Found)",
                                        429: "Слишком много запросов, превышен лимит (Too Many Requests)",
                                        500: "Внутренняя ошибка сервера (Internal Server Error)",
                                    }
                                    
                                    error_code_msg = subscription_error_messages.get(
                                        error_code if isinstance(error_code, int) else None,
                                        f"Код ошибки: {error_code}"
                                    )
                                    
                                    # Получаем информацию о символе для более детального логирования
                                    args_list = data.get("arg", [])
                                    symbol_info = "unknown"
                                    failed_symbols = []
                                    
                                    if isinstance(args_list, list) and args_list:
                                        failed_symbols = [arg.get("instId") for arg in args_list if isinstance(arg, dict) and arg.get("instId")]
                                        symbol_info = ", ".join(failed_symbols)
                                    elif isinstance(args_list, dict):
                                        inst_id = args_list.get("instId")
                                        if inst_id:
                                            failed_symbols = [inst_id]
                                            symbol_info = inst_id
                                    
                                    logger.warning(
                                        f"Bitget {market} batch-{batch_id}: "
                                        f"ошибка подписки на {symbol_info}: {error_code_msg} (code: {error_code}), "
                                        f"msg: {error_msg}"
                                    )
                                    
                                    # Отправляем информацию об ошибке через callback
                                    # Вызываем on_error с обработкой ошибок, чтобы не прервать переподключение
                                    try:
                                        await on_error({
                                            "exchange": "bitget",
                                            "market": market,
                                            "connection_id": f"batch-{batch_id}",
                                            "type": "subscription_error",
                                            "error_code": error_code,
                                            "error_code_message": error_code_msg,
                                            "error_msg": error_msg,
                                            "failed_symbols": failed_symbols,
                                            "full_response": json.dumps(data, ensure_ascii=False),
                                        })
                                    except Exception as e:
                                        logger.error(f"Bitget {market} batch-{batch_id}: ошибка в on_error при ошибке подписки: {e}")
                                    
                                    # Если ошибка 30001 (символ не существует) или другие коды, указывающие на несуществующий символ
                                    if (error_code == 30001 or 
                                        error_code == 404 or
                                        (isinstance(error_msg, str) and any(phrase in error_msg.lower() for phrase in ["doesn't exist", "not exist", "not found", "invalid symbol"]))):
                                        for symbol in failed_symbols:
                                            if symbol:
                                                symbols_to_remove.add(symbol)
                                                logger.info(
                                                    f"Bitget {market} batch-{batch_id}: "
                                                    f"символ {symbol} будет удален из списка подписки (не существует на бирже)"
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
                            
                            # Удаляем символы, которые не существуют на бирже
                            if symbols_to_remove:
                                removed = [s for s in symbols if s in symbols_to_remove]
                                symbols[:] = [s for s in symbols if s not in symbols_to_remove]
                                if removed:
                                    logger.warning(
                                        f"Bitget {market} batch-{batch_id}: "
                                        f"удалены символы из списка подписки: {', '.join(removed)}"
                                    )
                                    symbols_to_remove.clear()
                                    
                                    # Если все символы были удалены, прекращаем работу
                                    if not symbols:
                                        logger.warning(
                                            f"Bitget {market} batch-{batch_id}: "
                                            f"все символы были удалены, прекращаем работу батча"
                                        )
                                        break
                
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                
                # Удаляем соединение из регистрации
                if _symbol_update_lock:
                    async with _symbol_update_lock:
                        _active_connections.pop(connection_id, None)
                
                # Безопасная инициализация и проверка типов
                try:
                    if market not in _stats:
                        logger.error(f"Bitget: неизвестный market '{market}', инициализируем статистику")
                        _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                    
                    # Безопасная проверка и инициализация active_connections
                    if not isinstance(_stats[market], dict):
                        logger.error(f"Bitget {market}: '_stats[{market}]' имеет неверный тип, переинициализируем")
                        _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                    
                    if "active_connections" not in _stats[market] or not isinstance(_stats[market]["active_connections"], int):
                        logger.warning(f"Bitget {market}: 'active_connections' имеет неверный тип или отсутствует, сбрасываем")
                        _stats[market]["active_connections"] = 0
                    
                    _stats[market]["active_connections"] = max(0, _stats[market]["active_connections"] - 1)
                except Exception as e:
                    logger.error(f"Bitget {market} batch-{batch_id}: ошибка при обновлении счётчика активных соединений при отключении: {e}", exc_info=True)
                    # Принудительно инициализируем статистику при ошибке
                    try:
                        _stats[market] = {"active_connections": 0, "active_symbols": 0, "reconnects": 0}
                    except Exception:
                        pass
                # Сбрасываем флаг подключения при выходе из контекста WebSocket
                was_connected = False
                
                # Если список символов пуст, прекращаем работу
                if not symbols:
                    break
                
        except asyncio.CancelledError:
            break
        except (ConnectionResetError, ConnectionError) as e:
            # Обработка ConnectionResetError (WinError 10054) - соединение принудительно закрыто удаленным хостом
            error_msg = f"Соединение принудительно закрыто удаленным хостом: {e}"
            logger.warning(f"Bitget {market} batch-{batch_id}: {error_msg}")
            try:
                await on_error({
                    "exchange": "bitget",
                    "market": market,
                    "connection_id": f"batch-{batch_id}",
                    "error": error_msg,
                    "error_type": "connection_reset",
                })
            except Exception as callback_error:
                logger.error(f"Bitget {market} batch-{batch_id}: ошибка в on_error при ConnectionResetError: {callback_error}")
            # При ошибке соединения просто переходим к следующей итерации (реконнект)
            # Цикл while True на строке 119 продолжит работу и выполнит переподключение
        except Exception as e:
            # Если это была попытка реконнекта, ошибка уже залогирована через on_error выше
            # Не логируем повторно, просто переходим к следующей итерации
            if not was_reconnecting:
                # Если это первая попытка или другая ошибка, логируем
                logger.error(f"Ошибка в WS соединении Bitget {batch_id}: {e}", exc_info=True)
                try:
                    await on_error({
                        "exchange": "bitget",
                        "market": market,
                        "batch_id": batch_id,
                        "error": str(e),
                    })
                except Exception as callback_error:
                    logger.error(f"Bitget {market} batch-{batch_id}: ошибка в on_error: {callback_error}")
            # При ошибке соединения просто переходим к следующей итерации (реконнект)
            # Цикл while True на строке 119 продолжит работу и выполнит переподключение


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
                    exchange="Bitget",
                    market=market,
                    has_changes=has_changes,
                    removed_count=len(removed_symbols),
                    added_count=len(added_symbols),
                    total_symbols=len(new_symbols)
                )
                
                inst_type = "SPOT" if market == "spot" else "USDT-FUTURES"
                
                # Обрабатываем удаленные символы
                for symbol in removed_symbols:
                    # Находим все соединения, содержащие этот символ
                    connections_to_update = []
                    for conn_id, (ws, symbols_list, conn_market) in _active_connections.items():
                        if conn_market == market and symbol in symbols_list:
                            connections_to_update.append((conn_id, ws, symbols_list))
                    
                    # Удаляем символ из всех соединений
                    for conn_id, ws, symbols_list in connections_to_update:
                        if symbol in symbols_list:
                            symbols_list.remove(symbol)
                            logger.info(
                                f"Bitget {market}: символ {symbol} удален с биржи, "
                                f"удален из {conn_id}"
                            )
                            
                            # НЕ пытаемся отписаться, т.к. символ уже не существует на бирже
                            # Биржа вернет ошибку 30001, если попытаться отписаться от несуществующего символа
                            # Символ просто удаляется из списка, и соединение продолжает работать
                
                # Обрабатываем новые символы
                for symbol in added_symbols:
                    # Находим соединение с наименьшим количеством символов (но меньше лимита)
                    best_connection = None
                    best_conn_id = None
                    best_symbols = None
                    min_count = BATCH_SIZE if market == "spot" else FUT_BATCH_SIZE
                    
                    for conn_id, (ws, symbols_list, conn_market) in _active_connections.items():
                        if conn_market == market:
                            limit = BATCH_SIZE if market == "spot" else FUT_BATCH_SIZE
                            if len(symbols_list) < limit:
                                if len(symbols_list) < min_count:
                                    min_count = len(symbols_list)
                                    best_connection = ws
                                    best_conn_id = conn_id
                                    best_symbols = symbols_list
                    
                    if best_connection and not best_connection.closed:
                        # Добавляем символ в существующее соединение
                        best_symbols.append(symbol)
                        
                        # Отправляем subscribe
                        try:
                            subscribe_msg = {
                                "op": "subscribe",
                                "args": [{"instType": inst_type, "channel": "trade", "instId": symbol}]
                            }
                            await best_connection.send_json(subscribe_msg)
                            logger.info(
                                f"Bitget {market}: новый символ {symbol} добавлен, "
                                f"подписываемся в {best_conn_id}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Bitget {market} [{best_conn_id}]: "
                                f"ошибка при подписке на {symbol}: {e}"
                            )
                            # Удаляем символ из списка при ошибке
                            if symbol in best_symbols:
                                best_symbols.remove(symbol)
                    else:
                        # Все соединения заполнены или нет соединений - создаем новое
                        logger.info(
                            f"Bitget {market}: новый символ {symbol} добавлен, "
                            f"создаем новое соединение"
                        )
                        # Собираем все новые символы, которые не поместились
                        new_symbols_to_add = [s for s in added_symbols if s not in [
                            sym for _, symbols_list, m in _active_connections.values() 
                            if m == market for sym in symbols_list
                        ]]
                        
                        if new_symbols_to_add:
                            # Разбиваем на батчи
                            batch_size = BATCH_SIZE if market == "spot" else FUT_BATCH_SIZE
                            for i in range(0, len(new_symbols_to_add), batch_size):
                                symbols_batch = new_symbols_to_add[i:i+batch_size]
                                symbols_batch = list(symbols_batch)
                                
                                # Создаем новое соединение
                                batch_id = len(_tasks) + 1
                                task = asyncio.create_task(_ws_batch_worker(
                                    batch_id=batch_id,
                                    symbols=symbols_batch,
                                    market=market,
                                    on_candle=on_candle,
                                    on_error=on_error,
                                ))
                                _tasks.append(task)
                                if market == "spot":
                                    _spot_tasks.append(task)
                                else:
                                    _linear_tasks.append(task)
                                
                                logger.info(
                                    f"Bitget {market}: создано новое соединение batch-{batch_id} "
                                    f"для {len(symbols_batch)} символов"
                                )
        
        except Exception as e:
            logger.error(f"Ошибка при обновлении символов Bitget {market}: {e}", exc_info=True)
        
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
    
    # Инициализируем lock если еще не инициализирован
    global _symbol_update_lock
    if _symbol_update_lock is None:
        _symbol_update_lock = asyncio.Lock()
    
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
    
    # Инициализируем глобальные списки символов
    async with _symbol_update_lock:
        _active_spot_symbols[:] = spot_symbols
        _active_linear_symbols[:] = linear_symbols
    
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
            
            # Создаем изменяемый список для батча (чтобы можно было обновлять при реконнекте)
            symbols_batch = list(symbols_batch)
            
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
            
            # Создаем изменяемый список для батча (чтобы можно было обновлять при реконнекте)
            symbols_batch = list(symbols_batch)
            
            # Запускаем подключение (семафор ограничит параллельность)
            await _create_connection_task(batch_id, symbols_batch, "linear")
            batch_id += 1
            
            # Задержка между подключениями (кроме последнего)
            if i + FUT_BATCH_SIZE < len(linear_symbols):
                stagger_delay = WS_STAGGER_SEC + random.uniform(0, WS_STAGGER_JITTER_SEC)
                await asyncio.sleep(stagger_delay)
    
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

