"""
Модуль для замера производительности этапов обработки сигналов
"""
import time
from typing import Dict, Optional
from core.logger import get_logger

logger = get_logger(__name__)

# Маппинг английских названий этапов на русские для отображения в Telegram
STAGE_NAMES_RU = {
    "user.check": "Проверка условий",
    "db.get_user": "Получение данных пользователя",
    "db.save": "Сохранение в БД",
    "format.message": "Форматирование сообщения",
    "chart.fetch": "Получение данных графика",
    "chart.render": "Рендеринг графика",
    "tg.send": "Отправка в Telegram",
    "detect": "Детектирование",
}


class PerformanceTimer:
    """
    Класс для замера времени выполнения ключевых этапов обработки сигнала.
    Используется для мониторинга производительности для пользователя "Влад".
    """
    
    def __init__(self, user_name: str):
        """
        Инициализация таймера.
        
        Args:
            user_name: Имя пользователя (для логирования)
        """
        self.user_name = user_name
        self.metrics: Dict[str, float] = {}
        self._start_times: Dict[str, float] = {}
    
    def start(self, stage: str) -> None:
        """
        Начинает замер времени для этапа.
        
        Args:
            stage: Название этапа (например, "detect", "db.save", "tg.send")
        """
        self._start_times[stage] = time.perf_counter()
    
    def end(self, stage: str) -> None:
        """
        Завершает замер времени для этапа и сохраняет результат.
        
        Args:
            stage: Название этапа
        """
        if stage in self._start_times:
            duration = time.perf_counter() - self._start_times[stage]
            self.metrics[f"{stage}_duration"] = duration * 1000  # в миллисекундах
            del self._start_times[stage]
        else:
            logger.warning(f"Попытка завершить этап '{stage}', который не был начат для {self.user_name}")
    
    def get_summary(self) -> str:
        """
        Форматирует метрики для отправки в Telegram.
        
        Метрики отображаются в определённом порядке этапов:
        - user.check, db.get_user, db.save, format.message, chart.fetch, chart.render, tg.send
        
        В конце строки добавляется общее время (сумма всех этапов).
        
        Returns:
            Отформатированная строка с метриками
        """
        if not self.metrics:
            return "Нет метрик для отображения"
        
        lines = ["📊 <b>Метрики производительности</b>\n"]
        lines.append(f"👤 Пользователь: {self.user_name}\n")
        
        # Порядок этапов для отображения
        stage_order = [
            "user.check",
            "db.get_user",
            "db.save",
            "format.message",
            "chart.fetch",
            "chart.render",
            "tg.send",
        ]
        
        # Добавляем метрики в порядке этапов
        for stage in stage_order:
            key = f"{stage}_duration"
            stage_name_ru = STAGE_NAMES_RU.get(stage, stage)
            
            if key in self.metrics:
                duration_ms = self.metrics[key]
                lines.append(f"⏱ {stage_name_ru}: {duration_ms:.2f}мс")
        
        # Добавляем остальные метрики (если есть)
        processed_keys = set()
        for stage in stage_order:
            key = f"{stage}_duration"
            if key in self.metrics:
                processed_keys.add(key)
        
        for key, value in sorted(self.metrics.items()):
            if key not in processed_keys:
                lines.append(f"⏱ {key}: {value:.2f}мс")
        
        # Вычисляем общее время
        total_duration = sum(
            v for k, v in self.metrics.items() 
            if k.endswith("_duration")
        )
        if total_duration > 0:
            lines.append(f"\n<b>Общее время: {total_duration:.2f}мс</b>")
        
        return "\n".join(lines)
    
    def has_metrics(self) -> bool:
        """
        Проверяет, есть ли собранные метрики.
        
        Returns:
            True если есть метрики, False иначе
        """
        return len(self.metrics) > 0

