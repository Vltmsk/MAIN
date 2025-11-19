"""
Главный модуль для управления всеми биржами
"""
import asyncio
import importlib
import json
import time
import aiosqlite
import aiohttp
from typing import Dict, List, Callable, Awaitable, Optional
from core.candle_builder import CandleBuilder, Candle
from core.logger import setup_root_logger, get_logger
from core.metrics import Metrics
from core.spike_detector import spike_detector
from core.telegram_notifier import telegram_notifier
from core.health_monitor import health_monitor
from BD.database import db
from config import config


def format_candle_count(count: int) -> str:
    """
    Форматирует количество свечей с сокращениями.
    
    Args:
        count: Количество свечей
        
    Returns:
        Отформатированная строка с сокращениями (8,5к, 58,9к, 158к, 1,23 млн, 13,8 млрд)
    """
    if count < 1000:
        return str(count)
    elif count < 1_000_000:
        # Тысячи
        value = count / 1000
        return f"{value:.1f}к".replace('.0к', 'к')
    elif count < 1_000_000_000:
        # Миллионы
        value = count / 1_000_000
        return f"{value:.2f} млн".replace('.00 млн', ' млн')
    else:
        # Миллиарды
        value = count / 1_000_000_000
        return f"{value:.1f} млрд".replace('.0 млрд', ' млрд')

logger = get_logger(__name__)
metrics = Metrics()

# Словарь адаптеров для всех бирж
ADAPTERS: Dict[str, str] = {
    "gate": "exchanges.gate.ws_handler",
    "binance": "exchanges.binance.ws_handler",
    "bitget": "exchanges.bitget.ws_handler",
    "bybit": "exchanges.bybit.ws_handler",
    "hyperliquid": "exchanges.hyperliquid.ws_handler",
}


class ExchangeManager:
    """Класс для управления состоянием бирж и задач"""
    
    def __init__(self):
        """Инициализация менеджера"""
        self._all_tasks: List[asyncio.Task] = []
        self._reconnect_logged: Dict[str, float] = {}  # Для отслеживания дубликатов реконнектов: {key: timestamp}
        self._exchange_start_times: Dict[str, float] = {}  # Время старта биржи: {exchange: timestamp}
    
    def add_tasks(self, tasks: List[asyncio.Task]) -> None:
        """Добавляет задачи в список"""
        self._all_tasks.extend(tasks)
    
    def add_task(self, task: asyncio.Task) -> None:
        """Добавляет одну задачу в список"""
        self._all_tasks.append(task)
    
    def get_all_tasks(self) -> List[asyncio.Task]:
        """Возвращает все задачи"""
        return self._all_tasks
    
    def get_tasks_count(self) -> int:
        """Возвращает количество задач"""
        return len(self._all_tasks)
    
    def set_exchange_start_time(self, exchange_name: str, start_time: float) -> None:
        """Устанавливает время старта биржи"""
        self._exchange_start_times[exchange_name] = start_time
    
    def get_exchange_start_time(self, exchange_name: str, default: float) -> float:
        """Получает время старта биржи"""
        return self._exchange_start_times.get(exchange_name, default)
    
    def log_reconnect(self, reconnect_key: str, timestamp: float) -> None:
        """Логирует реконнект с временной меткой"""
        self._reconnect_logged[reconnect_key] = timestamp
    
    def get_last_reconnect_time(self, reconnect_key: str) -> float:
        """Получает время последнего реконнекта"""
        return self._reconnect_logged.get(reconnect_key, 0)
    
    def cleanup_old_reconnects(self, current_time: float, max_age: float = 10.0) -> None:
        """Очищает старые записи о реконнектах"""
        if len(self._reconnect_logged) > 100:
            self._reconnect_logged = {
                key: ts for key, ts in self._reconnect_logged.items()
                if current_time - ts < max_age
            }
    
    def clear_state(self) -> None:
        """Очищает все состояние (для перезапуска)"""
        self._all_tasks.clear()
        self._reconnect_logged.clear()
        self._exchange_start_times.clear()


# Глобальный экземпляр менеджера бирж
exchange_manager = ExchangeManager()


