# Практическое руководство по реализации детектора арбитража стейблкоинов

Этот документ содержит практические примеры и рекомендации для реализации детектора арбитража стейблкоинов в проекте.

---

## 1. Структура данных для стейблкоинов

### 1.1. Python структура

Создайте файл `core/stablecoin_config.py`:

```python
"""
Конфигурация стейблкоинов для детектора арбитража
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class StablecoinPriority(Enum):
    HIGHEST = "highest"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LEGACY = "legacy"
    NOT_RECOMMENDED = "not_recommended"

class StablecoinType(Enum):
    USD_STABLE = "usd_stable"
    FIAT_STABLE = "fiat_stable"
    COMMODITY_STABLE = "commodity_stable"
    WRAPPED = "wrapped"
    LST = "lst"

@dataclass
class StablecoinInfo:
    """Информация о стейблкоине"""
    type: StablecoinType
    target: float  # Для USD стейблкоинов = 1.0
    priority: StablecoinPriority
    exchanges: List[str]
    arbitrage_recommended: bool
    status: Optional[str] = None  # "legacy" или None
    comment: Optional[str] = None

# Мапа стейблкоинов
STABLECOIN_MAP: Dict[str, StablecoinInfo] = {
    "USDT": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.HIGHEST,
        exchanges=["binance", "gate", "bybit", "bitget", "hyperliquid"],
        arbitrage_recommended=False,  # Базовая единица
        comment="Базовая единица рынка"
    ),
    "USDC": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.HIGH,
        exchanges=["binance", "gate", "bybit", "bitget", "hyperliquid"],
        arbitrage_recommended=True,
        comment="Высокая ликвидность"
    ),
    "FDUSD": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.HIGH,
        exchanges=["binance"],
        arbitrage_recommended=True,
        comment="Официальный стейбл Binance"
    ),
    "USDP": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.MEDIUM,
        exchanges=["binance"],
        arbitrage_recommended=True,
        comment="Часто бывают арбитражные возможности"
    ),
    "TUSD": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.MEDIUM,
        exchanges=["binance", "gate"],
        arbitrage_recommended=True,
        comment="Ключевая альтернатива BUSD"
    ),
    "DAI": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.MEDIUM,
        exchanges=["binance"],
        arbitrage_recommended=True,
        comment="Децентрализованный стейбл MakerDAO"
    ),
    "XUSD": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.LOW,
        exchanges=["binance"],
        arbitrage_recommended=True,
        comment="USD-стейбл от StraitsX"
    ),
    "USD1": StablecoinInfo(
        type=StablecoinType.USD_STABLE,
        target=1.0,
        priority=StablecoinPriority.LOW,
        exchanges=["binance"],
        arbitrage_recommended=True,
        comment="Новый USD-стейбл под MiCA"
    ),
    # Добавьте остальные стейблкоины по аналогии
}

# Рекомендуемые пороги отклонения (в процентах)
ARBITRAGE_THRESHOLDS = {
    StablecoinPriority.HIGHEST: 0.5,
    StablecoinPriority.HIGH: 1.0,
    StablecoinPriority.MEDIUM: 2.0,
    StablecoinPriority.LOW: 3.0,
}

def get_stablecoin_info(symbol: str) -> Optional[StablecoinInfo]:
    """Получить информацию о стейблкоине по символу"""
    return STABLECOIN_MAP.get(symbol)

def is_stablecoin_pair(symbol: str, quote_currency: str = "USDT") -> bool:
    """
    Проверить, является ли пара стейблкоин-парой
    
    Args:
        symbol: Торговая пара (например, "USDP/USDT" или "USDCUSDT")
        quote_currency: Базовая валюта (обычно "USDT")
    
    Returns:
        True если это стейблкоин-пара, подходящая для арбитража
    """
    # Нормализуем формат пары
    normalized_symbol = symbol.replace("/", "").replace("-", "").upper()
    
    # Извлекаем базовую валюту
    if normalized_symbol.endswith(quote_currency.upper()):
        base_currency = normalized_symbol[:-len(quote_currency.upper())]
    else:
        return False
    
    # Проверяем, является ли базовая валюта стейблкоином
    info = get_stablecoin_info(base_currency)
    if not info:
        return False
    
    # Проверяем, рекомендуется ли для арбитража
    if not info.arbitrage_recommended:
        return False
    
    # Проверяем статус (не legacy)
    if info.status == "legacy":
        return False
    
    return True

def get_recommended_pairs() -> List[str]:
    """Получить список рекомендуемых пар для арбитража"""
    pairs = []
    for symbol, info in STABLECOIN_MAP.items():
        if (info.arbitrage_recommended and 
            info.status != "legacy" and
            info.type == StablecoinType.USD_STABLE):
            pairs.append(f"{symbol}/USDT")
    return pairs
```

