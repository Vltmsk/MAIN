"""
Модуль для генерации тиковых графиков прострелов
"""
import asyncio
import aiohttp
import time
import ssl
import certifi
import sys
import os
from typing import Optional, List, Dict, Tuple, Any
from io import BytesIO
import matplotlib
matplotlib.use('Agg')  # Используем backend без GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from core.candle_builder import Candle
from core.logger import get_logger
from core.symbol_utils import get_symbol_with_pair

logger = get_logger(__name__)

# Кэш для графиков: {cache_key: (image_bytes, timestamp)}
_chart_cache: Dict[str, Tuple[bytes, float]] = {}
CACHE_TTL = 600  # 10 минут


def _create_ssl_connector() -> aiohttp.TCPConnector:
    """
    Создаёт SSL‑коннектор с использованием корневых сертификатов certifi.
    Используется для всех REST‑запросов к биржам, чтобы избежать проблем с локальными сертификатами.
    """
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return aiohttp.TCPConnector(ssl=ssl_context)


def _log_ssl_error(exchange: str, url: str, error: Exception) -> None:
    """
    Расширенное логирование SSL‑ошибок для диагностики проблем окружения.
    """
    logger.error(
        f"SSL ошибка при запросе истории сделок: {exchange} {url}: {error}",
        exc_info=True,
        extra={
            "log_to_db": True,
            "error_type": "ssl_error",
            "exchange": exchange,
            "market": None,
            "symbol": None,
            "env_python_version": sys.version,
            "env_certifi_path": certifi.where(),
            "env_aiohttp_version": getattr(aiohttp, "__version__", "unknown"),
            "env_https_proxy": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
            "env_http_proxy": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        },
    )


