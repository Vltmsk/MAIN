"""
Конфигурация приложения
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExchangeToggle:
    """Переключатели включения/выключения бирж и рынков (spot/linear)"""
    # Gate.io
    gate_spot: bool = True
    gate_linear: bool = True
    
    # Binance
    binance_spot: bool = True
    binance_linear: bool = True
    
    # Bitget
    bitget_spot: bool = True
    bitget_linear: bool = True
    
    # Bybit
    bybit_spot: bool = True
    bybit_linear: bool = True
    
    # Hyperliquid
    hyperliquid_spot: bool = True
    hyperliquid_linear: bool = True


@dataclass
class AppConfig:
    """Основная конфигурация приложения"""
    # Максимальное количество свечей в памяти для каждого символа
    memory_max_candles_per_symbol: int = 1000
    
    # Настройки логирования
    log_level: str = "INFO"
    
    # Переключатели бирж
    exchanges: ExchangeToggle = None
    
    # Chat ID для отправки ошибок админу (опционально)
    admin_chat_id: Optional[str] = "-1003153484874"
    admin_bot_token: Optional[str] = "8483602131:AAFcLzlVcGxUfe0vyr-b78-Y1rjrdjyhX-I"
    
    def __post_init__(self):
        """Инициализация после создания dataclass"""
        if self.exchanges is None:
            self.exchanges = ExchangeToggle()


# Глобальный экземпляр конфигурации
config = AppConfig()