async def _send_chart_async(
    candle: Candle,
    delta: float,
    volume_usdt: float,
    wick_pct: float,
    token: str,
    chat_id: str,
    user_name: str
) -> None:
    """
    Асинхронно отправляет график прострела пользователю
    
    Args:
        candle: Свеча с детектом
        delta: Дельта в процентах
        volume_usdt: Объём в USDT
        wick_pct: Процент тени
        token: Telegram Bot Token
        chat_id: Telegram Chat ID
        user_name: Имя пользователя (для логирования)
    """
    try:
        logger.debug(
            f"Начало отправки графика для {user_name} "
            f"({candle.exchange} {candle.market} {candle.symbol})"
        )
        from core.chart_generator import chart_generator
        
        # Генерируем график
        logger.debug(f"Генерация графика для {user_name} ({candle.exchange} {candle.symbol})...")
        chart_bytes = await chart_generator.generate_chart(
            candle=candle,
            delta=delta,
            volume_usdt=volume_usdt,
            wick_pct=wick_pct
        )
        
        if chart_bytes:
            logger.debug(
                f"График сгенерирован для {user_name} "
                f"({candle.exchange} {candle.symbol}), размер: {len(chart_bytes)} байт"
            )
            # Отправляем график
            logger.debug(f"Отправка графика в Telegram для {user_name}...")
            success, error_msg = await telegram_notifier.send_photo(
                token=token,
                chat_id=chat_id,
                photo_bytes=chart_bytes
            )
            
            if success:
                logger.info(f"График успешно отправлен пользователю {user_name} ({candle.exchange} {candle.symbol})")
            else:
                logger.warning(
                    f"Не удалось отправить график пользователю {user_name}: {error_msg}",
                    extra={
                        "log_to_db": False,  # Не критично, не логируем в БД
                        "error_type": "chart_send_error",
                        "exchange": candle.exchange,
                        "market": candle.market,
                        "symbol": candle.symbol,
                    },
                )
        else:
            logger.warning(
                f"Не удалось сгенерировать график для пользователя {user_name} "
                f"({candle.exchange} {candle.market} {candle.symbol})"
            )
    except Exception as e:
        logger.warning(
            f"Ошибка при отправке графика пользователю {user_name}: {e}",
            exc_info=True,
            extra={
                "log_to_db": False,  # Не критично, не логируем в БД
                "error_type": "chart_send_exception",
                "exchange": candle.exchange,
                "market": candle.market,
                "symbol": candle.symbol,
            },
        )


