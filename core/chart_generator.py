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


async def _fetch_latest_aggtrades_binance_spot(symbol: str, limit: int = 1000) -> List[dict]:
    """
    Получить сырые aggTrades со спота Binance (последние limit сделок).
    Никаких startTime/fromId - только последние aggTrades.
    
    Args:
        symbol: Символ торговой пары (например, BTCUSDT)
        limit: Максимальное количество сделок (до 1000)
        
    Returns:
        Список словарей с aggTrades
    """
    url = "https://api.binance.com/api/v3/aggTrades"
    params = {"symbol": symbol.upper(), "limit": limit}
    
    connector = _create_ssl_connector()
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Ошибка получения aggTrades Binance Spot: HTTP {response.status}")
                    return []
    except ssl.SSLError as e:
        _log_ssl_error("binance", url, e)
        return []
    except Exception as e:
        logger.warning(f"Ошибка получения aggTrades Binance Spot: {e}")
        return []


async def _fetch_latest_aggtrades_binance_futures(symbol: str, limit: int = 1000) -> List[dict]:
    """
    То же самое, но для Binance Futures USDT-M.
    
    Args:
        symbol: Символ торговой пары (например, BTCUSDT)
        limit: Максимальное количество сделок (до 1000)
        
    Returns:
        Список словарей с aggTrades
    """
    url = "https://fapi.binance.com/fapi/v1/aggTrades"
    params = {"symbol": symbol.upper(), "limit": limit}
    
    connector = _create_ssl_connector()
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Ошибка получения aggTrades Binance Futures: HTTP {response.status}")
                    return []
    except ssl.SSLError as e:
        _log_ssl_error("binance", url, e)
        return []
    except Exception as e:
        logger.warning(f"Ошибка получения aggTrades Binance Futures: {e}")
        return []


def _aggtrades_to_ticks(aggtrades: List[dict]) -> List[Tick]:
    """
    Конвертация списка aggTrades в список тиков (Tick).
    Предполагаем, что aggtrades уже отсортированы Binance по времени (oldest -> newest).
    
    Args:
        aggtrades: Список словарей с aggTrades от Binance
        
    Returns:
        Список тиков
    """
    ticks: List[Tick] = []
    for a in aggtrades:
        tick: Tick = {
            "id": int(a["a"]),
            "ts": int(a["T"]),
            "price": float(a["p"]),
            "qty": float(a["q"]),
            "side": "sell" if a["m"] else "buy",  # m==True -> buyer is maker -> агрессор продавец -> SELL
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
        Получает последние тики с Binance через REST API aggTrades (последние 1000 сделок).
        Согласно chart.md: запрашиваем последние 1000 aggTrades без startTime/endTime.
        
        Args:
            symbol: Символ торговой пары (например, BTCUSDT)
            market: Тип рынка (spot/linear)
            
        Returns:
            Список тиков (Tick)
        """
        try:
            # Получаем последние aggTrades (без времени)
            if market == "spot":
                raw_aggtrades = await _fetch_latest_aggtrades_binance_spot(symbol, limit=1000)
            else:  # linear/futures
                raw_aggtrades = await _fetch_latest_aggtrades_binance_futures(symbol, limit=1000)
            
            if not raw_aggtrades:
                return []
            
            # Конвертируем aggTrades в тики
            ticks = _aggtrades_to_ticks(raw_aggtrades)
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
            
            # Фильтруем тики: показываем все тики до конца секунды детекта включительно
            detection_time_ms = candle.ts_ms
            end_of_detection_second_ms = detection_time_ms + 1000  # Конец секунды детекта
            ticks = [t for t in ticks if t["ts"] < end_of_detection_second_ms]
            
            if not ticks:
                logger.warning(f"Нет тиков до момента детекта для графика: {candle.exchange} {candle.market} {candle.symbol}")
                return None
            
            # Сортируем тики по времени (на всякий случай)
            ticks.sort(key=lambda t: t["ts"])
            
            # Подготавливаем данные для графика
            timestamps = [datetime.fromtimestamp(t["ts"] / 1000) for t in ticks]
            prices = [t["price"] for t in ticks]
            
            # Вычисляем базовую цену (цена первого тика) для конвертации в проценты
            base_price = prices[0] if prices[0] > 0 else None
            
            # Если базовая цена нулевая, используем значения из свечи
            if base_price is None or base_price == 0:
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
            
            # Рисуем тиковый график: линия с зелеными/красными сегментами
            # Для каждого сегмента между тиками рисуем линию соответствующего цвета
            for i in range(len(ticks) - 1):
                color = "green" if ticks[i]["side"] == "buy" else "red"
                ax.plot(
                    [timestamps[i], timestamps[i + 1]],
                    [price_percentages[i], price_percentages[i + 1]],
                    color=color,
                    linewidth=1.5,
                    alpha=0.8
                )
            
            # Находим пик для стрелки (максимальное значение процента)
            if price_percentages:
                max_pct_idx = max(range(len(price_percentages)), key=lambda i: price_percentages[i])
                max_pct_time = timestamps[max_pct_idx]
                max_pct_value = price_percentages[max_pct_idx]
                
                # Получаем текущие пределы оси Y
                y_min, y_max = ax.get_ylim()
                y_range = y_max - y_min
                
                # Добавляем стрелку вверх на пике, если пик выходит за пределы графика
                # Стрелка должна указывать вверх от пика
                arrow_length = y_range * 0.1  # 10% от диапазона Y
                
                # Если пик близко к верхней границе или выходит за нее, рисуем стрелку
                if max_pct_value >= y_max * 0.8:  # Если пик в верхних 20% графика
                    # Рисуем пунктирную стрелку вверх от пика
                    ax.annotate('',
                        xy=(max_pct_time, max_pct_value + arrow_length),  # Назначение: точка выше пика
                        xytext=(max_pct_time, max_pct_value),  # Источник: пиковая точка
                        arrowprops=dict(
                            arrowstyle='->',
                            color='green',
                            lw=2.5,
                            alpha=0.8,
                            linestyle='--',
                            connectionstyle='arc3'
                        ),
                        annotation_clip=False  # Позволяет рисовать стрелку за пределами графика
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

