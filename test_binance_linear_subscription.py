"""
Тестовый скрипт для отладки подписки Binance Linear WebSocket
Тестирует 4 WebSocket соединения по 150 подписок в каждом (как в реальном коде)
Показывает все сообщения от Binance в реальном времени
"""
import sys
import os

# Устанавливаем UTF-8 для консоли Windows
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

import ssl
import certifi
import asyncio
import aiohttp
import json
from datetime import datetime
from typing import List
from exchanges.binance.symbol_fetcher import fetch_symbols

# Endpoint для Binance Futures WebSocket
FAPI_WS_ENDPOINT_WS = "wss://fstream.binance.com/ws"

# Параметры теста
STREAMS_PER_CONNECTION = 150  # Количество стримов на одно соединение
NUM_CONNECTIONS = 4  # Количество параллельных соединений
SUBSCRIPTION_TIMEOUT = 60.0  # Таймаут ожидания подтверждения подписки


def format_timestamp():
    """Форматирует текущее время для логов"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _chunk_list(items: List[str], size: int) -> List[List[str]]:
    """Разделить список на чанки."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def print_message(msg_type: str, data: dict, connection_id: int, raw_data: str = None):
    """Красиво выводит сообщение от Binance"""
    print(f"\n{'='*80}")
    print(f"[{format_timestamp()}] [Соединение #{connection_id}] {msg_type}")
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