async def on_candle(candle: Candle) -> None:
    """
    Обработчик завершённых свечей.
    
    Args:
        candle: Завершённая свеча
    """
    # Для Bitget начинаем считать свечи только через 15 секунд после старта
    if candle.exchange == "bitget":
        current_time = time.time()
        start_time = exchange_manager.get_exchange_start_time(candle.exchange, current_time)
        
        # Если прошло менее 15 секунд, не считаем свечу
        if current_time - start_time < 15.0:
            return
    
    metrics.inc_candle(candle.exchange, candle.market)
    # Не логируем каждую свечу - только статистика
    
    # Детект стрел для всех пользователей
    try:
        detected_spikes = spike_detector.detect_spike(candle)
        
        if detected_spikes:
            logger.debug(f"Обнаружена стрела: {candle.exchange} {candle.market} {candle.symbol} - {len(detected_spikes)} пользователей")
            
            # Для каждого пользователя сохраняем стрелу и отправляем уведомление
            for spike_info in detected_spikes:
                user_id = spike_info["user_id"]
                user_name = spike_info["user_name"]
                delta = spike_info["delta"]
                wick_pct = spike_info["wick_pct"]
                volume_usdt = spike_info["volume_usdt"]
                
                # Получаем информацию о пользователе для отправки уведомления
                user_data = await db.get_user_by_id(user_id)
                if not user_data:
                    logger.warning(f"Пользователь с ID {user_id} не найден")
                    continue
                
                # Сохраняем стрелу в БД
                try:
                    alert_id = await db.add_alert(
                        ts=candle.ts_ms,
                        exchange=candle.exchange,
                        market=candle.market,
                        symbol=candle.symbol,
                        delta=delta,
                        wick_pct=wick_pct,
                        volume_usdt=volume_usdt,
                        meta=None,
                        user_id=user_id
                    )
                    logger.debug(f"Стрела сохранена в БД (ID: {alert_id}) для пользователя {user_name}")
                except aiosqlite.IntegrityError as e:
                    logger.warning(f"Стрела уже существует в БД для пользователя {user_name}: {e}")
                except aiosqlite.OperationalError as e:
                    logger.error(f"Ошибка БД при сохранении стрелы для пользователя {user_name}: {e}", exc_info=True, extra={
                        "log_to_db": True,
                        "error_type": "db_operational_error",
                        "exchange": candle.exchange,
                        "market": candle.market,
                        "symbol": candle.symbol,
                    })
                except Exception as e:
                    logger.error(f"Неожиданная ошибка при сохранении стрелы в БД для пользователя {user_name}: {e}", exc_info=True, extra={
                        "log_to_db": True,
                        "error_type": "db_error",
                        "exchange": candle.exchange,
                        "market": candle.market,
                        "symbol": candle.symbol,
                    })
                
                # Отправляем уведомление в Telegram, если настроено
                tg_token = user_data.get("tg_token", "")
                chat_id = user_data.get("chat_id", "")
                
                # Получаем пользовательский шаблон сообщения, условные шаблоны и timezone из настроек
                message_template = None
                conditional_templates = None
                user_timezone = "UTC"  # По умолчанию UTC
                should_send_chart = False  # По умолчанию графики отключены
                try:
                    options_json = user_data.get("options_json", "{}")
                    if options_json:
                        options = json.loads(options_json)
                        message_template = options.get("messageTemplate")
                        conditional_templates = options.get("conditionalTemplates")
                        user_timezone = options.get("timezone", "UTC")  # Получаем timezone пользователя
                        
                        # Проверяем настройку отправки графиков
                        # Сначала проверяем индивидуальные настройки пары
                        from core.symbol_utils import get_quote_currency
                        quote_currency = await get_quote_currency(candle.symbol, candle.exchange, candle.market)
                        exchange_key = candle.exchange.lower()
                        # Преобразуем market в формат настроек: "linear" -> "futures", "spot" -> "spot"
                        # Это работает для всех бирж: Binance, Bybit, Bitget, Gate, Hyperliquid
                        # Все они используют "linear" для фьючерсов в candle.market
                        market_key = "futures" if candle.market == "linear" else "spot"
                        
                        logger.debug(
                            f"Проверка отправки графика для {user_name}: "
                            f"exchange={candle.exchange}, market={candle.market}, symbol={candle.symbol}, "
                            f"exchange_key={exchange_key}, market_key={market_key}, quote_currency={quote_currency}"
                        )
                        
                        pair_settings = options.get("pairSettings", {})
                        if quote_currency:
                            pair_key = f"{exchange_key}_{market_key}_{quote_currency}"
                            logger.debug(f"Проверка индивидуальных настроек пары: pair_key={pair_key}, exists={pair_key in pair_settings}")
                            if pair_key in pair_settings:
                                pair_config = pair_settings[pair_key]
                                should_send_chart = pair_config.get("sendChart", False)
                                logger.debug(f"Найдены индивидуальные настройки пары: sendChart={should_send_chart}")
                        
                        # Если не найдено в индивидуальных настройках, проверяем глобальные настройки биржи/рынка
                        if not should_send_chart:
                            exchange_settings = options.get("exchangeSettings", {})
                            logger.debug(f"Проверка глобальных настроек: exchange_key={exchange_key}, exists={exchange_key in exchange_settings}")
                            if exchange_key in exchange_settings:
                                exchange_config = exchange_settings[exchange_key]
                                logger.debug(f"Настройки биржи {exchange_key}: {list(exchange_config.keys())}")
                                market_config = exchange_config.get(market_key, {})
                                logger.debug(f"Настройки рынка {market_key}: {market_config}")
                                should_send_chart = market_config.get("sendChart", False)
                                logger.debug(f"Глобальные настройки: sendChart={should_send_chart}")
                        
                        logger.info(
                            f"Результат проверки отправки графика для {user_name} "
                            f"({candle.exchange} {candle.market} {candle.symbol}): should_send_chart={should_send_chart}"
                        )
                except json.JSONDecodeError as e:
                    logger.debug(f"Ошибка парсинга JSON для пользователя {user_name}: {e}")
                except (ValueError, TypeError) as e:
                    logger.debug(f"Ошибка обработки настроек для пользователя {user_name}: {e}")
                
                if tg_token and chat_id:
                    try:
                        # Передаем user_id для проверки условий серий и timezone для форматирования времени
                        success, error_msg = await telegram_notifier.notify_spike(
                            candle=candle,
                            token=tg_token,
                            chat_id=chat_id,
                            delta=delta,
                            wick_pct=wick_pct,
                            volume_usdt=volume_usdt,
                            template=message_template,
                            conditional_templates=conditional_templates,
                            user_id=user_id,
                            timezone=user_timezone
                        )
                        if success:
                            logger.info(f"Уведомление отправлено пользователю {user_name} ({candle.exchange} {candle.symbol})")
                        else:
                            logger.error(
                                f"Не удалось отправить уведомление пользователю {user_name}: {error_msg}",
                                extra={
                                    "log_to_db": True,
                                    "error_type": "telegram_error",
                                    "exchange": candle.exchange,
                                    "market": candle.market,
                                    "symbol": candle.symbol,
                                },
                            )
                        
                        # Асинхронно отправляем график, если включено
                        if should_send_chart and success:
                            logger.info(
                                f"Запуск отправки графика для {user_name} "
                                f"({candle.exchange} {candle.market} {candle.symbol})"
                            )
                            # Запускаем отправку графика в фоне (не блокируем основной поток)
                            asyncio.create_task(_send_chart_async(
                                candle=candle,
                                delta=delta,
                                volume_usdt=volume_usdt,
                                wick_pct=wick_pct,
                                token=tg_token,
                                chat_id=chat_id,
                                user_name=user_name
                            ))
                        elif should_send_chart and not success:
                            logger.warning(
                                f"График не отправлен для {user_name} "
                                f"({candle.exchange} {candle.market} {candle.symbol}): "
                                f"уведомление не было отправлено успешно (success={success})"
                            )
                        elif not should_send_chart:
                            logger.debug(
                                f"График не отправлен для {user_name} "
                                f"({candle.exchange} {candle.market} {candle.symbol}): "
                                f"отправка графиков отключена (should_send_chart=False)"
                            )
                    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                        # Эти ошибки уже обработаны в telegram_notifier, но логируем для полноты
                        logger.error(
                            f"Ошибка сети/таймаут при отправке уведомления пользователю {user_name}: {e}",
                            exc_info=True,
                            extra={
                                "log_to_db": True,
                                "error_type": "telegram_network_error",
                                "exchange": candle.exchange,
                                "market": candle.market,
                                "symbol": candle.symbol,
                            },
                        )
                    except Exception as e:
                        logger.error(
                            f"Неожиданная ошибка при отправке уведомления пользователю {user_name}: {e}",
                            exc_info=True,
                            extra={
                                "log_to_db": True,
                                "error_type": "telegram_error",
                                "exchange": candle.exchange,
                                "market": candle.market,
                                "symbol": candle.symbol,
                            },
                        )
                else:
                    logger.debug(f"Пользователь {user_name} не настроил Telegram (нет token или chat_id)")
    
    except Exception as e:
        logger.error(f"Ошибка при детекте стрел: {e}", exc_info=True, extra={
            "log_to_db": True,
            "error_type": "spike_detection_error",
            "exchange": candle.exchange if 'candle' in locals() else "unknown",
            "market": candle.market if 'candle' in locals() else "unknown",
            "symbol": candle.symbol if 'candle' in locals() else "unknown",
        })


