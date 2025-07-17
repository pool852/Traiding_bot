#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функций бота
"""

import os
import sys
from dotenv import load_dotenv

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Тестирует импорты всех модулей"""
    print("🔍 Тестирование импортов...")
    
    try:
        from tradingview_ta import TA_Handler, Interval
        print("✅ tradingview_ta импортирован успешно")
    except ImportError as e:
        print(f"❌ Ошибка импорта tradingview_ta: {e}")
        return False
    
    try:
        from llm_explainer import generate_explanation
        print("✅ llm_explainer импортирован успешно")
    except ImportError as e:
        print(f"❌ Ошибка импорта llm_explainer: {e}")
        return False
    
    try:
        from charting import generate_chart
        print("✅ charting импортирован успешно")
    except ImportError as e:
        print(f"❌ Ошибка импорта charting: {e}")
        return False
    
    return True

def test_tradingview():
    """Тестирует подключение к TradingView"""
    print("\n📊 Тестирование TradingView...")
    
    try:
        from tradingview_ta import TA_Handler, Interval
        
        handler = TA_Handler(
            symbol="BTCUSDT",
            screener="crypto",
            exchange="BINANCE",
            interval=Interval.INTERVAL_15_MINUTES
        )
        
        analysis = handler.get_analysis()
        if analysis:
            print("✅ TradingView API работает")
            print(f"   Рекомендация: {analysis.summary.get('RECOMMENDATION', 'N/A')}")
            return True
        else:
            print("❌ TradingView вернул пустой анализ")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка TradingView: {e}")
        return False

def test_charting():
    """Тестирует генерацию графиков"""
    print("\n📈 Тестирование генерации графиков...")
    
    try:
        from charting import generate_chart
        
        # Тестируем с BTCUSDT
        chart_path = generate_chart("BTCUSDT", interval_binance="15m", output_path="test_chart.png")
        
        if os.path.exists(chart_path):
            print(f"✅ График создан: {chart_path}")
            # Удаляем тестовый файл
            os.remove(chart_path)
            return True
        else:
            print("❌ График не создан")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка генерации графика: {e}")
        return False

def test_llm():
    """Тестирует LLM объяснения"""
    print("\n🤖 Тестирование LLM...")
    
    try:
        from llm_explainer import generate_explanation
        
        # Тестовые данные
        test_indicators = {
            "recommendation": "BUY",
            "RSI": "45.2",
            "MACD": "0.15",
            "StochRSI": "65.8",
            "EMA9": "50000",
            "EMA20": "49500",
            "EMA50": "49000",
            "MA_summary": "BUY",
            "MA_buy": 8,
            "MA_sell": 3,
            "candles": "Doji",
            "trend": "📈 Бычий"
        }
        
        explanation = await generate_explanation(test_indicators, "15m")
        if explanation and len(explanation) > 10:
            print("✅ LLM работает")
            print(f"   Объяснение: {explanation[:100]}...")
            return True
        else:
            print("❌ LLM вернул пустое объяснение")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка LLM: {e}")
        return False

def test_env():
    """Тестирует переменные окружения"""
    print("\n🔧 Тестирование переменных окружения...")
    
    load_dotenv()
    
    bot_token = os.getenv("BOT_TOKEN")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if bot_token:
        print("✅ BOT_TOKEN найден")
    else:
        print("❌ BOT_TOKEN не найден")
    
    if openai_key:
        print("✅ OPENAI_API_KEY найден")
    else:
        print("❌ OPENAI_API_KEY не найден")
    
    return bool(bot_token and openai_key)

async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования бота...\n")
    
    tests = [
        ("Импорты", test_imports),
        ("Переменные окружения", test_env),
        ("TradingView", test_tradingview),
        ("Графики", test_charting),
        ("LLM", test_llm),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Ошибка в тесте {test_name}: {e}")
            results.append((test_name, False))
    
    # Итоговый отчет
    print("\n" + "="*50)
    print("📋 ИТОГОВЫЙ ОТЧЕТ")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nРезультат: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены! Бот готов к работе.")
    else:
        print("⚠️  Некоторые тесты провалены. Проверьте настройки.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 