---

## 2. Детектор арбитража

### 2.1. Основной класс детектора

Создайте файл `core/stablecoin_arbitrage_detector.py`:

```python
"""
Детектор арбитража стейблкоинов
"""
import asyncio
from typing import Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass
from core.candle_builder import Candle
from core.logger import get_logger
from core.stablecoin_config import (
    get_stablecoin_info,
    is_stablecoin_pair,
    ARBITRAGE_THRESHOLDS,
    StablecoinPriority
)
from BD.database import db

logger = get_logger(__name__)

@dataclass
class ArbitrageAlert:
    """Алерт о возможности арбитража"""
    exchange: str
    market: str
    symbol: str
    current_price: float
    target_price: float
    deviation_pct: float
    timestamp_ms: int
    stablecoin_base: str
    priority: str

class StablecoinArbitrageDetector:
    """Детектор арбитража стейблкоинов"""
    
    def __init__(self):
        self.user_thresholds: Dict[int, float] = {}  # user_id -> threshold
        self.enabled_users: Dict[int, bool] = {}  # user_id -> enabled
    
    async def check_candle(self, candle: Candle, user_id: int) -> Optional[ArbitrageAlert]:
        """
        Проверить свечу на возможность арбитража
        
        Args:
            candle: Свеча с данными
            user_id: ID пользователя
        
        Returns:
            ArbitrageAlert если обнаружена возможность арбитража, иначе None
        """
        # Проверяем, включен ли детектор для пользователя
        if not self.enabled_users.get(user_id, False):
            return None
        
        # Проверяем, является ли пара стейблкоин-парой
        if not is_stablecoin_pair(candle.symbol):
            return None
        
        # Извлекаем базовую валюту из символа
        base_currency = self._extract_base_currency(candle.symbol)
        if not base_currency:
            return None
        
        # Получаем информацию о стейблкоине
        info = get_stablecoin_info(base_currency)
        if not info:
            return None
        
        # Получаем текущую цену (close price свечи)
        current_price = candle.close
        target_price = info.target
        
        # Вычисляем отклонение в процентах
        deviation_pct = abs((current_price - target_price) / target_price) * 100
        
        # Получаем порог для пользователя (или используем рекомендуемый)
        threshold = self.get_user_threshold(user_id, info.priority)
        
        # Проверяем, превышает ли отклонение порог
        if deviation_pct >= threshold:
            logger.info(
                f"Обнаружена возможность арбитража: {candle.exchange} {candle.symbol} "
                f"отклонение {deviation_pct:.2f}% (порог: {threshold}%)"
            )
            
            return ArbitrageAlert(
                exchange=candle.exchange,
                market=candle.market,
                symbol=candle.symbol,
                current_price=current_price,
                target_price=target_price,
                deviation_pct=deviation_pct,
                timestamp_ms=candle.ts_ms,
                stablecoin_base=base_currency,
                priority=info.priority.value
            )
        
        return None
    
    def _extract_base_currency(self, symbol: str) -> Optional[str]:
        """
        Извлечь базовую валюту из символа
        
        Args:
            symbol: Торговая пара (например, "USDP/USDT", "USDCUSDT", "USDC-USDT")
        
        Returns:
            Базовая валюта или None
        """
        # Нормализуем формат
        normalized = symbol.replace("/", "").replace("-", "").upper()
        
        # Убираем USDT в конце
        if normalized.endswith("USDT"):
            base = normalized[:-4]
            return base
        
        return None
    
    def get_user_threshold(self, user_id: int, priority: StablecoinPriority) -> float:
        """
        Получить порог отклонения для пользователя
        
        Args:
            user_id: ID пользователя
            priority: Приоритет стейблкоина
        
        Returns:
            Порог отклонения в процентах
        """
        # Если у пользователя установлен свой порог, используем его
        if user_id in self.user_thresholds:
            return self.user_thresholds[user_id]
        
        # Иначе используем рекомендуемый порог по приоритету
        return ARBITRAGE_THRESHOLDS.get(priority, 2.0)
    
    async def update_user_settings(self, user_id: int, settings: Dict):
        """
        Обновить настройки детектора для пользователя
        
        Args:
            user_id: ID пользователя
            settings: Настройки из options_json
        """
        stablecoin_settings = settings.get("stablecoinArbitrage", {})
        
        # Включен/выключен
        enabled = stablecoin_settings.get("enabled", False)
        self.enabled_users[user_id] = enabled
        
        # Порог отклонения (в процентах)
        threshold = stablecoin_settings.get("threshold")
        if threshold is not None:
            self.user_thresholds[user_id] = float(threshold)
        
        logger.debug(f"Настройки арбитража обновлены для user_id={user_id}: enabled={enabled}, threshold={threshold}")
    
    async def save_alert(self, alert: ArbitrageAlert, user_id: int) -> int:
        """
        Сохранить алерт в БД
        
        Args:
            alert: Алерт о возможности арбитража
            user_id: ID пользователя
        
        Returns:
            ID сохранённого алерта
        """
        # Сохраняем в отдельную таблицу или используем существующую таблицу alerts
        # с дополнительным полем type='stablecoin_arbitrage'
        
        meta = {
            "type": "stablecoin_arbitrage",
            "stablecoin_base": alert.stablecoin_base,
            "target_price": alert.target_price,
            "deviation_pct": alert.deviation_pct,
            "priority": alert.priority
        }
        
        alert_id = await db.add_alert(
            ts=alert.timestamp_ms,
            exchange=alert.exchange,
            market=alert.market,
            symbol=alert.symbol,
            delta=alert.deviation_pct,  # Используем delta для отклонения
            wick_pct=0.0,  # Не применимо для арбитража
            volume_usdt=0.0,  # Можно использовать volume из свечи, если нужно
            meta=str(meta),
            user_id=user_id
        )
        
        return alert_id

# Глобальный экземпляр детектора
stablecoin_arbitrage_detector = StablecoinArbitrageDetector()
```

