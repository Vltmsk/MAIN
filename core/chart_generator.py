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
from typing import Optional, List, Dict, Tuple, Any, Literal, TypedDict
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

# Структура тика для тикового графика
class Tick(TypedDict):
    id: int
    ts: int          # timestamp в миллисекундах
    price: float
    qty: float
    side: Literal["buy", "sell"]

# Кэш для графиков: {cache_key: (image_bytes, timestamp)}
_chart_cache: Dict[str, Tuple[bytes, float]] = {}
CACHE_TTL = 600  # 10 минут


async def _fetch_latest_trades_binance_spot(symbol: str, limit: int = 1000) -> List[dict]:
    """
    Получить последние trades со спота Binance (последние limit сделок).
    Использует GET /api/v3/trades (limit максимум: 1000, request weight: 10 за запрос).
    
    Args:
        symbol: Символ торговой пары (например, BTCUSDT)
        limit: Максимальное количество сделок (до 1000)
        
    Returns:
        Список словарей с trades
    """
    url = "https://api.binance.com/api/v3/trades"
    params = {"symbol": symbol.upper(), "limit": limit}
    
    connector = _create_ssl_connector()
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Ошибка получения trades Binance Spot: HTTP {response.status}")
                    return []
    except ssl.SSLError as e:
        _log_ssl_error("binance", url, e)
        return []
    except Exception as e:
        logger.warning(f"Ошибка получения trades Binance Spot: {e}")
        return []


async def _fetch_latest_trades_binance_futures(symbol: str, limit: int = 1000) -> List[dict]:
    """
    Получить последние trades с Binance Futures USDT-M.
    Использует GET /fapi/v1/trades (limit максимум: 1000, request weight: 5 за запрос).
    
    Args:
        symbol: Символ торговой пары (например, BTCUSDT)
        limit: Максимальное количество сделок (до 1000)
        
    Returns:
        Список словарей с trades
    """
    url = "https://fapi.binance.com/fapi/v1/trades"
    params = {"symbol": symbol.upper(), "limit": limit}
    
    connector = _create_ssl_connector()
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Ошибка получения trades Binance Futures: HTTP {response.status}")
                    return []
    except ssl.SSLError as e:
        _log_ssl_error("binance", url, e)
        return []
    except Exception as e:
        logger.warning(f"Ошибка получения trades Binance Futures: {e}")
        return []


