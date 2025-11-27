"""
Тестовый скрипт для отладки подписки Binance Linear WebSocket
Показывает все сообщения от Binance в реальном времени
"""
import ssl
import certifi
import asyncio
import aiohttp
import json
from datetime import datetime
from exchanges.binance.symbol_fetcher import fetch_symbols

# Endpoint для Binance Futures WebSocket
FAPI_WS_ENDPOINT_WS = "wss://fstream.binance.com/ws"

# Количество символов для теста
# Для воспроизведения проблемы используем 100 стримов
TEST_SYMBOLS_COUNT = 100


def format_timestamp():
    """Форматирует текущее время для логов"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def print_message(msg_type: str, data: dict, raw_data: str = None):
    """Красиво выводит сообщение от Binance"""
    print(f"\n{'='*80}")
    print(f"[{format_timestamp()}] {msg_type}")
    print(f"{'='*80}")
    
    if raw_data:
        print(f"RAW JSON (первые 500 символов):")
        print(raw_data[:500])
        if len(raw_data) > 500:
            print(f"... (всего {len(raw_data)} символов)")
        print()
    
    print("Парсированный JSON:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print()
    
    # Анализ структуры сообщения
    print("Анализ структуры:")
    print(f"  - Тип события (e): {data.get('e', 'N/A')}")
    print(f"  - ID сообщения (id): {data.get('id', 'N/A')}")
    print(f"  - Результат (result): {data.get('result', 'N/A')}")
    print(f"  - Ошибка (error): {data.get('error', 'N/A')}")
    print(f"  - Параметры (params): {data.get('params', 'N/A')}")
    
    if 'e' in data:
        event_type = data['e']
        if event_type == 'continuous_kline':
            print(f"  - Символ (ps): {data.get('ps', 'N/A')}")
            print(f"  - Тип контракта (ct): {data.get('ct', 'N/A')}")
            k = data.get('k', {})
            if k:
                print(f"  - Свеча закрыта (x): {k.get('x', 'N/A')}")
                print(f"  - Интервал (i): {k.get('i', 'N/A')}")
    
    print(f"{'='*80}\n")


async def test_binance_linear_subscription():
    """Тестирует подписку на Binance Linear WebSocket"""
    
    print(f"[{format_timestamp()}] Начало теста подписки Binance Linear")
    print("="*80)
    
    # Получаем список символов
    print(f"[{format_timestamp()}] Получение списка символов...")
    try:
        all_symbols = await fetch_symbols("linear")
        print(f"[{format_timestamp()}] Получено {len(all_symbols)} символов")
        
        if not all_symbols:
            print("ОШИБКА: Не удалось получить символы")
            return
        
        # Берём первые несколько символов для теста
        test_symbols = all_symbols[:TEST_SYMBOLS_COUNT]
        print(f"[{format_timestamp()}] Используем {len(test_symbols)} символов для теста:")
        for i, sym in enumerate(test_symbols, 1):
            print(f"  {i}. {sym}")
        
    except Exception as e:
        print(f"ОШИБКА при получении символов: {e}")
        return
    
    # Формируем стримы для подписки
    streams = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in test_symbols]
    print(f"\n[{format_timestamp()}] Сформировано {len(streams)} стримов для подписки")
    print("Примеры стримов:")
    for i, stream in enumerate(streams[:5], 1):
        print(f"  {i}. {stream}")
    if len(streams) > 5:
        print(f"  ... и ещё {len(streams) - 5} стримов")
    
    # Создаём SSL контекст
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    # Создаём сессию
    session = aiohttp.ClientSession(connector=connector)
    
    try:
        print(f"\n[{format_timestamp()}] Подключение к {FAPI_WS_ENDPOINT_WS}...")
        
        async with session.ws_connect(FAPI_WS_ENDPOINT_WS) as ws:
            print(f"[{format_timestamp()}] ✓ WebSocket соединение установлено")
            
            # Формируем сообщение подписки
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": streams,
                "id": 1
            }
            
            print(f"\n[{format_timestamp()}] Отправка подписки...")
            print(f"Сообщение подписки:")
            print(json.dumps(subscribe_msg, indent=2, ensure_ascii=False))
            
            await ws.send_json(subscribe_msg)
            print(f"[{format_timestamp()}] ✓ Сообщение подписки отправлено")
            
            # Ждём ответы от сервера
            print(f"\n[{format_timestamp()}] Ожидание ответов от сервера...")
            print("(Нажмите Ctrl+C для остановки)\n")
            
            message_count = 0
            subscription_confirmed = False
            first_data_received = False
            start_time = asyncio.get_event_loop().time()
            subscription_timeout = 60.0  # Увеличенный таймаут для теста
            timeout_triggered = False
            
            # Создаём задачу для проверки таймаута подписки (как в основном коде)
            async def check_subscription_timeout():
                nonlocal timeout_triggered
                await asyncio.sleep(subscription_timeout)
                if not subscription_confirmed and not first_data_received:
                    timeout_triggered = True
                    current_elapsed = asyncio.get_event_loop().time() - start_time
                    print(f"\n{'='*80}")
                    print(f"[{format_timestamp()}] ⚠️ ТАЙМАУТ ПОДПИСКИ!")
                    print(f"Время ожидания: {subscription_timeout}с")
                    print(f"Прошло времени: {current_elapsed:.1f}с")
                    print(f"Получено сообщений: {message_count}")
                    print(f"Подписка подтверждена: {subscription_confirmed}")
                    print(f"Данные получены: {first_data_received}")
                    print(f"{'='*80}\n")
                    if not ws.closed:
                        await ws.close()
            
            timeout_task = asyncio.create_task(check_subscription_timeout())
            
            try:
                async for msg in ws:
                    # Отменяем задачу таймаута, если получили данные или подтверждение
                    if subscription_confirmed or first_data_received:
                        if not timeout_task.done():
                            timeout_task.cancel()
                            try:
                                await timeout_task
                            except asyncio.CancelledError:
                                pass
                    current_time = asyncio.get_event_loop().time()
                    elapsed = current_time - start_time
                    
                    message_count += 1
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            raw_data = msg.data
                            payload = json.loads(raw_data)
                            
                            # Определяем тип сообщения
                            if payload.get("id") == 1:
                                if "error" in payload:
                                    print_message("❌ ОШИБКА ПОДПИСКИ", payload, raw_data)
                                    subscription_confirmed = False
                                    # Отменяем таймаут при ошибке
                                    if not timeout_task.done():
                                        timeout_task.cancel()
                                else:
                                    print_message("✅ ПОДТВЕРЖДЕНИЕ ПОДПИСКИ", payload, raw_data)
                                    subscription_confirmed = True
                                    # Отменяем таймаут при подтверждении
                                    if not timeout_task.done():
                                        timeout_task.cancel()
                            elif payload.get("e") == "continuous_kline":
                                if not first_data_received:
                                    print_message("📊 ПЕРВОЕ СООБЩЕНИЕ С ДАННЫМИ (continuous_kline)", payload, raw_data)
                                    first_data_received = True
                                    subscription_confirmed = True
                                    # Отменяем таймаут при получении данных
                                    if not timeout_task.done():
                                        timeout_task.cancel()
                                else:
                                    # Последующие сообщения с данными - показываем только краткую информацию
                                    k = payload.get("k", {})
                                    if message_count % 10 == 0:  # Показываем каждое 10-е сообщение
                                        print(f"[{format_timestamp()}] 📊 Сообщение #{message_count} (continuous_kline): "
                                              f"символ={payload.get('ps')}, закрыта={k.get('x')}, "
                                              f"время={k.get('T')}, цена={k.get('c')}")
                            else:
                                print_message(f"❓ НЕИЗВЕСТНОЕ СООБЩЕНИЕ #{message_count}", payload, raw_data)
                            
                            # Статус каждые 10 сообщений
                            if message_count % 10 == 0:
                                print(f"\n[{format_timestamp()}] Статус: сообщений={message_count}, "
                                      f"подтверждено={subscription_confirmed}, "
                                      f"данные получены={first_data_received}, "
                                      f"время с начала={elapsed:.1f}с")
                            
                        except json.JSONDecodeError as e:
                            print(f"\n[{format_timestamp()}] ❌ ОШИБКА парсинга JSON: {e}")
                            print(f"RAW данные: {msg.data[:200]}")
                        except Exception as e:
                            print(f"\n[{format_timestamp()}] ❌ ОШИБКА обработки сообщения: {e}")
                            print(f"Тип сообщения: {msg.type}")
                            print(f"RAW данные: {msg.data[:200] if hasattr(msg, 'data') else 'N/A'}")
                    
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        print(f"\n[{format_timestamp()}] 🔴 WebSocket закрыт сервером")
                        print(f"Код закрытия: {msg.data if hasattr(msg, 'data') else 'N/A'}")
                        print(f"Всего получено сообщений: {message_count}")
                        break
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"\n[{format_timestamp()}] ❌ ОШИБКА WebSocket")
                        print(f"Данные ошибки: {msg.data if hasattr(msg, 'data') else 'N/A'}")
                        break
                    
                    elif msg.type == aiohttp.WSMsgType.PING:
                        print(f"\n[{format_timestamp()}] 🏓 Получен PING от сервера")
                    
                    elif msg.type == aiohttp.WSMsgType.PONG:
                        print(f"\n[{format_timestamp()}] 🏓 Получен PONG от сервера")
                    
                    else:
                        print(f"\n[{format_timestamp()}] ❓ Неизвестный тип сообщения: {msg.type}")
                
            except KeyboardInterrupt:
                print(f"\n[{format_timestamp()}] ⏹ Остановка по запросу пользователя")
                print(f"Всего получено сообщений: {message_count}")
                print(f"Подписка подтверждена: {subscription_confirmed}")
                print(f"Данные получены: {first_data_received}")
            
            finally:
                # Отменяем задачу таймаута в finally, если она ещё активна
                if not timeout_task.done():
                    timeout_task.cancel()
                    try:
                        await timeout_task
                    except asyncio.CancelledError:
                        pass
                
                # Итоговая статистика
                elapsed_total = asyncio.get_event_loop().time() - start_time
                print(f"\n{'='*80}")
                print(f"[{format_timestamp()}] ИТОГОВАЯ СТАТИСТИКА")
                print(f"{'='*80}")
                print(f"Всего получено сообщений: {message_count}")
                print(f"Подписка подтверждена: {subscription_confirmed}")
                print(f"Данные получены: {first_data_received}")
                print(f"Таймаут сработал: {timeout_triggered}")
                print(f"Время работы: {elapsed_total:.1f} секунд")
                print(f"{'='*80}\n")
    
    except Exception as e:
        print(f"\n[{format_timestamp()}] ❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await session.close()
        print(f"[{format_timestamp()}] Сессия закрыта")


if __name__ == "__main__":
    print("="*80)
    print("ТЕСТ ПОДПИСКИ BINANCE LINEAR WEBSOCKET")
    print("="*80)
    print(f"Тестируем подписку на {TEST_SYMBOLS_COUNT} символов")
    print("Скрипт покажет все сообщения от Binance в реальном времени")
    print("="*80)
    print()
    
    try:
        asyncio.run(test_binance_linear_subscription())
    except KeyboardInterrupt:
        print("\n\nТест прерван пользователем")
    except Exception as e:
        print(f"\n\nКРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