async def on_error(error: dict) -> None:
    """
    Обработчик ошибок.
    
    Args:
        error: Информация об ошибке
    """
    exchange = error.get("exchange", "unknown")
    
    # Если это реконнект, логируем уведомление (без дубликатов)
    if error.get("type") == "reconnect":
        market = error.get("market", "")
        connection_id = error.get("connection_id", "")
        reconnect_key = f"{exchange}:{market}:{connection_id}"
        
        # Проверяем, не логировали ли мы этот реконнект недавно
        current_time = time.time()
        
        # Логируем только если этот реконнект не был залогирован в последние 0.5 секунды
        last_logged = exchange_manager.get_last_reconnect_time(reconnect_key)
        if current_time - last_logged >= 0.5:
            logger.info(
                f"РЕКОННЕКТ: {exchange.upper()} {market} {connection_id}",
                extra={
                    "log_to_db": True,
                    "error_type": "reconnect",
                    "exchange": exchange,
                    "market": market,
                    "connection_id": connection_id,
                },
            )
            exchange_manager.log_reconnect(reconnect_key, current_time)
            
            # Периодически очищаем старые записи (старше 10 секунд), только после добавления
            exchange_manager.cleanup_old_reconnects(current_time, max_age=10.0)
    else:
        metrics.inc_error(exchange)
        error_message = error.get("error") or error.get("message") or str(error)
        logger.error(
            f"Ошибка от {exchange}: {error_message}",
            extra={
                "log_to_db": True,
                "error_type": error.get("type") or "exchange_error",
                "exchange": exchange,
                "market": error.get("market"),
                "connection_id": error.get("connection_id"),
                "symbol": error.get("symbol"),
                "stack_trace": error.get("stack_trace"),
            },
        )