class ChartGenerator:
    """Класс для генерации тиковых графиков прострелов"""
    
    @staticmethod
    def _get_cache_key(exchange: str, market: str, symbol: str, detection_timestamp: int) -> str:
        """
        Генерирует ключ кэша для графика
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            symbol: Символ торговой пары
            detection_timestamp: Временная метка детекта в миллисекундах
            
        Returns:
            Ключ кэша
        """
        # Используем точное время детекта для кэш-ключа
        # График показывает 60 минут до детекта включительно, поэтому для каждого уникального момента детекта
        # нужен свой график, чтобы показывать актуальные данные включая саму стрелу
        # Кэш все равно эффективен, так как один и тот же детект (одна свеча) обычно отправляется
        # нескольким пользователям одновременно, и они получат один и тот же график
        return f"{exchange}_{market}_{symbol}_{detection_timestamp}"
    
    @staticmethod
    def _get_cached_chart(cache_key: str) -> Optional[bytes]:
        """
        Получает график из кэша, если он актуален
        
        Args:
            cache_key: Ключ кэша
            
        Returns:
            Байты изображения или None если нет в кэше или устарел
        """
        if cache_key in _chart_cache:
            image_bytes, cache_timestamp = _chart_cache[cache_key]
            current_time = time.time()
            
            # Проверяем, не устарел ли кэш
            if current_time - cache_timestamp < CACHE_TTL:
                logger.debug(f"График найден в кэше: {cache_key}")
                return image_bytes
            else:
                # Удаляем устаревший кэш
                del _chart_cache[cache_key]
                logger.debug(f"Кэш устарел, удаляем: {cache_key}")
        
        return None
    
    @staticmethod
    def _save_to_cache(cache_key: str, image_bytes: bytes) -> None:
        """
        Сохраняет график в кэш
        
        Args:
            cache_key: Ключ кэша
            image_bytes: Байты изображения
        """
        _chart_cache[cache_key] = (image_bytes, time.time())
        logger.debug(f"График сохранен в кэш: {cache_key}")
    
    @staticmethod
    async def _fetch_trades_binance(symbol: str, market: str, start_time: int, end_time: int) -> List[Dict]:
        """
        Получает историю сделок с Binance через REST API
        
        Args:
            symbol: Символ торговой пары (например, BTCUSDT)
            market: Тип рынка (spot/linear)
            start_time: Начальное время в миллисекундах
            end_time: Конечное время в миллисекундах
            
        Returns:
            Список сделок (максимум 1000 сделок)
        
        Примечание:
            Функция использует endpoint aggTrades (агрегированные сделки) вместо обычных trades,
            так как он позволяет запрашивать данные за определённый период времени.
            Данные преобразуются из формата aggTrades в стандартный формат сделок.
        """
        try:
            # Для Binance нужно использовать разные endpoints для spot и futures
            if market == "spot":
                url = "https://api.binance.com/api/v3/trades"
            else:  # linear/futures
                url = "https://fapi.binance.com/fapi/v1/trades"
            
            # Binance возвращает последние 1000 сделок, но мы можем запросить по времени
            # Используем агрегированные сделки (aggTrades) для получения данных за период
            if market == "spot":
                url = "https://api.binance.com/api/v3/aggTrades"
            else:
                url = "https://fapi.binance.com/fapi/v1/aggTrades"
            
            params = {
                "symbol": symbol,
                "startTime": start_time,
                "endTime": end_time,
                "limit": 1000
            }
            
            connector = _create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Преобразуем aggTrades в формат сделок
                        trades = []
                        for trade in data:
                            # aggTrades содержит: a (agg trade id), p (price), q (quantity), f (first trade id), l (last trade id), T (timestamp), m (is buyer maker)
                            price = float(trade.get("p", 0))
                            quantity = float(trade.get("q", 0))
                            timestamp = trade.get("T", 0)
                            is_buyer_maker = trade.get("m", False)
                            
                            trades.append({
                                "price": price,
                                "quantity": quantity,
                                "timestamp": timestamp,
                                "is_buyer": not is_buyer_maker  # Если maker - продавец, то taker - покупатель
                            })
                        return trades
                    else:
                        logger.warning(f"Ошибка получения сделок Binance: HTTP {response.status}")
                        return []
        except ssl.SSLError as e:
            _log_ssl_error("binance", url, e)
            return []
        except Exception as e:
            logger.warning(f"Ошибка получения сделок Binance: {e}")
            return []
    
    @staticmethod
    async def _fetch_trades_bybit(symbol: str, market: str, start_time: int, end_time: int) -> List[Dict]:
        """
        Получает историю сделок с Bybit через REST API
        
        Args:
            symbol: Символ торговой пары
            market: Тип рынка (spot/linear)
            start_time: Начальное время в миллисекундах
            end_time: Конечное время в миллисекундах
            
        Returns:
            Список сделок
        
        Примечание:
            Для spot и linear используется один и тот же URL "https://api.bybit.com/v5/market/recent-trade",
            различие только в параметре "category" (spot или linear).
            Символ может быть автоматически преобразован: если он не заканчивается на USDT или USDC,
            к нему добавляется USDT.
        """
        try:
            # Bybit V5 API
            if market == "spot":
                url = "https://api.bybit.com/v5/market/recent-trade"
            else:  # linear
                url = "https://api.bybit.com/v5/market/recent-trade"
            
            # Преобразуем символ для Bybit (нужно добавить USDT если его нет)
            bybit_symbol = symbol
            if not symbol.endswith("USDT") and not symbol.endswith("USDC"):
                bybit_symbol = f"{symbol}USDT"
            
            params = {
                "category": "spot" if market == "spot" else "linear",
                "symbol": bybit_symbol,
                "limit": 1000
            }
            
            connector = _create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get("result", {})
                        trades_list = result.get("list", [])
                        
                        trades = []
                        for trade in trades_list:
                            price = float(trade.get("price", 0))
                            quantity = float(trade.get("size", 0))
                            timestamp = int(trade.get("time", 0))
                            side = trade.get("side", "").lower()
                            
                            # Фильтруем по времени
                            if timestamp < start_time or timestamp > end_time:
                                continue
                            
                            trades.append({
                                "price": price,
                                "quantity": quantity,
                                "timestamp": timestamp,
                                "is_buyer": side == "buy"
                            })
                        return trades
                    else:
                        logger.warning(f"Ошибка получения сделок Bybit: HTTP {response.status}")
                        return []
        except ssl.SSLError as e:
            _log_ssl_error("bybit", url, e)
            return []
        except Exception as e:
            logger.warning(f"Ошибка получения сделок Bybit: {e}")
            return []
    
    @staticmethod
    async def _fetch_trades_gate(symbol: str, market: str, start_time: int, end_time: int) -> List[Dict]:
        """
        Получает историю сделок с Gate.io через REST API
        
        Args:
            symbol: Символ торговой пары
            market: Тип рынка (spot/linear)
            start_time: Начальное время в миллисекундах
            end_time: Конечное время в миллисекундах
            
        Returns:
            Список сделок
        """
        try:
            # Gate.io API
            if market == "spot":
                url = "https://api.gateio.ws/api/v4/spot/trades"
            else:  # linear
                url = "https://api.gateio.ws/api/v4/futures/usdt/trades"
            
            # Преобразуем символ для Gate.io (формат: BTC_USDT)
            gate_symbol = symbol.replace("USDT", "_USDT").replace("USDC", "_USDC")
            
            params = {
                "currency_pair": gate_symbol,
                "limit": 1000
            }
            
            connector = _create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        trades = []
                        for trade in data:
                            price = float(trade.get("price", 0))
                            amount = float(trade.get("amount", 0))
                            timestamp = int(trade.get("create_time", 0)) * 1000  # Gate.io возвращает секунды
                            side = trade.get("side", "").lower()
                            
                            # Фильтруем по времени
                            if timestamp < start_time or timestamp > end_time:
                                continue
                            
                            trades.append({
                                "price": price,
                                "quantity": amount,
                                "timestamp": timestamp,
                                "is_buyer": side == "buy"
                            })
                        return trades
                    else:
                        logger.warning(f"Ошибка получения сделок Gate.io: HTTP {response.status}")
                        return []
        except ssl.SSLError as e:
            _log_ssl_error("gate", url, e)
            return []
        except Exception as e:
            logger.warning(f"Ошибка получения сделок Gate.io: {e}")
            return []
    
    @staticmethod
    async def _fetch_trades_bitget(symbol: str, market: str, start_time: int, end_time: int) -> List[Dict]:
        """
        Получает историю сделок с Bitget через REST API
        
        Args:
            symbol: Символ торговой пары
            market: Тип рынка (spot/linear)
            start_time: Начальное время в миллисекундах
            end_time: Конечное время в миллисекундах
            
        Returns:
            Список сделок
        """
        try:
            # Bitget API
            if market == "spot":
                url = "https://api.bitget.com/api/spot/v1/market/fills"
            else:  # linear
                url = "https://api.bitget.com/api/mix/v1/market/fills"
            
            # Преобразуем символ для Bitget
            bitget_symbol = symbol
            
            params = {
                "symbol": bitget_symbol,
                "limit": 1000
            }
            
            if market != "spot":
                params["productType"] = "umcbl"  # USDT-M perpetual
            
            connector = _create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get("data", [])
                        
                        trades = []
                        for trade in result:
                            price = float(trade.get("price", 0))
                            size = float(trade.get("size", 0))
                            timestamp = int(trade.get("ts", 0))
                            side = trade.get("side", "").lower()
                            
                            # Фильтруем по времени
                            if timestamp < start_time or timestamp > end_time:
                                continue
                            
                            trades.append({
                                "price": price,
                                "quantity": size,
                                "timestamp": timestamp,
                                "is_buyer": side == "buy"
                            })
                        return trades
                    else:
                        logger.warning(f"Ошибка получения сделок Bitget: HTTP {response.status}")
                        return []
        except ssl.SSLError as e:
            _log_ssl_error("bitget", url, e)
            return []
        except Exception as e:
            logger.warning(f"Ошибка получения сделок Bitget: {e}")
            return []
    
    @staticmethod
    async def _fetch_trades_hyperliquid(symbol: str, market: str, start_time: int, end_time: int) -> List[Dict]:
        """
        Получает историю сделок с Hyperliquid через REST API
        
        Args:
            symbol: Символ торговой пары
            market: Тип рынка (spot/linear)
            start_time: Начальное время в миллисекундах
            end_time: Конечное время в миллисекундах
            
        Returns:
            Список сделок
        """
        try:
            # Hyperliquid API
            url = "https://api.hyperliquid.xyz/info"
            
            # Hyperliquid использует POST запросы
            payload = {
                "type": "trades",
                "coin": symbol,
                "n": 1000
            }
            
            connector = _create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        trades_list = data if isinstance(data, list) else []
                        
                        trades = []
                        for trade in trades_list:
                            price = float(trade.get("px", 0))
                            size = float(trade.get("sz", 0))
                            timestamp = int(trade.get("time", 0))
                            side = trade.get("side", "").lower()
                            
                            # Фильтруем по времени
                            if timestamp < start_time or timestamp > end_time:
                                continue
                            
                            trades.append({
                                "price": price,
                                "quantity": size,
                                "timestamp": timestamp,
                                "is_buyer": side == "b"  # 'b' для buy, 's' для sell
                            })
                        return trades
                    else:
                        logger.warning(f"Ошибка получения сделок Hyperliquid: HTTP {response.status}")
                        return []
        except ssl.SSLError as e:
            _log_ssl_error("hyperliquid", url, e)
            return []
        except Exception as e:
            logger.warning(f"Ошибка получения сделок Hyperliquid: {e}")
            return []
    
    @staticmethod
    async def _fetch_trades(exchange: str, symbol: str, market: str, start_time: int, end_time: int) -> List[Dict]:
        """
        Получает историю сделок с биржи
        
        Args:
            exchange: Название биржи
            symbol: Символ торговой пары
            market: Тип рынка (spot/linear)
            start_time: Начальное время в миллисекундах
            end_time: Конечное время в миллисекундах
            
        Returns:
            Список сделок
        """
        exchange_lower = exchange.lower()
        
        if exchange_lower == "binance":
            return await ChartGenerator._fetch_trades_binance(symbol, market, start_time, end_time)
        elif exchange_lower == "bybit":
            return await ChartGenerator._fetch_trades_bybit(symbol, market, start_time, end_time)
        elif exchange_lower == "gate":
            return await ChartGenerator._fetch_trades_gate(symbol, market, start_time, end_time)
        elif exchange_lower == "bitget":
            return await ChartGenerator._fetch_trades_bitget(symbol, market, start_time, end_time)
        elif exchange_lower == "hyperliquid":
            return await ChartGenerator._fetch_trades_hyperliquid(symbol, market, start_time, end_time)
        else:
            logger.warning(f"Неподдерживаемая биржа для получения сделок: {exchange}")
            return []
    
    @staticmethod
    async def generate_chart(
        candle: Candle,
        delta: float,
        volume_usdt: float,
        wick_pct: float,
        spike_ratio: Optional[float] = None,
        duration: Optional[float] = None,
        strategy: Optional[str] = None,
        score: Optional[float] = None,
        timer: Optional[Any] = None  # PerformanceTimer для замера времени
    ) -> Optional[bytes]:
        """
        Генерирует тиковый график прострела
        
        Args:
            candle: Свеча с детектом
            delta: Дельта в процентах
            volume_usdt: Объём в USDT
            wick_pct: Процент тени
            spike_ratio: Spike Ratio (опционально)
            duration: Duration (опционально)
            strategy: Strategy (опционально)
            score: Score (опционально)
            
        Returns:
            Байты PNG изображения или None при ошибке
        """
        try:
            # Проверяем кэш
            cache_key = ChartGenerator._get_cache_key(
                candle.exchange,
                candle.market,
                candle.symbol,
                candle.ts_ms
            )
            
            cached_chart = ChartGenerator._get_cached_chart(cache_key)
            if cached_chart:
                return cached_chart
            
            # Вычисляем период для запроса (60 минут до детекта включительно)
            # candle.ts_ms - это начало секунды детекта, свеча содержит сделки от ts_ms до ts_ms + 999ms
            # Запрашиваем сделки от (ts_ms - 60 минут) до (ts_ms + 1000ms), чтобы включить все сделки свечи
            # end_time_ms = ts_ms + 1000 означает запрос до конца секунды детекта, а не до начала
            detection_time_ms = candle.ts_ms
            start_time_ms = detection_time_ms - (60 * 60 * 1000)  # 60 минут назад
            end_time_ms = detection_time_ms + 1000  # До конца секунды детекта включительно (ts_ms + 1000ms)
            
            # Получаем историю сделок
            if timer:
                timer.start("chart.fetch")
            trades = await ChartGenerator._fetch_trades(
                candle.exchange,
                candle.symbol,
                candle.market,
                start_time_ms,
                end_time_ms
            )
            if timer:
                timer.end("chart.fetch")
            
            if not trades:
                logger.warning(f"Не удалось получить сделки для графика: {candle.exchange} {candle.market} {candle.symbol}")
                return None
            
            # Фильтруем сделки: показываем все сделки до конца секунды детекта включительно
            # candle.ts_ms - это начало секунды, свеча содержит сделки от ts_ms до ts_ms + 999ms
            # Поэтому включаем все сделки до начала следующей секунды (ts_ms + 1000ms)
            # Последние сделки на графике - это сама свеча детекта
            end_of_detection_second_ms = detection_time_ms + 1000  # Конец секунды детекта
            trades = [t for t in trades if t["timestamp"] < end_of_detection_second_ms]
            
            if not trades:
                logger.warning(f"Нет сделок до момента детекта для графика: {candle.exchange} {candle.market} {candle.symbol}")
                return None
            
            # Сортируем сделки по времени
            trades.sort(key=lambda t: t["timestamp"])
            
            # Подготавливаем данные для графика
            timestamps = [datetime.fromtimestamp(t["timestamp"] / 1000) for t in trades]
            prices = [t["price"] for t in trades]
            colors = ["green" if t["is_buyer"] else "red" for t in trades]
            
            # Вычисляем базовую цену (цена первой сделки) для конвертации в проценты
            # Ищем первую ненулевую цену из сделок
            base_price = None
            for price in prices:
                if price > 0:
                    base_price = price
                    break
            
            # Если все цены нулевые, используем значения из свечи
            if base_price is None or base_price == 0:
                # Пробуем использовать close, open, high или low свечи
                if candle.close > 0:
                    base_price = candle.close
                elif candle.open > 0:
                    base_price = candle.open
                elif candle.high > 0:
                    base_price = candle.high
                elif candle.low > 0:
                    base_price = candle.low
                else:
                    # Если все значения нулевые, это ошибка данных
                    logger.error(f"Все цены нулевые для графика: {candle.exchange} {candle.market} {candle.symbol}")
                    return None
            
            # Преобразуем цены в проценты изменения относительно базовой цены
            price_percentages = [((price - base_price) / base_price) * 100 for price in prices]
            
            # Создаем график
            if timer:
                timer.start("chart.render")
            fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)  # 1920x1080 пикселей
            
            # Рисуем scatter plot с точками сделок (в процентах)
            ax.scatter(timestamps, price_percentages, c=colors, s=6, alpha=0.6)
            
            # Рисуем жёлтую линейку справа от прострела (от high до low свечи)
            # Используем точное время свечи для определения позиции
            detection_time = datetime.fromtimestamp(candle.ts_ms / 1000)
            
            # Находим позицию для жёлтой линейки - справа от последней сделки
            if timestamps:
                # Находим последнюю сделку, которая была до или в момент детекта
                trades_before_detection = [t for t in timestamps if t <= detection_time]
                
                if trades_before_detection:
                    # Берём последнюю сделку до детекта
                    last_trade_time = max(trades_before_detection)
                else:
                    # Если нет сделок до детекта, берём первую сделку
                    last_trade_time = min(timestamps)
                
                # Добавляем небольшой отступ вправо (примерно 2% от диапазона времени или минимум 10 секунд)
                if len(timestamps) > 1:
                    time_range = (max(timestamps) - min(timestamps)).total_seconds()
                    # Используем меньший отступ, чтобы линейка была ближе к моменту детекта
                    offset_seconds = max(time_range * 0.02, 10)  # Минимум 10 секунд
                    marker_time = last_trade_time + timedelta(seconds=offset_seconds)
                else:
                    # Если только одна сделка, добавляем 10 секунд
                    marker_time = last_trade_time + timedelta(seconds=10)
                
                # Преобразуем high и low свечи в проценты для жёлтой линии
                candle_low_pct = ((candle.low - base_price) / base_price) * 100
                candle_high_pct = ((candle.high - base_price) / base_price) * 100
                
                # Рисуем вертикальную линию от high до low свечи жёлтым цветом
                ax.plot(
                    [marker_time, marker_time],
                    [candle_low_pct, candle_high_pct],
                    color='yellow',
                    linewidth=3,
                    alpha=0.9,
                    label='Момент детекта'
                )
            
            # Форматируем оси
            ax.set_xlabel('Время', fontsize=12)
            ax.set_ylabel('Процент изменения (%)', fontsize=12)
            ax.grid(True, alpha=0.3)
            
            # Форматируем время на оси X
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
            plt.xticks(rotation=45)
            
            # Получаем символ с торговой парой для заголовка
            symbol_with_pair = await get_symbol_with_pair(
                candle.symbol,
                candle.exchange,
                candle.market
            )
            
            # Формируем заголовок с метриками
            market_text = "SPOT" if candle.market == "spot" else "FUTURES"
            title_parts = [
                f"{candle.exchange.upper()} | {market_text}",
                f"Symbol: {symbol_with_pair}",
                f"Δ: {delta:.2f}%",
                f"Volume: {volume_usdt:,.0f} USDT",
            ]
            
            if spike_ratio is not None:
                title_parts.append(f"Spike Ratio: {spike_ratio:.2f}")
            if duration is not None:
                title_parts.append(f"Duration: {duration:.2f}s")
            if strategy:
                title_parts.append(f"Strategy: {strategy}")
            if score is not None:
                title_parts.append(f"Score: {score:.2f}")
            
            title = " | ".join(title_parts)
            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
            
            # Добавляем легенду
            ax.legend()
            
            # Сохраняем в буфер
            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
            buf.seek(0)
            image_bytes = buf.read()
            buf.close()
            plt.close(fig)
            
            # Сохраняем в кэш
            ChartGenerator._save_to_cache(cache_key, image_bytes)
            
            if timer:
                timer.end("chart.render")
            
            logger.debug(f"График успешно сгенерирован: {candle.exchange} {candle.market} {candle.symbol}")
            return image_bytes
            
        except Exception as e:
            logger.error(f"Ошибка генерации графика: {e}", exc_info=True, extra={
                "log_to_db": True,
                "error_type": "chart_generation_error",
                "exchange": candle.exchange,
                "market": candle.market,
                "symbol": candle.symbol,
            })
            return None


# Глобальный экземпляр генератора
chart_generator = ChartGenerator()

