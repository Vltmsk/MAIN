"""
Модуль для мониторинга здоровья системы (heartbeat)
"""
import asyncio
import time
import psutil
import os
from typing import Dict, Any, Optional
from core.logger import get_logger

logger = get_logger(__name__)


class HealthMonitor:
    """Мониторинг здоровья системы"""
    
    def __init__(self):
        self.start_time = time.time()
        self.process = psutil.Process(os.getpid())
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 60  # Интервал heartbeat в секундах
        self._monitoring_task: Optional[asyncio.Task] = None
    
    def get_system_health(self) -> Dict[str, Any]:
        """
        Получает текущее состояние здоровья системы
        
        Returns:
            Dict: Статистика системы
        """
        try:
            # Использование памяти процессом
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Использование CPU
            cpu_percent = self.process.cpu_percent(interval=0.1)
            
            # Системная память
            system_memory = psutil.virtual_memory()
            
            # Uptime
            uptime_seconds = time.time() - self.start_time
            
            # Количество открытых файловых дескрипторов
            num_fds = self.process.num_fds() if hasattr(self.process, 'num_fds') else 0
            
            # Количество потоков
            num_threads = self.process.num_threads()
            
            return {
                "status": "healthy",
                "uptime_seconds": int(uptime_seconds),
                "uptime_formatted": self._format_uptime(uptime_seconds),
                "process": {
                    "memory_mb": round(memory_mb, 2),
                    "cpu_percent": round(cpu_percent, 2),
                    "num_threads": num_threads,
                    "num_fds": num_fds,
                },
                "system": {
                    "memory_total_mb": round(system_memory.total / 1024 / 1024, 2),
                    "memory_available_mb": round(system_memory.available / 1024 / 1024, 2),
                    "memory_percent": round(system_memory.percent, 2),
                    "cpu_percent": round(psutil.cpu_percent(interval=0.1), 2),
                },
                "last_heartbeat": self.last_heartbeat,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики здоровья: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": time.time()
            }
    
    def _format_uptime(self, seconds: float) -> str:
        """Форматирует uptime в читаемый вид"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if days > 0:
            return f"{days}д {hours}ч {minutes}м {secs}с"
        elif hours > 0:
            return f"{hours}ч {minutes}м {secs}с"
        elif minutes > 0:
            return f"{minutes}м {secs}с"
        else:
            return f"{secs}с"
    
    async def start_monitoring(self):
        """Запускает периодический мониторинг здоровья системы"""
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("Мониторинг уже запущен")
            return
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Мониторинг здоровья системы запущен")
    
    async def stop_monitoring(self):
        """Останавливает мониторинг"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("Мониторинг здоровья системы остановлен")
    
    async def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                self.last_heartbeat = time.time()
                
                health = self.get_system_health()
                
                # Логируем предупреждения при высоком использовании ресурсов
                if health.get("status") == "healthy":
                    process_memory = health["process"]["memory_mb"]
                    process_cpu = health["process"]["cpu_percent"]
                    system_memory = health["system"]["memory_percent"]
                    
                    # Предупреждение при использовании памяти > 500MB
                    if process_memory > 500:
                        logger.warning(
                            f"Высокое использование памяти процессом: {process_memory:.2f}MB"
                        )
                    
                    # Предупреждение при использовании CPU > 80%
                    if process_cpu > 80:
                        logger.warning(
                            f"Высокое использование CPU процессом: {process_cpu:.2f}%"
                        )
                    
                    # Предупреждение при использовании системной памяти > 90%
                    if system_memory > 90:
                        logger.warning(
                            f"Высокое использование системной памяти: {system_memory:.2f}%"
                        )
                    
                    # Логируем heartbeat каждые 5 минут (300 секунд)
                    if int(time.time()) % 300 < self.heartbeat_interval:
                        logger.info(
                            f"Heartbeat: uptime={health['uptime_formatted']}, "
                            f"memory={process_memory:.2f}MB, cpu={process_cpu:.2f}%"
                        )
        except asyncio.CancelledError:
            logger.debug("Мониторинг остановлен")
            raise
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)


# Глобальный экземпляр монитора здоровья
health_monitor = HealthMonitor()

