"""
Универсальный построитель свечей для всех бирж
"""
from typing import Dict, Optional, Callable, Awaitable
from dataclasses import dataclass


@dataclass
class Candle:
    """
    1-секундная свеча
    
    Attributes:
        ts_ms: Timestamp в миллисекундах (начало секунды)
        open: Цена открытия
        high: Максимальная цена
        low: Минимальная цена
        close: Цена закрытия
        volume: Объём в базовой валюте
        market: "spot" или "linear"
        exchange: Название биржи (например, "binance")
        symbol: Название пары (например, "BTCUSDT")
    """
    ts_ms: int      # Timestamp в миллисекундах (начало секунды)
    open: float     # Цена открытия
    high: float     # Максимальная цена
    low: float      # Минимальная цена
    close: float    # Цена закрытия
    volume: float   # Объём в базовой валюте (например, BTC для BTCUSDT)
    market: str     # "spot" или "linear"
    exchange: str   # Название биржи (например, "binance")
    symbol: str     # Название пары (например, "BTCUSDT")


class CandleBuilder:
    """
    Построитель 1-секундных свечей из сделок.
    
    Использует коллекцию для хранения активных свечей по ключу (exchange, market, symbol).
    При добавлении сделки автоматически завершает предыдущую секунду, если сделка относится к новой.
    """
    
    def __init__(self, maxlen: int = 1000, on_trade: Optional[Callable[[str, str], Awaitable[None]]] = None):
        """
        Инициализация построителя свечей.
        
        Args:
            maxlen: Максимальное количество свечей в памяти (для ограничения использования памяти)
            on_trade: Опциональный callback для подсчёта трейдов: on_trade(exchange, market)
        """
        self.maxlen = maxlen
        self.on_trade = on_trade
        # Словарь активных свечей: {(exchange, market, symbol): CurrentCandle}
        self._active_candles: Dict[tuple, 'CurrentCandle'] = {}
        
    async def add_trade(
        self,
        exchange: str,
        market: str,
        symbol: str,
        price: float,
        qty: float,
        ts_ms: int,
    ) -> Optional[Candle]:
        """
        Добавить сделку и получить завершённую свечу (если есть).
        
        Args:
            exchange: Название биржи (например, "binance")
            market: "spot" или "linear"
            symbol: Название пары (например, "BTCUSDT")
            price: Цена сделки
            qty: Объём сделки в базовой валюте
            ts_ms: Timestamp сделки в миллисекундах
            
        Returns:
            Candle или None, если свеча ещё не завершена
        """
        # Вызываем callback для подсчёта трейда, если он установлен
        if self.on_trade:
            try:
                await self.on_trade(exchange, market)
            except Exception:
                pass  # Игнорируем ошибки в callback
        
        # Округляем timestamp до начала секунды
        candle_ts_ms = (ts_ms // 1000) * 1000
        
        key = (exchange, market, symbol)
        
        # Получаем или создаём активную свечу для этого ключа
        if key not in self._active_candles:
            self._active_candles[key] = CurrentCandle(
                exchange=exchange,
                market=market,
                symbol=symbol,
                ts_ms=candle_ts_ms
            )
        
        active_candle = self._active_candles[key]
        
        # Проверяем, относится ли сделка к текущей активной свече
        if candle_ts_ms != active_candle.ts_ms:
            # Сделка относится к новой секунде - завершаем предыдущую
            finished = active_candle.to_candle()
            # Создаём новую активную свечу для новой секунды
            self._active_candles[key] = CurrentCandle(
                exchange=exchange,
                market=market,
                symbol=symbol,
                ts_ms=candle_ts_ms
            )
            
            # Добавляем сделку в новую свечу
            self._active_candles[key].add_trade(price, qty)
            
            return finished
        else:
            # Сделка относится к текущей активной свече
            active_candle.add_trade(price, qty)
            return None


class CurrentCandle:
    """
    Временное представление свечи в процессе построения.
    """
    
    def __init__(self, exchange: str, market: str, symbol: str, ts_ms: int):
        self.exchange = exchange
        self.market = market
        self.symbol = symbol
        self.ts_ms = ts_ms
        self.open: Optional[float] = None
        self.high: Optional[float] = None
        self.low: Optional[float] = None
        self.close: Optional[float] = None
        self.volume = 0.0
        self._first_trade = True
        
    def add_trade(self, price: float, qty: float):
        """Добавить сделку в свечу."""
        if self._first_trade:
            self.open = price
            self.high = price
            self.low = price
            self._first_trade = False
        
        self.close = price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.volume += qty
        
    def to_candle(self) -> Optional[Candle]:
        """
        Конвертировать в финальную Candle или None, если не было сделок.
        
        Returns:
            Candle или None
        """
        if self._first_trade:
            # Не было сделок
            return None
            
        return Candle(
            ts_ms=self.ts_ms,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            market=self.market,
            exchange=self.exchange,
            symbol=self.symbol,
        )

