"""
Модуль для профилирования производительности и использования памяти
"""
import cProfile
import pstats
import io
import tracemalloc
import time
from typing import Optional, Dict, Any
from functools import wraps
from core.logger import get_logger

logger = get_logger(__name__)


class PerformanceProfiler:
    """Класс для профилирования производительности кода"""
    
    def __init__(self):
        self.profiler: Optional[cProfile.Profile] = None
        self.memory_snapshot: Optional[tracemalloc.Snapshot] = None
        self.start_time: Optional[float] = None
    
    def start_profiling(self):
        """Начинает профилирование CPU"""
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        logger.debug("Профилирование CPU запущено")
    
    def stop_profiling(self) -> str:
        """
        Останавливает профилирование и возвращает статистику
        
        Returns:
            str: Отформатированная статистика профилирования
        """
        if not self.profiler:
            return "Профилирование не было запущено"
        
        self.profiler.disable()
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s)
        ps.sort_stats('cumulative')
        ps.print_stats(20)  # Топ 20 функций
        return s.getvalue()
    
    def start_memory_tracking(self):
        """Начинает отслеживание использования памяти"""
        tracemalloc.start()
        self.memory_snapshot = tracemalloc.take_snapshot()
        logger.debug("Отслеживание памяти запущено")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Получает статистику использования памяти
        
        Returns:
            Dict: Статистика памяти
        """
        if not self.memory_snapshot:
            return {"error": "Отслеживание памяти не было запущено"}
        
        current_snapshot = tracemalloc.take_snapshot()
        top_stats = current_snapshot.compare_to(self.memory_snapshot, 'lineno')
        
        stats = {
            "current_memory_mb": tracemalloc.get_traced_memory()[1] / 1024 / 1024,
            "peak_memory_mb": tracemalloc.get_traced_memory()[0] / 1024 / 1024,
            "top_allocations": []
        }
        
        for stat in top_stats[:10]:
            stats["top_allocations"].append({
                "file": stat.traceback[0].filename if stat.traceback else "unknown",
                "line": stat.traceback[0].lineno if stat.traceback else 0,
                "size_diff_mb": stat.size_diff / 1024 / 1024,
                "count": stat.count_diff
            })
        
        return stats


def profile_function(func):
    """
    Декоратор для профилирования функции
    
    Usage:
        @profile_function
        async def my_function():
            ...
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        profiler = PerformanceProfiler()
        profiler.start_profiling()
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            elapsed = time.time() - start_time
            stats = profiler.stop_profiling()
            logger.debug(f"Функция {func.__name__} выполнена за {elapsed:.3f}с")
            if elapsed > 1.0:  # Логируем только медленные функции
                logger.warning(f"Медленная функция {func.__name__}: {elapsed:.3f}с\n{stats}")
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        profiler = PerformanceProfiler()
        profiler.start_profiling()
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = time.time() - start_time
            stats = profiler.stop_profiling()
            logger.debug(f"Функция {func.__name__} выполнена за {elapsed:.3f}с")
            if elapsed > 1.0:  # Логируем только медленные функции
                logger.warning(f"Медленная функция {func.__name__}: {elapsed:.3f}с\n{stats}")
    
    import inspect
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


# Глобальный экземпляр профилировщика
profiler = PerformanceProfiler()