def _trades_to_ticks(trades: List[dict]) -> List[Tick]:
    """
    Конвертация списка trades в список тиков (Tick).
    Предполагаем, что trades уже отсортированы Binance по времени (oldest -> newest).
    
    Формат trades API:
    - SPOT: id, price, qty, time, isBuyerMaker, isBestMatch
    - Futures: id, price, qty, time, isBuyerMaker
    
    Args:
        trades: Список словарей с trades от Binance
        
    Returns:
        Список тиков
    """
    ticks: List[Tick] = []
    for t in trades:
        # Формат trades: id, price, qty, time (в миллисекундах), isBuyerMaker
        # isBuyerMaker=True означает, что покупатель был мейкером, т.е. агрессор - продавец (SELL)
        # isBuyerMaker=False означает, что продавец был мейкером, т.е. агрессор - покупатель (BUY)
        tick: Tick = {
            "id": int(t["id"]),
            "ts": int(t["time"]),
            "price": float(t["price"]),
            "qty": float(t["qty"]),
            "side": "sell" if t["isBuyerMaker"] else "buy",
        }
        ticks.append(tick)
    
    # На всякий случай сортируем по ts (Binance уже возвращает в правильном порядке)
    ticks.sort(key=lambda t: t["ts"])
    return ticks


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
    async def _fetch_ticks_binance(symbol: str, market: str) -> List[Tick]:
        """
        Получает последние тики с Binance через REST API trades (последние 1000 сделок).
        Использует trades API вместо aggTrades для построения тикового графика.
        
        Лимиты:
        - SPOT: GET /api/v3/trades - limit 1000, weight 10 за запрос
        - Futures: GET /fapi/v1/trades - limit 1000, weight 5 за запрос
        - Общий IP-лимит для SPOT: ~6000 weight/мин
        
        Args:
            symbol: Символ торговой пары (например, BTCUSDT)
            market: Тип рынка (spot/linear)
            
        Returns:
            Список тиков (Tick)
        """
        try:
            # Получаем последние trades (без времени)
            if market == "spot":
                raw_trades = await _fetch_latest_trades_binance_spot(symbol, limit=1000)
            else:  # linear/futures
                raw_trades = await _fetch_latest_trades_binance_futures(symbol, limit=1000)
            
            if not raw_trades:
                return []
            
            # Конвертируем trades в тики
            ticks = _trades_to_ticks(raw_trades)
            return ticks
            
        except Exception as e:
            logger.warning(f"Ошибка получения тиков Binance: {e}")
            return []
    
    @staticmethod
    async def _fetch_ticks(exchange: str, symbol: str, market: str) -> List[Tick]:
        """
        Получает последние тики с биржи
        
        Args:
            exchange: Название биржи
            symbol: Символ торговой пары
            market: Тип рынка (spot/linear)
            
        Returns:
            Список тиков (Tick) или пустой список для неподдерживаемых бирж
        """
        exchange_lower = exchange.lower()
        
        if exchange_lower == "binance":
            return await ChartGenerator._fetch_ticks_binance(symbol, market)
        else:
            logger.warning(f"Графики поддерживаются только для Binance. Биржа {exchange} не поддерживается.")
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
        Генерирует тиковый график прострела для Binance
        
        Args:
            candle: Свеча с детектом
            delta: Дельта в процентах
            volume_usdt: Объём в USDT
            wick_pct: Процент тени
            spike_ratio: Spike Ratio (опционально)
            duration: Duration в миллисекундах (опционально)
            strategy: Strategy (опционально)
            score: Score (опционально)
            
        Returns:
            Байты PNG изображения или None при ошибке
        """
        try:
            # Проверяем биржу - графики поддерживаются только для Binance
            if candle.exchange.lower() != "binance":
                logger.warning(f"Графики поддерживаются только для Binance. Биржа: {candle.exchange}")
                return None
            
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
            
            # Получаем последние тики
            if timer:
                timer.start("chart.fetch")
            ticks = await ChartGenerator._fetch_ticks(
                candle.exchange,
                candle.symbol,
                candle.market
            )
            if timer:
                timer.end("chart.fetch")
            
            if not ticks:
                logger.warning(f"Не удалось получить тики для графика: {candle.exchange} {candle.market} {candle.symbol}")
                return None
            
            # НЕ фильтруем тики - показываем все полученные трейды (до 1000)
            # Сортируем тики по времени (на всякий случай)
            ticks.sort(key=lambda t: t["ts"])
            
            # Подготавливаем данные для графика
            timestamps = [datetime.fromtimestamp(t["ts"] / 1000) for t in ticks]
            prices = [t["price"] for t in ticks]
            
            # Базовая цена - это цена в момент детекта (candle.open), чтобы начало стрелы было на 0%
            # Используем цену открытия свечи как базовую для расчёта процентов
            if candle.open > 0:
                base_price = candle.open
            elif candle.close > 0:
                base_price = candle.close
            elif candle.high > 0:
                base_price = candle.high
            elif candle.low > 0:
                base_price = candle.low
            else:
                logger.error(f"Все цены нулевые для графика: {candle.exchange} {candle.market} {candle.symbol}")
                return None
            
            # Преобразуем цены в проценты изменения относительно базовой цены
            price_percentages = [((price - base_price) / base_price) * 100 for price in prices]
            
            # Создаем график
            if timer:
                timer.start("chart.render")
            fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)  # 1920x1080 пикселей
            
            # Рисуем тиковый график: каждая сделка (тик) отображается как отдельная точка
            # Разделяем тики на покупки и продажи для правильной визуализации
            buy_timestamps = []
            buy_prices = []
            sell_timestamps = []
            sell_prices = []
            
            for i, tick in enumerate(ticks):
                if tick["side"] == "buy":
                    buy_timestamps.append(timestamps[i])
                    buy_prices.append(price_percentages[i])
                else:  # sell
                    sell_timestamps.append(timestamps[i])
                    sell_prices.append(price_percentages[i])
            
            # Рисуем точки покупок (зелёные)
            if buy_timestamps:
                ax.scatter(
                    buy_timestamps,
                    buy_prices,
                    color="green",
                    s=15,  # размер точки (увеличен для лучшей видимости)
                    alpha=0.8,
                    label="Buy" if len(buy_timestamps) > 0 else None
                )
            
            # Рисуем точки продаж (красные)
            if sell_timestamps:
                ax.scatter(
                    sell_timestamps,
                    sell_prices,
                    color="red",
                    s=15,  # размер точки (увеличен для лучшей видимости)
                    alpha=0.8,
                    label="Sell" if len(sell_timestamps) > 0 else None
                )
            
            # Для лучшей визуализации также рисуем тонкие линии между тиками,
            # чтобы видеть последовательность сделок во времени
            if len(ticks) > 1:
                ax.plot(
                    timestamps,
                    price_percentages,
                    color="gray",
                    linewidth=0.5,
                    alpha=0.15,  # Полупрозрачная линия
                    linestyle="-"
                )
            
            # Форматируем оси
            ax.set_xlabel('Время', fontsize=12)
            ax.set_ylabel('Процент изменения (%)', fontsize=12)
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            
            # Форматируем время на оси X (показываем минуты)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
            plt.xticks(rotation=45, ha='right')
            
            # Получаем символ с торговой парой для заголовка
            symbol_with_pair = await get_symbol_with_pair(
                candle.symbol,
                candle.exchange,
                candle.market
            )
            
            # Формируем заголовок в формате из изображения
            # Формат: "Binance Futures | MONUSDT ↑ UP 2.40% (0.035370→0.036220)"
            market_text = "Spot" if candle.market == "spot" else "Futures"
            direction = "↑ UP" if delta > 0 else "↓ DOWN"
            price_change_pct = abs(delta)
            start_price = prices[0] if prices else base_price
            end_price = prices[-1] if prices else base_price
            
            # Форматируем цены: убираем лишние нули в конце
            def format_price(price: float) -> str:
                # Для очень малых цен используем научную нотацию или больше знаков после запятой
                if price == 0:
                    return "0"
                # Определяем количество значащих цифр
                if price < 0.00000001:
                    # Для очень малых цен используем научную нотацию
                    return f"{price:.2e}"
                elif price < 0.0001:
                    # Для малых цен используем до 12 знаков после запятой
                    price_str = f"{price:.12f}".rstrip("0").rstrip(".")
                    return price_str
                else:
                    # Для обычных цен используем до 8 знаков после запятой
                    price_str = f"{price:.8f}".rstrip("0").rstrip(".")
                    return price_str
            
            start_price_str = format_price(start_price)
            end_price_str = format_price(end_price)
            
            header_line1 = f"{candle.exchange.capitalize()} {market_text} | {symbol_with_pair} {direction} {price_change_pct:.2f}% ({start_price_str}→{end_price_str})"
            
            # Формируем вторую строку заголовка с метриками
            # Формат: "Volume: $897K | Spike Ratio: 240.7x | Duration: 49ms | Strategy: Ultra Large Strike | Score: 104.03"
            if volume_usdt < 1000:
                volume_str = f"${volume_usdt:.0f}"
            elif volume_usdt < 1_000_000:
                volume_str = f"${volume_usdt/1000:.0f}K"
            else:
                volume_str = f"${volume_usdt/1_000_000:.2f}M"
            
            header_parts2 = [f"Volume: {volume_str}"]
            
            if spike_ratio is not None:
                header_parts2.append(f"Spike Ratio: {spike_ratio:.1f}x")
            if duration is not None:
                # duration может быть в секундах или миллисекундах
                if duration < 10:  # Если меньше 10, вероятно в секундах, конвертируем в мс
                    duration_ms = duration * 1000
                else:
                    duration_ms = duration
                header_parts2.append(f"Duration: {duration_ms:.0f}ms")
            if strategy:
                header_parts2.append(f"Strategy: {strategy}")
            if score is not None:
                header_parts2.append(f"Score: {score:.2f}")
            
            header_line2 = " | ".join(header_parts2)
            
            # Устанавливаем заголовок (две строки)
            ax.set_title(f"{header_line1}\n{header_line2}", fontsize=12, fontweight='bold', pad=15, loc='left')
            
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