async def start_exchange(exchange_name: str) -> None:
    """
    Запуск одной биржи.
    
    Args:
        exchange_name: Название биржи (например, "gate")
    """
    try:
        # Проверяем, какие рынки включены для этой биржи
        enabled_markets = []
        exchange_config_map = {
            "gate": ("gate_spot", "gate_linear"),
            "binance": ("binance_spot", "binance_linear"),
            "bitget": ("bitget_spot", "bitget_linear"),
            "bybit": ("bybit_spot", "bybit_linear"),
            "hyperliquid": ("hyperliquid_spot", "hyperliquid_linear"),
        }
        
        spot_key, linear_key = exchange_config_map.get(exchange_name, (None, None))
        if spot_key and getattr(config.exchanges, spot_key, False):
            enabled_markets.append("spot")
        if linear_key and getattr(config.exchanges, linear_key, False):
            enabled_markets.append("linear")
        
        if not enabled_markets:
            logger.info(f"Биржа {exchange_name}: все рынки отключены, пропускаем")
            return
        
        logger.info(f"Запуск биржи: {exchange_name} (рынки: {', '.join(enabled_markets)})")
        
        # Запоминаем время старта биржи
        exchange_manager.set_exchange_start_time(exchange_name, time.time())
        
        # Получаем модуль адаптера
        adapter_path = ADAPTERS[exchange_name]
        adapter_module = importlib.import_module(adapter_path)
        
        # Callback для подсчёта трейдов
        async def on_trade_callback(exchange: str, market: str):
            """Callback для подсчёта трейдов (ticks) при получении каждой сделки"""
            metrics.inc_trade(exchange, market)
        
        # Вызываем функцию start()
        tasks = await adapter_module.start(
            on_candle=on_candle,
            on_error=on_error,
            config=config,
            on_trade=on_trade_callback,  # Передаём callback для подсчёта трейдов
        )
        
        # Сохраняем задачи
        exchange_manager.add_tasks(tasks)
        logger.info(f"Биржа {exchange_name} запущена: {len(tasks)} задач создано")
        
    except ImportError as e:
        logger.error(f"Не удалось импортировать модуль {exchange_name}: {e}", extra={
            "log_to_db": True,
            "error_type": "exchange_import_error",
            "exchange": exchange_name,
        })
    except AttributeError as e:
        logger.error(f"Модуль {exchange_name} не содержит функцию start(): {e}", extra={
            "log_to_db": True,
            "error_type": "exchange_attribute_error",
            "exchange": exchange_name,
        })
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запуске {exchange_name}: {e}", exc_info=True, extra={
            "log_to_db": True,
            "error_type": "exchange_start_error",
            "exchange": exchange_name,
        })


