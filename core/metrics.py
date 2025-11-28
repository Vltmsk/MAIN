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
        
        # Для подсчёта свечей в секунду для Binance (candles per second)
        # Структура: candles_counter[(exchange, market)] = {"count": int, "start_time": float}
        self._candles_counter: Dict[tuple, Dict] = {}
        
        # Время последней очистки старых счетчиков
        self._last_cleanup_time = time.time()
        self._cleanup_interval = 3600  # Очистка каждый час
        
    def inc_candle(self, exchange: str, market: str = None):
        """
        Увеличить счётчик свечей.
        
        Args:
            exchange: Название биржи (например, "binance")
            market: Тип рынка ("spot" или "linear"), опционально
        
        Примечание:
            Для Binance сохраняется время последней свечи в формате ISO timestamp
            (поле "last_candle_time" в статистике). Для других бирж это поле не обновляется.
        """
        current_time = time.time()
        if market:
            self.stats[exchange][market]["candles"] += 1
            # Сохраняем время последней свечи в формате ISO timestamp
            from datetime import datetime
            self.stats[exchange][market]["last_candle_time"] = datetime.fromtimestamp(current_time).isoformat()
            
            # Для Binance считаем свечи в секунду (аналогично ticks для других бирж)
            if exchange == "binance":
                key = (exchange, market)
                if key not in self._candles_counter:
                    self._candles_counter[key] = {
                        "count": 0,
                        "start_time": time.time(),
                    }
                self._candles_counter[key]["count"] += 1
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
    
    def get_candles_per_second(self, exchange: str, market: str) -> Optional[float]:
        """
        Получить среднее количество candles per second для биржи и рынка.
        Используется для Binance, где получаем готовые свечи, а не трейды.
        
        Args:
            exchange: Название биржи
            market: Тип рынка (spot/linear)
            
        Returns:
            Среднее количество candles per second или None, если данных нет
        """
        key = (exchange, market)
        
        if key not in self._candles_counter:
            return None
        
        counter = self._candles_counter[key]
        elapsed_time = time.time() - counter["start_time"]
        
        if elapsed_time <= 0:
            return None
        
        candles_per_second = counter["count"] / elapsed_time
        return candles_per_second
    
    def _cleanup_old_counters(self):
        """
        Периодическая очистка старых счетчиков для предотвращения утечки памяти.
        Удаляет счетчики, которые не обновлялись более 2 часов.
        """
        current_time = time.time()
        # Выполняем очистку не чаще чем раз в час
        if current_time - self._last_cleanup_time < self._cleanup_interval:
            return
        
        self._last_cleanup_time = current_time
        max_age = 7200  # 2 часа
        
        # Очищаем ticks_counter
        keys_to_remove = []
        for key, counter in self._ticks_counter.items():
            age = current_time - counter.get("start_time", 0)
            if age > max_age:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._ticks_counter[key]
        
        # Очищаем candles_counter
        keys_to_remove = []
        for key, counter in self._candles_counter.items():
            age = current_time - counter.get("start_time", 0)
            if age > max_age:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._candles_counter[key]
    
    def get_stats(self) -> Dict:
        """Получить текущую статистику."""
        # Выполняем периодическую очистку перед получением статистики
        self._cleanup_old_counters()
        
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
        self._candles_counter.clear()
        self._last_cleanup_time = time.time()