---

## 3. Интеграция в main.py

### 3.1. Обновление функции on_candle

В `main.py`, в функции `on_candle`, добавьте проверку арбитража:

```python
async def on_candle(candle: Candle) -> None:
    """
    Обработчик завершённых свечей.
    
    Args:
        candle: Завершённая свеча
    """
    # ... существующий код для Bitget ...
    
    metrics.inc_candle(candle.exchange, candle.market)
    
    # Детект стрел для всех пользователей
    try:
        detected_spikes = spike_detector.detect_spike(candle)
        
        if detected_spikes:
            # ... существующая обработка стрел ...
        
        # Детект арбитража стейблкоинов для всех пользователей
        try:
            from core.stablecoin_arbitrage_detector import stablecoin_arbitrage_detector
            
            # Получаем всех пользователей, у которых включен детектор арбитража
            all_users = await db.get_all_users()
            
            for user_data in all_users:
                user_id = user_data["id"]
                user_name = user_data["user"]
                
                # Получаем настройки пользователя
                import json
                options_json = user_data.get("options_json", "{}")
                if options_json:
                    try:
                        options = json.loads(options_json)
                        # Обновляем настройки детектора для пользователя
                        await stablecoin_arbitrage_detector.update_user_settings(user_id, options)
                        
                        # Проверяем свечу на возможность арбитража
                        alert = await stablecoin_arbitrage_detector.check_candle(candle, user_id)
                        
                        if alert:
                            # Сохраняем алерт
                            alert_id = await stablecoin_arbitrage_detector.save_alert(alert, user_id)
                            logger.info(
                                f"Алерт арбитража сохранён для {user_name} "
                                f"({candle.exchange} {candle.symbol}, ID: {alert_id})"
                            )
                            
                            # Отправляем уведомление в Telegram, если настроено
                            tg_token = user_data.get("tg_token", "")
                            chat_id = user_data.get("chat_id", "")
                            
                            if tg_token and chat_id:
                                await _send_arbitrage_notification_async(
                                    alert=alert,
                                    tg_token=tg_token,
                                    chat_id=chat_id,
                                    user_name=user_name
                                )
                    
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"Ошибка при проверке арбитража для {user_name}: {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"Ошибка в детекторе арбитража: {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Ошибка при детекте стрел: {e}", exc_info=True, extra={
            "log_to_db": True,
            "error_type": "spike_detection_error",
            # ...
        })

async def _send_arbitrage_notification_async(
    alert: ArbitrageAlert,
    tg_token: str,
    chat_id: str,
    user_name: str
) -> None:
    """Отправить уведомление об арбитраже в Telegram"""
    try:
        from core.telegram_notifier import telegram_notifier
        
        message = (
            f"💰 <b>АРБИТРАЖ СТЕЙБЛКОИНОВ</b>\n\n"
            f"<b>{alert.exchange.upper()} {alert.market}</b>\n"
            f"📊 <b>{alert.symbol}</b>\n\n"
            f"💵 Текущая цена: <b>{alert.current_price:.6f}</b>\n"
            f"🎯 Целевая цена: <b>{alert.target_price:.6f}</b>\n"
            f"📈 Отклонение: <b>{alert.deviation_pct:.2f}%</b>\n"
            f"⭐ Приоритет: {alert.priority}\n"
        )
        
        success, error_msg = await telegram_notifier.send_message(
            token=tg_token,
            chat_id=chat_id,
            message=message
        )
        
        if success:
            logger.info(f"Уведомление об арбитраже отправлено {user_name}")
        else:
            logger.error(f"Ошибка отправки уведомления {user_name}: {error_msg}")
    
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления об арбитраже: {e}", exc_info=True)
```