async def stop_all_exchanges() -> None:
    """Остановка всех бирж."""
    logger.info("Остановка всех бирж...")
    
    # Останавливаем все задачи
    all_tasks = exchange_manager.get_all_tasks()
    for task in all_tasks:
        task.cancel()
    
    if all_tasks:
        try:
            await asyncio.wait_for(
                asyncio.gather(*all_tasks, return_exceptions=True),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("Таймаут при ожидании остановки задач")
    
    # Вызываем stop() для каждой биржи и закрываем сессии
    for exchange_name in ADAPTERS.keys():
        try:
            adapter_path = ADAPTERS[exchange_name]
            adapter_module = importlib.import_module(adapter_path)
            if hasattr(adapter_module, 'stop'):
                # Получаем задачи для остановки
                if hasattr(adapter_module, '_tasks'):
                    tasks_to_stop = adapter_module._tasks
                    try:
                        await asyncio.wait_for(
                            adapter_module.stop(tasks_to_stop),
                            timeout=10.0  # Увеличиваем таймаут для корректного закрытия
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Таймаут при остановке {exchange_name}")
                    except Exception as e:
                        logger.error(f"Ошибка при stop() {exchange_name}: {e}")
        except Exception as e:
            logger.error(f"Ошибка при остановке {exchange_name}: {e}")
    
    logger.info("Все биржи остановлены")


def _format_market_stats(exchange_name: str, market: str, active_symbols: int, 
                         active_connections: int, reconnects: int, candles_count: int) -> str:
    """Форматирует строку статистики для одного рынка."""
    return (f"{exchange_name} {market} - {active_symbols} пар   "
            f"собрано свечей - {format_candle_count(candles_count)}  "
            f"сколько WS используется - {active_connections}  "
            f"реконнекты WS - {reconnects}")


def _print_exchange_statistics():
    """Вспомогательная функция для вывода статистики всех бирж."""
    logger.info("stats: tick")
    
    metrics_stats = metrics.get_stats()
    
    # Получаем статистику по всем биржам
    for exchange_name in ADAPTERS.keys():
        try:
            adapter_path = ADAPTERS[exchange_name]
            adapter_module = importlib.import_module(adapter_path)
            
            # Получаем данные по свечам один раз
            exchange_candles = metrics_stats.get("by_exchange", {}).get(exchange_name, {})
            
            if hasattr(adapter_module, 'get_statistics'):
                exchange_stats = adapter_module.get_statistics()
                
                # Статистика по рынкам
                for market in ["spot", "linear"]:
                    market_candles = exchange_candles.get(market, {})
                    candles_count = market_candles.get("candles", 0)
                    
                    if market in exchange_stats:
                        market_stats = exchange_stats[market]
                        active_symbols = market_stats.get("active_symbols", 0)
                        active_connections = market_stats.get("active_connections", 0)
                        reconnects = market_stats.get("reconnects", 0)
                        
                        logger.info(_format_market_stats(
                            exchange_name, market, active_symbols, 
                            active_connections, reconnects, candles_count
                        ))
                    else:
                        # Если market отсутствует в статистике, выводим нулевые значения
                        logger.info(_format_market_stats(
                            exchange_name, market, 0, 0, 0, candles_count
                        ))
            else:
                # Если модуль не имеет get_statistics, все равно выводим статистику с нулевыми значениями
                for market in ["spot", "linear"]:
                    market_candles = exchange_candles.get(market, {})
                    candles_count = market_candles.get("candles", 0)
                    
                    logger.info(_format_market_stats(
                        exchange_name, market, 0, 0, 0, candles_count
                    ))
        except Exception as e:
            # Даже при ошибке выводим статистику с нулевыми значениями
            logger.warning(f"Ошибка получения статистики для {exchange_name}: {e}")
            
            exchange_candles = metrics_stats.get("by_exchange", {}).get(exchange_name, {})
            for market in ["spot", "linear"]:
                market_candles = exchange_candles.get(market, {})
                candles_count = market_candles.get("candles", 0)
                
                logger.info(_format_market_stats(
                    exchange_name, market, 0, 0, 0, candles_count
                ))


def _calculate_batches_per_ws(exchange_name: str, market: str, active_symbols: int, ws_connections: int) -> Optional[int]:
    """
    Рассчитывает количество батчей внутри одного WebSocket для биржи и рынка.
    
    Args:
        exchange_name: Название биржи
        market: Тип рынка (spot/linear)
        active_symbols: Количество активных символов
        ws_connections: Количество WebSocket-подключений
        
    Returns:
        Количество батчей на одно соединение или None, если батчи не используются
    """
    if ws_connections == 0:
        return None
    
    # Для Bybit: есть батчи внутри соединений
    if exchange_name == "bybit":
        if market == "spot":
            # SPOT: max 86 символов на соединение, 10 символов на батч
            symbols_per_connection = 86
            batch_size = 10
        else:  # linear
            # LINEAR: max 100 символов на соединение, обычно 1 батч на соединение
            symbols_per_connection = 100
            batch_size = 100
        
        # Рассчитываем среднее количество батчей на соединение
        if active_symbols > 0:
            avg_symbols_per_conn = active_symbols / ws_connections
            batches_per_conn = max(1, int((avg_symbols_per_conn + batch_size - 1) // batch_size))
            return batches_per_conn
        return None
    
    # Для Bitget: каждый worker - это отдельное соединение, батчей нет в нашем понимании
    # Для Gate и Binance: батчей нет
    return None


async def _save_statistics_to_db():
    """
    Собирает статистику со всех бирж и сохраняет в БД.
    """
    try:
        metrics_stats = metrics.get_stats()
        
        # Получаем статистику по всем биржам
        for exchange_name in ADAPTERS.keys():
            try:
                adapter_path = ADAPTERS[exchange_name]
                adapter_module = importlib.import_module(adapter_path)
                
                # Получаем данные по свечам
                exchange_candles = metrics_stats.get("by_exchange", {}).get(exchange_name, {})
                
                exchange_stats = {}
                if hasattr(adapter_module, 'get_statistics'):
                    exchange_stats = adapter_module.get_statistics()
                
                # Статистика по рынкам
                for market in ["spot", "linear"]:
                    market_candles = exchange_candles.get(market, {})
                    candles_count = market_candles.get("candles", 0)
                    last_candle_time = market_candles.get("last_candle_time")
                    
                    # Конвертируем ISO timestamp в формат SQLite TIMESTAMP, если есть
                    if last_candle_time:
                        # ISO формат уже подходит для SQLite TIMESTAMP
                        # Но убедимся, что это строка в правильном формате
                        pass  # ISO формат уже корректный
                    
                    market_stats = exchange_stats.get(market, {})
                    active_symbols = market_stats.get("active_symbols", 0)
                    active_connections = market_stats.get("active_connections", 0)
                    reconnects = market_stats.get("reconnects", 0)
                    
                    # Рассчитываем батчи
                    batches_per_ws = _calculate_batches_per_ws(
                        exchange_name, market, active_symbols, active_connections
                    )
                    
                    # Получаем T/s
                    # Для Binance используем свечи в секунду, для остальных - трейды в секунду
                    if exchange_name == "binance":
                        ticks_per_second = metrics.get_candles_per_second(exchange_name, market)
                    else:
                        ticks_per_second = metrics.get_ticks_per_second(exchange_name, market)
                    
                    # Сохраняем в БД
                    await db.upsert_exchange_statistics(
                        exchange=exchange_name,
                        market=market,
                        symbols_count=active_symbols,
                        ws_connections=active_connections,
                        batches_per_ws=batches_per_ws,
                        reconnects=reconnects,
                        candles_count=candles_count,
                        last_candle_time=last_candle_time,
                        ticks_per_second=ticks_per_second,
                    )
                    
            except Exception as e:
                logger.error(f"Ошибка при сохранении статистики для {exchange_name}: {e}", exc_info=True)
                # Продолжаем обработку других бирж
                continue
                
    except Exception as e:
        logger.error(f"Ошибка при сборе статистики: {e}", exc_info=True)


async def print_statistics():
    """Вывод статистики работы каждые 30 секунд, независимо от состояния бирж."""
    try:
        # Первый вывод статистики через 5 секунд после запуска
        await asyncio.sleep(5)
        _print_exchange_statistics()
        
        # Затем каждые 30 секунд - выводим статистику всегда
        while True:
            await asyncio.sleep(30)
            _print_exchange_statistics()
    except asyncio.CancelledError:
        logger.debug("Задача статистики отменена")
        raise
    except Exception as e:
        logger.error(f"Ошибка в задаче статистики: {e}", exc_info=True)
        # Даже при ошибке продолжаем выводить статистику
        while True:
            try:
                await asyncio.sleep(30)
                _print_exchange_statistics()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.error(f"Ошибка в задаче статистики: {err}", exc_info=True)


async def update_statistics_to_db():
    """Периодическое обновление статистики в БД каждые 15 секунд."""
    try:
        # Первое сохранение через 5 секунд после запуска
        await asyncio.sleep(5)
        await _save_statistics_to_db()
        
        # Затем каждые 15 секунд
        while True:
            await asyncio.sleep(15)
            await _save_statistics_to_db()
    except asyncio.CancelledError:
        logger.debug("Задача обновления статистики в БД отменена")
        raise
    except Exception as e:
        logger.error(f"Ошибка в задаче обновления статистики в БД: {e}", exc_info=True)
        # Даже при ошибке продолжаем обновлять статистику
        while True:
            try:
                await asyncio.sleep(15)
                await _save_statistics_to_db()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.error(f"Ошибка в задаче обновления статистики в БД: {err}", exc_info=True)


async def main():
    """Главная функция."""
    # Настройка логирования с ротацией
    setup_root_logger(config.log_level, enable_file_logging=True)
    
    logger.info("=" * 60)
    logger.info("START: Запуск сборщика данных со всех бирж")
    logger.info("=" * 60)
    
    # Инициализируем БД нормализации символов
    try:
        from BD.symbol_normalization_db import symbol_normalization_db
        await symbol_normalization_db.initialize()
        logger.info("БД нормализации символов инициализирована")
        
        # Проверяем, нужно ли заполнить БД (если она пустая)
        all_symbols = await symbol_normalization_db.get_all_symbols()
        if not all_symbols:
            logger.info("БД нормализации пуста, начинаем заполнение...")
            from core.symbol_utils import populate_normalization_db
            await populate_normalization_db()
        else:
            logger.info(f"БД нормализации содержит {len(all_symbols)} символов")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД нормализации: {e}", exc_info=True)
        # Продолжаем работу даже если БД нормализации не инициализирована
    
    # Запускаем мониторинг здоровья системы
    await health_monitor.start_monitoring()
    
    # _builder больше не используется глобально - каждый ws_handler создаёт свой
    # Но callback передаётся через параметр start()
    
    # Запускаем включённые биржи (хотя бы один рынок должен быть включен)
    enabled_exchanges = []
    if config.exchanges.gate_spot or config.exchanges.gate_linear:
        enabled_exchanges.append("gate")
    if config.exchanges.binance_spot or config.exchanges.binance_linear:
        enabled_exchanges.append("binance")
    if config.exchanges.bitget_spot or config.exchanges.bitget_linear:
        enabled_exchanges.append("bitget")
    if config.exchanges.bybit_spot or config.exchanges.bybit_linear:
        enabled_exchanges.append("bybit")
    if config.exchanges.hyperliquid_spot or config.exchanges.hyperliquid_linear:
        enabled_exchanges.append("hyperliquid")
    
    # Запускаем биржи параллельно
    logger.info(f"Запускаем {len(enabled_exchanges)} бирж: {', '.join(enabled_exchanges)}")
    results = await asyncio.gather(
        *[start_exchange(exchange_name) for exchange_name in enabled_exchanges],
        return_exceptions=True  # Продолжаем запуск других бирж даже если одна упала
    )
    
    # Проверяем результаты запуска и логируем ошибки
    for exchange_name, result in zip(enabled_exchanges, results):
        if isinstance(result, Exception):
            logger.error(f"Ошибка при запуске биржи {exchange_name}: {result}", exc_info=result)
    
    logger.info(f"Всего создано задач: {exchange_manager.get_tasks_count()}")
    
    # Запускаем вывод статистики
    logger.info("Запуск задачи вывода статистики...")
    stats_task = asyncio.create_task(print_statistics())
    exchange_manager.add_task(stats_task)
    logger.info("Задача статистики запущена. Первый вывод через 5 секунд.")
    
    # Запускаем обновление статистики в БД
    logger.info("Запуск задачи обновления статистики в БД...")
    db_stats_task = asyncio.create_task(update_statistics_to_db())
    exchange_manager.add_task(db_stats_task)
    logger.info("Задача обновления статистики в БД запущена. Первое обновление через 5 секунд, затем каждые 15 секунд.")
    
    # Ожидание
    try:
        while True:
            await asyncio.sleep(3600)  # Проверка каждый час
    except KeyboardInterrupt:
        logger.info("\nПолучен сигнал остановки...")
    except asyncio.CancelledError:
        logger.info("\nSTOP: Остановка программы...")
    finally:
        # Останавливаем мониторинг здоровья
        await health_monitor.stop_monitoring()
        await stop_all_exchanges()
        logger.info("Программа остановлена.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Обрабатывается в main()
    except Exception as e:
        print(f"\n\nКритическая ошибка: {e}")
        import traceback
        traceback.print_exc()