async def test_single_connection(
    connection_id: int,
    streams: List[str],
    session: aiohttp.ClientSession,
    connection_ready_event: asyncio.Event,
    stop_event: asyncio.Event,
):
    """Тестирует одно WebSocket соединение с заданными стримами"""
    
    stats = {
        "connection_id": connection_id,
        "message_count": 0,
        "subscription_confirmed": False,
        "first_data_received": False,
        "timeout_triggered": False,
        "error_occurred": False,
        "start_time": None,
        "subscription_time": None,
        "first_data_time": None,
    }
    
    try:
        print(f"[{format_timestamp()}] [Соединение #{connection_id}] Подключение к {FAPI_WS_ENDPOINT_WS}...")
        
        async with session.ws_connect(FAPI_WS_ENDPOINT_WS) as ws:
            stats["start_time"] = asyncio.get_event_loop().time()
            print(f"[{format_timestamp()}] [Соединение #{connection_id}] [OK] WebSocket соединение установлено")
            
            # Формируем сообщение подписки
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": streams,
                "id": 1
            }
            
            print(f"[{format_timestamp()}] [Соединение #{connection_id}] Отправка подписки на {len(streams)} стримов...")
            
            await ws.send_json(subscribe_msg)
            stats["subscription_time"] = asyncio.get_event_loop().time()
            print(f"[{format_timestamp()}] [Соединение #{connection_id}] [OK] Сообщение подписки отправлено")
            
            # Сигнализируем, что соединение готово (установлено и подписка отправлена)
            connection_ready_event.set()
            
            # Создаём задачу для проверки таймаута подписки
            timeout_task = None
            
            async def check_subscription_timeout():
                await asyncio.sleep(SUBSCRIPTION_TIMEOUT)
                if not stats["subscription_confirmed"] and not stats["first_data_received"]:
                    stats["timeout_triggered"] = True
                    elapsed = asyncio.get_event_loop().time() - stats["start_time"]
                    print(f"\n{'='*80}")
                    print(f"[{format_timestamp()}] [Соединение #{connection_id}] [WARNING] ТАЙМАУТ ПОДПИСКИ!")
                    print(f"Время ожидания: {SUBSCRIPTION_TIMEOUT}с")
                    print(f"Прошло времени: {elapsed:.1f}с")
                    print(f"Получено сообщений: {stats['message_count']}")
                    print(f"Подписка подтверждена: {stats['subscription_confirmed']}")
                    print(f"Данные получены: {stats['first_data_received']}")
                    print(f"{'='*80}\n")
                    if not ws.closed:
                        await ws.close()
            
            timeout_task = asyncio.create_task(check_subscription_timeout())
            
            try:
                async for msg in ws:
                    # Отменяем задачу таймаута, если получили данные или подтверждение
                    if stats["subscription_confirmed"] or stats["first_data_received"]:
                        if timeout_task and not timeout_task.done():
                            timeout_task.cancel()
                            try:
                                await timeout_task
                            except asyncio.CancelledError:
                                pass
                    
                    # Проверяем флаг остановки
                    if stop_event.is_set():
                        break
                    
                    stats["message_count"] += 1
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            raw_data = msg.data
                            payload = json.loads(raw_data)
                            
                            # Определяем тип сообщения
                            if payload.get("id") == 1:
                                if "error" in payload:
                                    print_message("[ERROR] ОШИБКА ПОДПИСКИ", payload, connection_id, raw_data)
                                    stats["subscription_confirmed"] = False
                                    stats["error_occurred"] = True
                                    # Отменяем таймаут при ошибке
                                    if timeout_task and not timeout_task.done():
                                        timeout_task.cancel()
                                else:
                                    print_message("[OK] ПОДТВЕРЖДЕНИЕ ПОДПИСКИ", payload, connection_id, raw_data)
                                    stats["subscription_confirmed"] = True
                                    elapsed = asyncio.get_event_loop().time() - stats["start_time"]
                                    print(f"[{format_timestamp()}] [Соединение #{connection_id}] Подписка подтверждена через {elapsed:.2f}с")
                                    # Отменяем таймаут при подтверждении
                                    if timeout_task and not timeout_task.done():
                                        timeout_task.cancel()
                            elif payload.get("e") == "continuous_kline":
                                if not stats["first_data_received"]:
                                    print_message("[DATA] ПЕРВОЕ СООБЩЕНИЕ С ДАННЫМИ (continuous_kline)", payload, connection_id, raw_data)
                                    stats["first_data_received"] = True
                                    stats["subscription_confirmed"] = True
                                    stats["first_data_time"] = asyncio.get_event_loop().time()
                                    elapsed = stats["first_data_time"] - stats["start_time"]
                                    print(f"[{format_timestamp()}] [Соединение #{connection_id}] Первые данные получены через {elapsed:.2f}с")
                                    # Отменяем таймаут при получении данных
                                    if timeout_task and not timeout_task.done():
                                        timeout_task.cancel()
                                else:
                                    # Последующие сообщения с данными - показываем только краткую информацию
                                    k = payload.get("k", {})
                                    if stats["message_count"] % 50 == 0:  # Показываем каждое 50-е сообщение
                                        elapsed = asyncio.get_event_loop().time() - stats["start_time"]
                                        print(f"[{format_timestamp()}] [Соединение #{connection_id}] [DATA] Сообщение #{stats['message_count']}: "
                                              f"символ={payload.get('ps')}, закрыта={k.get('x')}, "
                                              f"цена={k.get('c')}, время={elapsed:.1f}с")
                            else:
                                if stats["message_count"] <= 3:  # Показываем первые несколько неизвестных сообщений
                                    print_message(f"[?] НЕИЗВЕСТНОЕ СООБЩЕНИЕ #{stats['message_count']}", payload, connection_id, raw_data)
                            
                            # Статус каждые 50 сообщений
                            if stats["message_count"] % 50 == 0:
                                elapsed = asyncio.get_event_loop().time() - stats["start_time"]
                                print(f"[{format_timestamp()}] [Соединение #{connection_id}] Статус: сообщений={stats['message_count']}, "
                                      f"подтверждено={stats['subscription_confirmed']}, "
                                      f"данные получены={stats['first_data_received']}, "
                                      f"время={elapsed:.1f}с")
                            
                        except json.JSONDecodeError as e:
                            print(f"[{format_timestamp()}] [Соединение #{connection_id}] [ERROR] ОШИБКА парсинга JSON: {e}")
                            print(f"RAW данные: {msg.data[:200]}")
                        except Exception as e:
                            print(f"[{format_timestamp()}] [Соединение #{connection_id}] [ERROR] ОШИБКА обработки сообщения: {e}")
                            print(f"Тип сообщения: {msg.type}")
                    
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        print(f"[{format_timestamp()}] [Соединение #{connection_id}] [CLOSED] WebSocket закрыт сервером")
                        print(f"Код закрытия: {msg.data if hasattr(msg, 'data') else 'N/A'}")
                        break
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"[{format_timestamp()}] [Соединение #{connection_id}] [ERROR] ОШИБКА WebSocket")
                        stats["error_occurred"] = True
                        break
                    
                    elif msg.type == aiohttp.WSMsgType.PING:
                        if stats["message_count"] % 100 == 0:  # Логируем редко
                            print(f"[{format_timestamp()}] [Соединение #{connection_id}] [PING] Получен PING")
                    
                    elif msg.type == aiohttp.WSMsgType.PONG:
                        if stats["message_count"] % 100 == 0:  # Логируем редко
                            print(f"[{format_timestamp()}] [Соединение #{connection_id}] [PONG] Получен PONG")
            
            except KeyboardInterrupt:
                print(f"[{format_timestamp()}] [Соединение #{connection_id}] [STOP] Остановка по запросу пользователя")
            
            finally:
                # Отменяем задачу таймаута в finally, если она ещё активна
                if timeout_task and not timeout_task.done():
                    timeout_task.cancel()
                    try:
                        await timeout_task
                    except asyncio.CancelledError:
                        pass
                
                # Итоговая статистика для этого соединения
                elapsed_total = asyncio.get_event_loop().time() - stats["start_time"] if stats["start_time"] else 0
                print(f"\n{'='*80}")
                print(f"[{format_timestamp()}] [Соединение #{connection_id}] ИТОГОВАЯ СТАТИСТИКА")
                print(f"{'='*80}")
                print(f"Стримов: {len(streams)}")
                print(f"Получено сообщений: {stats['message_count']}")
                print(f"Подписка подтверждена: {stats['subscription_confirmed']}")
                print(f"Данные получены: {stats['first_data_received']}")
                print(f"Таймаут сработал: {stats['timeout_triggered']}")
                print(f"Ошибка: {stats['error_occurred']}")
                if stats["subscription_time"]:
                    print(f"Время до подписки: {stats['subscription_time'] - stats['start_time']:.2f}с")
                if stats["first_data_time"]:
                    print(f"Время до первых данных: {stats['first_data_time'] - stats['start_time']:.2f}с")
                print(f"Время работы: {elapsed_total:.1f} секунд")
                print(f"{'='*80}\n")
    
    except Exception as e:
        stats["error_occurred"] = True
        print(f"[{format_timestamp()}] [Соединение #{connection_id}] [ERROR] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    return stats


async def test_binance_linear_subscription():
    """Тестирует подписку на Binance Linear WebSocket с 4 соединениями по 150 подписок"""
    
    print(f"[{format_timestamp()}] Начало теста подписки Binance Linear")
    print("="*80)
    print(f"Конфигурация: {NUM_CONNECTIONS} соединений по {STREAMS_PER_CONNECTION} стримов в каждом")
    print("="*80)
    
    # Получаем список символов
    print(f"\n[{format_timestamp()}] Получение списка символов...")
    try:
        all_symbols = await fetch_symbols("linear")
        print(f"[{format_timestamp()}] Получено {len(all_symbols)} символов")
        
        if not all_symbols:
            print("ОШИБКА: Не удалось получить символы")
            return
        
        # Берём нужное количество символов для теста (4 соединения * 150 стримов = 600)
        needed_symbols = NUM_CONNECTIONS * STREAMS_PER_CONNECTION
        test_symbols = all_symbols[:needed_symbols]
        print(f"[{format_timestamp()}] Используем {len(test_symbols)} символов для теста")
        
    except Exception as e:
        print(f"ОШИБКА при получении символов: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Формируем стримы для подписки
    all_streams = [f"{sym.lower()}_perpetual@continuousKline_1s" for sym in test_symbols]
    print(f"\n[{format_timestamp()}] Сформировано {len(all_streams)} стримов для подписки")
    
    # Разбиваем на чанки по 150 стримов
    stream_chunks = _chunk_list(all_streams, STREAMS_PER_CONNECTION)
    print(f"[{format_timestamp()}] Разбито на {len(stream_chunks)} чанков:")
    for i, chunk in enumerate(stream_chunks, 1):
        print(f"  Чанк {i}: {len(chunk)} стримов")
        if i == 1:
            print(f"    Примеры: {chunk[:3]}")
    
    # Создаём SSL контекст
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    # Создаём сессию
    session = aiohttp.ClientSession(connector=connector)
    
    # События для синхронизации
    stop_event = asyncio.Event()
    
    try:
        print(f"\n[{format_timestamp()}] Запуск {len(stream_chunks)} соединений последовательно...")
        
        # Запускаем соединения последовательно - каждое должно установиться и отправить подписку
        # перед запуском следующего (как это происходит в основном коде с учетом лимитов)
        tasks = []
        connection_ready_events = []
        
        for i, chunk in enumerate(stream_chunks, 1):
            print(f"[{format_timestamp()}] Запуск соединения #{i}...")
            
            # Создаём событие готовности для этого соединения
            connection_ready = asyncio.Event()
            connection_ready_events.append(connection_ready)
            
            # Создаём задачу для соединения
            task = asyncio.create_task(
                test_single_connection(i, chunk, session, connection_ready, stop_event)
            )
            tasks.append(task)
            
            # Ждём установки соединения и отправки подписки перед запуском следующего
            # Это воспроизводит последовательный запуск как в основном коде
            print(f"[{format_timestamp()}] Ожидание готовности соединения #{i}...")
            try:
                # Ждём до 10 секунд на установку соединения и отправку подписки
                await asyncio.wait_for(connection_ready.wait(), timeout=10.0)
                print(f"[{format_timestamp()}] [OK] Соединение #{i} готово (подключено и подписка отправлена)")
            except asyncio.TimeoutError:
                print(f"[{format_timestamp()}] [WARNING] Таймаут ожидания готовности соединения #{i}")
            
            # Небольшая задержка перед запуском следующего соединения
            if i < len(stream_chunks):
                await asyncio.sleep(0.3)
        
        print(f"\n[{format_timestamp()}] Все {len(stream_chunks)} соединений запущены и готовы к работе")
        
        print(f"\n[{format_timestamp()}] Ожидание данных от Binance...")
        print("(Нажмите Ctrl+C для остановки)\n")
        
        # Ждём завершения всех задач или прерывания
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except KeyboardInterrupt:
            print(f"\n[{format_timestamp()}] [STOP] Остановка по запросу пользователя")
            stop_event.set()
            # Отменяем все задачи
            for task in tasks:
                task.cancel()
            # Ждём отмены
            await asyncio.gather(*tasks, return_exceptions=True)
            results = []
        
        # Итоговая сводная статистика
        print(f"\n{'='*80}")
        print(f"[{format_timestamp()}] СВОДНАЯ СТАТИСТИКА ВСЕХ СОЕДИНЕНИЙ")
        print(f"{'='*80}")
        
        total_messages = 0
        confirmed_count = 0
        data_received_count = 0
        timeout_count = 0
        error_count = 0
        
        for i, result in enumerate(results, 1):
            if isinstance(result, Exception):
                print(f"Соединение #{i}: [ERROR] ИСКЛЮЧЕНИЕ: {result}")
                error_count += 1
            elif isinstance(result, dict):
                total_messages += result.get("message_count", 0)
                if result.get("subscription_confirmed"):
                    confirmed_count += 1
                if result.get("first_data_received"):
                    data_received_count += 1
                if result.get("timeout_triggered"):
                    timeout_count += 1
                if result.get("error_occurred"):
                    error_count += 1
        
        print(f"Всего соединений: {len(stream_chunks)}")
        print(f"Подписки подтверждены: {confirmed_count}/{len(stream_chunks)}")
        print(f"Данные получены: {data_received_count}/{len(stream_chunks)}")
        print(f"Таймауты: {timeout_count}/{len(stream_chunks)}")
        print(f"Ошибки: {error_count}/{len(stream_chunks)}")
        print(f"Всего сообщений получено: {total_messages}")
        print(f"{'='*80}\n")
    
    except Exception as e:
        print(f"\n[{format_timestamp()}] [ERROR] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        stop_event.set()
        await session.close()
        print(f"[{format_timestamp()}] Сессия закрыта")


if __name__ == "__main__":
    print("="*80)
    print("ТЕСТ ПОДПИСКИ BINANCE LINEAR WEBSOCKET")
    print("="*80)
    print(f"Конфигурация: {NUM_CONNECTIONS} соединений по {STREAMS_PER_CONNECTION} стримов")
    print(f"Всего: {NUM_CONNECTIONS * STREAMS_PER_CONNECTION} подписок")
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

