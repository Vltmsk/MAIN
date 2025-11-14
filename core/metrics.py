"""
Метрики и статистика проекта
"""
import time
from typing import Dict, Optional
from collections import defaultdict


class Metrics:
    """Сбор и хранение метрик работы всех бирж"""
    
    def __init__(self):
        # Структура: stats[exchange][market] = {"candles": 0, "trades": 0, "errors": 0, "last_candle_time": None}
        self.stats = defaultdict(lambda: defaultdict(lambda: {
            "candles": 0,
            "trades": 0,
            "errors": 0,
            "last_candle_time": None,
        }))
        self.total_candles = 0
        self.total_trades = 0
        
        # Для подсчёта T/s (ticks per second)
        # Структура: ticks_counter[(exchange, market)] = {"count": int, "start_time": float}
        self._ticks_counter: Dict[tuple, Dict] = {}
        
    def inc_candle(self, exchange: str, market: str = None):
        """Увеличить счётчик свечей."""
        current_time = time.time()
        if market:
            self.stats[exchange][market]["candles"] += 1
            # Сохраняем время последней свечи в формате ISO timestamp
            from datetime import datetime
            self.stats[exchange][market]["last_candle_time"] = datetime.fromtimestamp(current_time).isoformat()
        else:
            # Для обратной совместимости, если market не указан
            self.stats[exchange]["total"]["candles"] += 1
        self.total_candles += 1
        
    def inc_trade(self, exchange: str, market: str = None):
        """
        Увеличить счётчик сделок (ticks).
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear), опционально
        """
        key = (exchange, market) if market else (exchange, None)
        
        if key not in self._ticks_counter:
            self._ticks_counter[key] = {
                "count": 0,
                "start_time": time.time(),
            }
        
        self._ticks_counter[key]["count"] += 1
        
        # Для обратной совместимости
        if market:
            self.stats[exchange][market]["trades"] += 1
        else:
            self.stats[exchange]["trades"] += 1
        self.total_trades += 1
        
    def inc_error(self, exchange: str):
        """Увеличить счётчик ошибок."""
        self.stats[exchange]["errors"] += 1
        
    def get_ticks_per_second(self, exchange: str, market: str) -> Optional[float]:
        """
        Получить среднее количество ticks per second для биржи и рынка.
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            
        Returns:
            Среднее количество ticks per second или None, если данных нет
        """
        key = (exchange, market)
        
        if key not in self._ticks_counter:
            return None
        
        counter = self._ticks_counter[key]
        elapsed_time = time.time() - counter["start_time"]
        
        if elapsed_time <= 0:
            return None
        
        ticks_per_second = counter["count"] / elapsed_time
        return ticks_per_second
    
    def get_stats(self) -> Dict:
        """Получить текущую статистику."""
        return {
            "total_candles": self.total_candles,
            "total_trades": self.total_trades,
            "by_exchange": dict(self.stats),
        }
        
    def reset(self):
        """Сбросить статистику."""
        self.stats.clear()
        self.total_candles = 0
        self.total_trades = 0
        self._ticks_counter.clear()