---

## 4. База данных

### 4.1. Создание таблицы для арбитража (опционально)

Можно использовать существующую таблицу `alerts` с полем `meta`, или создать отдельную таблицу:

```python
# В BD/database.py
async def create_stablecoin_arbitrage_table():
    """Создать таблицу для алертов арбитража стейблкоинов"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stablecoin_arbitrage_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                stablecoin_base TEXT NOT NULL,
                current_price REAL NOT NULL,
                target_price REAL NOT NULL,
                deviation_pct REAL NOT NULL,
                priority TEXT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        await db.commit()
```

---

## 5. API эндпоинты

### 5.1. Добавление эндпоинтов в api_server.py

```python
# В api_server.py

@app.get("/api/users/{user}/stablecoin-arbitrage/alerts", response_model=dict)
async def get_stablecoin_arbitrage_alerts(
    user: str,
    exchange: Optional[str] = None,
    market: Optional[str] = None,
    ts_from: Optional[int] = None,
    ts_to: Optional[int] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0
):
    """Получить алерты арбитража стейблкоинов для пользователя"""
    try:
        user_data = await db.get_user(user)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_data["id"]
        
        # Фильтруем алерты по типу из meta
        alerts = await db.get_alerts(
            exchange=exchange,
            market=market,
            user_id=user_id,
            ts_from=ts_from,
            ts_to=ts_to,
            limit=limit,
            offset=offset
        )
        
        # Фильтруем только арбитражные алерты
        arbitrage_alerts = []
        for alert in alerts:
            meta = alert.get("meta")
            if meta and "stablecoin_arbitrage" in str(meta):
                arbitrage_alerts.append(alert)
        
        return {"alerts": arbitrage_alerts, "count": len(arbitrage_alerts)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 6. Настройки пользователя в options_json

Пример структуры настроек арбитража в `options_json`:

```json
{
  "stablecoinArbitrage": {
    "enabled": true,
    "threshold": 1.5,
    "pairs": ["USDP/USDT", "USDC/USDT", "FDUSD/USDT"],
    "notifications": {
      "telegram": true
    }
  }
}
```

---

## 7. Веб-интерфейс (Next.js/React)

См. примеры компонентов для настройки арбитража в `WEB/app/(dashboard)/components/StablecoinArbitrageTab.tsx` (нужно создать).

Основные элементы:
- Переключатель включения/выключения
- Настройка порога отклонения (slider или input)
- Выбор отслеживаемых пар
- История алертов
- Статистика по алертам

---

## Резюме

1. **Структура данных:** Используйте `stablecoin_config.py` для хранения информации о стейблкоинах
2. **Детектор:** Реализуйте `StablecoinArbitrageDetector` для проверки свечей
3. **Интеграция:** Добавьте проверку в `on_candle` в `main.py`
4. **БД:** Используйте существующую таблицу `alerts` с метаданными или создайте отдельную
5. **API:** Добавьте эндпоинты для получения алертов
6. **UI:** Создайте вкладку настройки в веб-интерфейсе

---

## Дополнительные рекомендации

- **Оптимизация:** Кэшируйте проверки для часто используемых пар
- **Лимиты:** Учитывайте ограничения WebSocket соединений при подписке на новые пары
- **Уведомления:** Настройте rate limiting для Telegram уведомлений
- **Мониторинг:** Логируйте статистику детектирования арбитража

