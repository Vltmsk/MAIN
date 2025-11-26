"""
Конфигурация приложения
"""
from dataclasses import dataclass


@dataclass
class ExchangeToggle:
    """Переключатели включения/выключения бирж и рынков (spot/linear)"""
    # Gate.io
    gate_spot: bool = False
    gate_linear: bool = False
    
    # Binance
    binance_spot: bool = True
    binance_linear: bool = True
    
    # Bitget
    bitget_spot: bool = False
    bitget_linear: bool = False
    
    # Bybit
    bybit_spot: bool = False
    bybit_linear: bool = False
    
    # Hyperliquid
    hyperliquid_spot: bool = False
    hyperliquid_linear: bool = False


@dataclass
class AppConfig:
    """Основная конфигурация приложения"""
    # Максимальное количество свечей в памяти для каждого символа
    memory_max_candles_per_symbol: int = 1000
    
    # Настройки логирования
    log_level: str = "INFO"
    
    # Переключатели бирж
    exchanges: ExchangeToggle = None
    
    def __post_init__(self):
        """Инициализация после создания dataclass"""
        if self.exchanges is None:
            self.exchanges = ExchangeToggle()


# Глобальный экземпляр конфигурации
config = AppConfig()

