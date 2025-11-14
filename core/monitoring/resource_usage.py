"""
Модуль для мониторинга использования ресурсов системы (CPU, память, I/O, сеть, диск)
Используется для тестирования пиковой нагрузки и оценки требований к серверу
"""
import psutil
import time
import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from core.logger import get_logger
from BD.database import db

logger = get_logger(__name__)


class ResourceMonitor:
    """Класс для мониторинга использования ресурсов системы"""
    
    def __init__(self, save_to_db: bool = True, enable_file_saving: bool = True, output_dir: Path = None):
        """
        Инициализация монитора ресурсов
        
        Args:
            save_to_db: Сохранять ли метрики в БД
            enable_file_saving: Сохранять ли метрики в файл
            output_dir: Директория для сохранения файлов с метриками
        """
        self.save_to_db = save_to_db
        self.enable_file_saving = enable_file_saving
        self.output_dir = output_dir or Path("tests/performance/metrics")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.process = psutil.Process()
        self.metrics_history: List[Dict[str, Any]] = []
        self.start_time = time.time()
        self.test_name: Optional[str] = None
        
    def start_test(self, test_name: str):
        """
        Начать новый тест
        
        Args:
            test_name: Название теста (например, "peak_load_5min")
        """
        self.test_name = test_name
        self.start_time = time.time()
        self.metrics_history.clear()
        logger.info(f"Начат тест: {test_name}")
        
    def collect_metrics(self) -> Dict[str, Any]:
        """
        Собрать текущие метрики системы
        
        Returns:
            Dict: Словарь с метриками
        """
        timestamp = time.time()
        elapsed = timestamp - self.start_time
        
        try:
            # Метрики процесса
            process_memory = self.process.memory_info()
            process_cpu = self.process.cpu_percent(interval=0.1)
            process_threads = self.process.num_threads()
            process_fds = self.process.num_fds() if hasattr(self.process, 'num_fds') else 0
            
            # Системные метрики CPU
            cpu_percent_per_core = psutil.cpu_percent(percpu=True, interval=0.1)
            cpu_percent_total = psutil.cpu_percent(interval=0.1)
            cpu_count_physical = psutil.cpu_count(logical=False)
            cpu_count_logical = psutil.cpu_count(logical=True)
            
            # Метрики памяти
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Метрики диска
            disk_usage = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            # Метрики сети
            net_io = psutil.net_io_counters()
            
            # Метрики I/O процесса
            process_io = self.process.io_counters() if hasattr(self.process, 'io_counters') else None
            
            metrics = {
                "timestamp": timestamp,
                "elapsed_seconds": round(elapsed, 2),
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                
                # Процесс
                "process": {
                    "memory_rss_mb": round(process_memory.rss / 1024 / 1024, 2),
                    "memory_vms_mb": round(process_memory.vms / 1024 / 1024, 2),
                    "memory_percent": round(self.process.memory_percent(), 2),
                    "cpu_percent": round(process_cpu, 2),
                    "num_threads": process_threads,
                    "num_fds": process_fds,
                },
                
                # CPU система
                "cpu": {
                    "total_percent": round(cpu_percent_total, 2),
                    "per_core_percent": [round(c, 2) for c in cpu_percent_per_core],
                    "count_physical": cpu_count_physical,
                    "count_logical": cpu_count_logical,
                    "freq_current_mhz": round(psutil.cpu_freq().current, 2) if psutil.cpu_freq() else None,
                },
                
                # Память система
                "memory": {
                    "total_gb": round(memory.total / 1024 / 1024 / 1024, 2),
                    "available_gb": round(memory.available / 1024 / 1024 / 1024, 2),
                    "used_gb": round(memory.used / 1024 / 1024 / 1024, 2),
                    "percent": round(memory.percent, 2),
                },
                
                # Swap
                "swap": {
                    "total_gb": round(swap.total / 1024 / 1024 / 1024, 2) if swap.total > 0 else 0,
                    "used_gb": round(swap.used / 1024 / 1024 / 1024, 2) if swap.used > 0 else 0,
                    "percent": round(swap.percent, 2) if swap.total > 0 else 0,
                },
                
                # Диск
                "disk": {
                    "total_gb": round(disk_usage.total / 1024 / 1024 / 1024, 2),
                    "used_gb": round(disk_usage.used / 1024 / 1024 / 1024, 2),
                    "free_gb": round(disk_usage.free / 1024 / 1024 / 1024, 2),
                    "percent": round(disk_usage.percent, 2),
                },
                
                # Диск I/O
                "disk_io": {
                    "read_bytes": disk_io.read_bytes if disk_io else 0,
                    "write_bytes": disk_io.write_bytes if disk_io else 0,
                    "read_count": disk_io.read_count if disk_io else 0,
                    "write_count": disk_io.write_count if disk_io else 0,
                } if disk_io else {},
                
                # Сеть
                "network": {
                    "bytes_sent": net_io.bytes_sent if net_io else 0,
                    "bytes_recv": net_io.bytes_recv if net_io else 0,
                    "packets_sent": net_io.packets_sent if net_io else 0,
                    "packets_recv": net_io.packets_recv if net_io else 0,
                } if net_io else {},
                
                # I/O процесса
                "process_io": {
                    "read_bytes": process_io.read_bytes if process_io else 0,
                    "write_bytes": process_io.write_bytes if process_io else 0,
                    "read_count": process_io.read_count if process_io else 0,
                    "write_count": process_io.write_count if process_io else 0,
                } if process_io else {},
            }
            
            # Сохраняем в историю
            self.metrics_history.append(metrics)
            
            # Сохраняем в БД, если включено
            if self.save_to_db:
                self._save_to_db(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик: {e}", exc_info=True)
            return {"error": str(e), "timestamp": timestamp}
    
    def _save_to_db(self, metrics: Dict[str, Any]):
        """Сохранить метрики в БД"""
        try:
            # Проверяем, есть ли таблица для метрик
            conn = db._get_connection()
            cursor = conn.cursor()
            
            # Создаём таблицу для метрик, если её нет
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    datetime TEXT NOT NULL,
                    elapsed_seconds REAL,
                    process_memory_rss_mb REAL,
                    process_memory_vms_mb REAL,
                    process_memory_percent REAL,
                    process_cpu_percent REAL,
                    process_num_threads INTEGER,
                    process_num_fds INTEGER,
                    cpu_total_percent REAL,
                    cpu_count_physical INTEGER,
                    cpu_count_logical INTEGER,
                    memory_total_gb REAL,
                    memory_available_gb REAL,
                    memory_used_gb REAL,
                    memory_percent REAL,
                    swap_total_gb REAL,
                    swap_used_gb REAL,
                    swap_percent REAL,
                    disk_total_gb REAL,
                    disk_used_gb REAL,
                    disk_free_gb REAL,
                    disk_percent REAL,
                    disk_read_bytes INTEGER,
                    disk_write_bytes INTEGER,
                    network_bytes_sent INTEGER,
                    network_bytes_recv INTEGER,
                    process_read_bytes INTEGER,
                    process_write_bytes INTEGER,
                    metrics_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Создаём индекс для быстрого поиска по тесту и времени
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_performance_metrics_test_time 
                ON performance_metrics(test_name, timestamp)
            """)
            
            # Вставляем метрики
            cursor.execute("""
                INSERT INTO performance_metrics (
                    test_name, timestamp, datetime, elapsed_seconds,
                    process_memory_rss_mb, process_memory_vms_mb, process_memory_percent,
                    process_cpu_percent, process_num_threads, process_num_fds,
                    cpu_total_percent, cpu_count_physical, cpu_count_logical,
                    memory_total_gb, memory_available_gb, memory_used_gb, memory_percent,
                    swap_total_gb, swap_used_gb, swap_percent,
                    disk_total_gb, disk_used_gb, disk_free_gb, disk_percent,
                    disk_read_bytes, disk_write_bytes,
                    network_bytes_sent, network_bytes_recv,
                    process_read_bytes, process_write_bytes,
                    metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.test_name,
                metrics["timestamp"],
                metrics["datetime"],
                metrics["elapsed_seconds"],
                metrics["process"]["memory_rss_mb"],
                metrics["process"]["memory_vms_mb"],
                metrics["process"]["memory_percent"],
                metrics["process"]["cpu_percent"],
                metrics["process"]["num_threads"],
                metrics["process"]["num_fds"],
                metrics["cpu"]["total_percent"],
                metrics["cpu"]["count_physical"],
                metrics["cpu"]["count_logical"],
                metrics["memory"]["total_gb"],
                metrics["memory"]["available_gb"],
                metrics["memory"]["used_gb"],
                metrics["memory"]["percent"],
                metrics["swap"]["total_gb"],
                metrics["swap"]["used_gb"],
                metrics["swap"]["percent"],
                metrics["disk"]["total_gb"],
                metrics["disk"]["used_gb"],
                metrics["disk"]["free_gb"],
                metrics["disk"]["percent"],
                metrics["disk_io"].get("read_bytes", 0),
                metrics["disk_io"].get("write_bytes", 0),
                metrics["network"].get("bytes_sent", 0),
                metrics["network"].get("bytes_recv", 0),
                metrics["process_io"].get("read_bytes", 0),
                metrics["process_io"].get("write_bytes", 0),
                json.dumps(metrics)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении метрик в БД: {e}", exc_info=True)
    
    def save_to_file(self, format: str = "json") -> Path:
        """
        Сохранить собранные метрики в файл
        
        Args:
            format: Формат файла ("json" или "csv")
            
        Returns:
            Path: Путь к сохранённому файлу
        """
        if not self.metrics_history:
            logger.warning("Нет метрик для сохранения")
            return None
        
        timestamp_str = datetime.fromtimestamp(self.start_time).strftime("%Y%m%d_%H%M%S")
        test_name_safe = self.test_name.replace(" ", "_").replace("/", "-") if self.test_name else "test"
        filename = f"{test_name_safe}_{timestamp_str}.{format}"
        filepath = self.output_dir / filename
        
        try:
            if format == "json":
                # Сохраняем как JSON
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump({
                        "test_name": self.test_name,
                        "start_time": self.start_time,
                        "start_datetime": datetime.fromtimestamp(self.start_time).isoformat(),
                        "end_time": time.time(),
                        "end_datetime": datetime.fromtimestamp(time.time()).isoformat(),
                        "duration_seconds": time.time() - self.start_time,
                        "metrics_count": len(self.metrics_history),
                        "metrics": self.metrics_history
                    }, f, indent=2, ensure_ascii=False)
                    
            elif format == "csv":
                # Сохраняем как CSV
                if not self.metrics_history:
                    return None
                
                # Определяем все ключи для CSV
                fieldnames = ["timestamp", "datetime", "elapsed_seconds"]
                
                # Добавляем все поля из метрик
                sample = self.metrics_history[0]
                for key in sample.keys():
                    if key not in ["timestamp", "datetime", "elapsed_seconds"]:
                        if isinstance(sample[key], dict):
                            for subkey in sample[key].keys():
                                fieldnames.append(f"{key}_{subkey}")
                        else:
                            fieldnames.append(key)
                
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for metrics in self.metrics_history:
                        row = {
                            "timestamp": metrics["timestamp"],
                            "datetime": metrics["datetime"],
                            "elapsed_seconds": metrics["elapsed_seconds"],
                        }
                        
                        # Разворачиваем вложенные словари
                        for key, value in metrics.items():
                            if key not in ["timestamp", "datetime", "elapsed_seconds"]:
                                if isinstance(value, dict):
                                    for subkey, subvalue in value.items():
                                        if isinstance(subvalue, list):
                                            row[f"{key}_{subkey}"] = ",".join(map(str, subvalue))
                                        else:
                                            row[f"{key}_{subkey}"] = subvalue
                                elif isinstance(value, list):
                                    row[key] = ",".join(map(str, value))
                                else:
                                    row[key] = value
                        
                        writer.writerow(row)
            
            logger.info(f"Метрики сохранены в файл: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении метрик в файл: {e}", exc_info=True)
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Получить статистику по собранным метрикам
        
        Returns:
            Dict: Статистика (мин, макс, среднее, медиана)
        """
        if not self.metrics_history:
            return {"error": "Нет собранных метрик"}
        
        # Извлекаем числовые значения
        def extract_values(key_path: str) -> List[float]:
            """Извлечь значения по пути ключа (например, 'process.cpu_percent')"""
            values = []
            for metrics in self.metrics_history:
                keys = key_path.split('.')
                value = metrics
                try:
                    for k in keys:
                        value = value[k]
                    if isinstance(value, (int, float)):
                        values.append(float(value))
                except (KeyError, TypeError):
                    pass
            return values
        
        stats = {
            "test_name": self.test_name,
            "duration_seconds": time.time() - self.start_time,
            "metrics_count": len(self.metrics_history),
        }
        
        # Метрики для анализа
        metrics_to_analyze = [
            ("process.cpu_percent", "CPU процесса (%)"),
            ("process.memory_rss_mb", "Память процесса RSS (MB)"),
            ("process.memory_percent", "Память процесса (%)"),
            ("cpu.total_percent", "CPU системы (%)"),
            ("memory.percent", "Память системы (%)"),
            ("disk.percent", "Диск (%)"),
        ]
        
        for key_path, label in metrics_to_analyze:
            values = extract_values(key_path)
            if values:
                stats[label] = {
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "avg": round(sum(values) / len(values), 2),
                    "median": round(sorted(values)[len(values) // 2], 2),
                }
        
        return stats
    
    def print_statistics(self):
        """Вывести статистику в консоль"""
        stats = self.get_statistics()
        
        if "error" in stats:
            logger.warning(stats["error"])
            return
        
        logger.info("=" * 60)
        logger.info(f"Статистика теста: {stats['test_name']}")
        logger.info(f"Длительность: {stats['duration_seconds']:.2f} секунд")
        logger.info(f"Количество собранных метрик: {stats['metrics_count']}")
        logger.info("-" * 60)
        
        for key, value in stats.items():
            if key not in ["test_name", "duration_seconds", "metrics_count"] and isinstance(value, dict):
                logger.info(f"{key}:")
                logger.info(f"  Мин: {value['min']}, Макс: {value['max']}, Среднее: {value['avg']}, Медиана: {value['median']}")
        
        logger.info("=" * 60)


# Глобальный экземпляр монитора
resource_monitor = ResourceMonitor()

