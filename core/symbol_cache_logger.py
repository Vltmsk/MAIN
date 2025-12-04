"""
Централизованное логирование обновлений кэша символов со всех бирж.
Собирает результаты обновлений и выводит одно обобщенное сообщение.
"""
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class UpdateResult:
    """Результат обновления кэша символов для одной биржи и рынка."""
    exchange: str
    market: str
    has_changes: bool
    removed_count: int = 0
    added_count: int = 0
    total_symbols: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class SymbolCacheLogger:
    """Централизованный сборщик результатов обновления кэша символов."""
    
    def __init__(self):
        self._pending_results: Dict[str, UpdateResult] = {}
        self._lock = asyncio.Lock()
        self._summary_task: Optional[asyncio.Task] = None
        self._check_delay = 10  # секунд задержки после последнего обновления перед выводом сводки
        self._last_update_time: Optional[datetime] = None
    
    async def report_update(
        self,
        exchange: str,
        market: str,
        has_changes: bool,
        removed_count: int = 0,
        added_count: int = 0,
        total_symbols: int = 0
    ):
        """
        Сообщить о результате обновления кэша символов.
        
        Args:
            exchange: Название биржи (Binance, Bybit, Gate, Bitget, Hyperliquid)
            market: Тип рынка (spot или linear)
            has_changes: Есть ли изменения в списке символов
            removed_count: Количество удаленных символов
            added_count: Количество добавленных символов
            total_symbols: Общее количество символов
        """
        async with self._lock:
            key = f"{exchange}_{market}"
            result = UpdateResult(
                exchange=exchange,
                market=market,
                has_changes=has_changes,
                removed_count=removed_count,
                added_count=added_count,
                total_symbols=total_symbols
            )
            
            # Если есть изменения, логируем сразу и очищаем ожидающие результаты
            if has_changes:
                logger.info(
                    f"{exchange} {market}: обновлен список символов: "
                    f"{removed_count} удалено, {added_count} добавлено, "
                    f"всего символов: {total_symbols}"
                )
                # Очищаем ожидающие результаты, так как есть изменения
                self._pending_results.clear()
                self._last_update_time = None
                # Отменяем задачу вывода сводки, если она есть
                if self._summary_task and not self._summary_task.done():
                    self._summary_task.cancel()
                self._summary_task = None
                return
            
            # Если изменений нет, сохраняем для обобщенного сообщения
            self._pending_results[key] = result
            self._last_update_time = datetime.now()
            
            # Отменяем предыдущую задачу, если она есть
            if self._summary_task and not self._summary_task.done():
                self._summary_task.cancel()
            
            # Запускаем новую отложенную задачу для проверки и вывода сводки
            self._summary_task = asyncio.create_task(self._delayed_summary_check())
    
    async def _delayed_summary_check(self):
        """Отложенная проверка результатов и вывод обобщенного сообщения."""
        try:
            await asyncio.sleep(self._check_delay)
            
            async with self._lock:
                # Проверяем, что прошло достаточно времени с последнего обновления
                if self._last_update_time:
                    time_since_last = datetime.now() - self._last_update_time
                    if time_since_last < timedelta(seconds=self._check_delay):
                        # Еще не прошло достаточно времени, выходим
                        self._summary_task = None
                        return
                
                # Если есть результаты без изменений, выводим обобщенное сообщение
                if self._pending_results and not any(r.has_changes for r in self._pending_results.values()):
                    logger.info("кэш символов по всем биржам обновлён, изменений нет")
                    self._pending_results.clear()
                    self._last_update_time = None
                
                self._summary_task = None
        except asyncio.CancelledError:
            # Задача была отменена, это нормально
            pass


# Глобальный экземпляр
_cache_logger = SymbolCacheLogger()


async def report_symbol_cache_update(
    exchange: str,
    market: str,
    has_changes: bool,
    removed_count: int = 0,
    added_count: int = 0,
    total_symbols: int = 0
):
    """
    Удобная функция для сообщения о результате обновления кэша символов.
    
    Args:
        exchange: Название биржи
        market: Тип рынка (spot или linear)
        has_changes: Есть ли изменения
        removed_count: Количество удаленных символов
        added_count: Количество добавленных символов
        total_symbols: Общее количество символов
    """
    await _cache_logger.report_update(
        exchange=exchange,
        market=market,
        has_changes=has_changes,
        removed_count=removed_count,
        added_count=added_count,
        total_symbols=total_symbols
    )
