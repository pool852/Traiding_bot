import os
from openai import OpenAI
from dotenv import load_dotenv
import logging
import asyncio

load_dotenv()

client = OpenAI(
    api_key=os.getenv("TOGETHER_API_KEY"),
    base_url="https://api.together.xyz/v1"
)

# Очередь и воркер для Together AI
_together_queue = asyncio.Queue()
TOGETHER_RATE_LIMIT = 1  # 1 запрос в секунду

async def together_worker():
    while True:
        func, args, kwargs, future = await _together_queue.get()
        try:
            result = await func(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
        await asyncio.sleep(1 / TOGETHER_RATE_LIMIT)

asyncio.get_event_loop().create_task(together_worker())

async def together_request(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    await _together_queue.put((func, args, kwargs, future))
    return await future


def translate_timeframe(tf: str) -> str:
    return {
        "15m": "15 минут",
        "1h": "1 час",
        "4h": "4 часа",
        "1d": "1 день"
    }.get(tf, tf)


async def generate_explanation(indicators: dict, timeframe: str, symbol: str = "BTCUSDT") -> str:
    readable_tf = translate_timeframe(timeframe)

    prompt = f"""
Ты — криптовалютный аналитик. Составь краткий и структурированный обзор для трейдера на русском языке по следующему шаблону:

1. Шапка:
📊 {symbol} — {readable_tf}
• Рекомендация: <recommendation>
• Seven days: <SevenDays>
• Итоговый сигнал: <final_signal>
• RSI: <RSI>
• MACD: <MACD>
• Stoch RSI: <StochRSI>
• EMA(9/20/50): <EMA9> / <EMA20> / <EMA50>
• MA Summary: <MA_summary> (<MA_buy> Buy / <MA_sell> Sell)
• Свечные сигналы: <candles>
• Текущий тренд: <trend>

2. После блока с показателями обязательно добавь краткий вывод отдельной строкой (Краткий вывод: ...), 1-2 предложения, только по делу, с акцентом на неопределённость/силу сигнала, если она есть.

Пример:
📊 BTCUSDT — 15 минут
• Рекомендация: SELL
• Seven days: HOLD
• Итоговый сигнал: HOLD
• RSI: 33.23
• MACD: -246.14
• Stoch RSI: 50.21
• EMA(9/20/50): Недостаточно данных / 116973.14 / 117693.61
• MA Summary: STRONG_SELL (0 Buy / 14 Sell)
• Свечные сигналы: —
• Текущий тренд: 📉 Медвежий

Краткий вывод: Нет явного сигнала, рынок в ожидании.

Таймфрейм: {readable_tf}

Индикаторы:
- Итоговый сигнал: {indicators.get('final_signal')}
- Seven days: {indicators.get('SevenDays')}
- Рекомендация: {indicators.get('recommendation')}
- RSI: {indicators.get('RSI')}
- MACD: {indicators.get('MACD')}
- Stoch RSI: {indicators.get('StochRSI')}
- EMA(9): {indicators.get('EMA9')}
- EMA(20): {indicators.get('EMA20')}
- EMA(50): {indicators.get('EMA50')}
- MA Summary: {indicators.get('MA_summary')} (Покупка: {indicators.get('MA_buy')}, Продажа: {indicators.get('MA_sell')})
- Свечные сигналы: {indicators.get('candles')}
- Тренд: {indicators.get('trend')}
"""

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="mistralai/Mixtral-8x7B-Instruct-v0.1",
                messages=[
                    {"role": "system", "content": "Ты эксперт по криптоанализу. Строго следуй шаблону из примера пользователя. После блока с показателями всегда добавляй краткий вывод отдельной строкой (Краткий вывод: ...). Не добавляй лишних пояснений. Пиши только по одному таймфрейму, не добавляй блоки по другим таймфреймам. Пиши на русском."},
                    {"role": "user", "content": prompt.strip()}
                ],
                temperature=0.5,
                max_tokens=600
            )
        )
        content = response.choices[0].message.content
        return content.strip() if content else "⚠️ Ответ от ИИ пустой."

    except Exception as e:
        logging.exception(f"[TOGETHER AI] Ошибка при получении пояснения: {e}")
        return f"⚠️ Не удалось получить пояснение от ИИ (Together AI): {str(e)}"


async def generate_short_comment(indicators: dict, timeframe: str, symbol: str = "BTCUSDT") -> str:
    readable_tf = translate_timeframe(timeframe)
    # Формируем краткий prompt только для вывода
    prompt = f"""
На основе этих индикаторов для {symbol} на таймфрейме {readable_tf} дай краткий вывод (1-2 предложения) для трейдера. Не повторяй показатели, не пиши шапку, только вывод. Пиши только на русском языке, не используй английский, не вставляй англоязычные слова и фразы. Если в индикаторах встречаются английские слова, обязательно переводи их на русский.

Индикаторы:
- Итоговый сигнал: {indicators.get('final_signal')}
- Seven days: {indicators.get('SevenDays')}
- Рекомендация: {indicators.get('recommendation')}
- RSI: {indicators.get('RSI')}
- MACD: {indicators.get('MACD')}
- Stoch RSI: {indicators.get('StochRSI')}
- EMA(9): {indicators.get('EMA9')}
- EMA(20): {indicators.get('EMA20')}
- EMA(50): {indicators.get('EMA50')}
- Объём: {indicators.get('volume')}
- Тренд: {indicators.get('trend')}
"""
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="mistralai/Mixtral-8x7B-Instruct-v0.1",
                messages=[
                    {"role": "system", "content": "Ты эксперт по криптоанализу. Дай только краткий вывод по индикаторам, не повторяй показатели, не пиши шапку, только вывод. Пиши только на русском языке, не используй английский, не вставляй англоязычные слова и фразы. Запрещено использовать английские слова, даже в технических терминах."},
                    {"role": "user", "content": prompt.strip()}
                ],
                temperature=0.5,
                max_tokens=200
            )
        )
        content = response.choices[0].message.content
        return content.strip() if content else "—"
    except Exception as e:
        logging.exception(f"[TOGETHER AI] Ошибка при получении краткого вывода: {e}")
        return "—"


async def generate_direction_and_probability(indicators: dict, timeframe: str, symbol: str = "BTCUSDT") -> str:
    readable_tf = translate_timeframe(timeframe)
    prompt = f"""
На основе этих индикаторов для {symbol} на таймфрейме {readable_tf} оцени, куда с большей вероятностью пойдёт цена (только ЛОНГ или ШОРТ) и укажи процент уверенности (например: ЛОНГ 68%). Не добавляй других пояснений, только направление и процент.

Индикаторы:
- Итоговый сигнал: {indicators.get('final_signal')}
- Seven days: {indicators.get('SevenDays')}
- Рекомендация: {indicators.get('recommendation')}
- RSI: {indicators.get('RSI')}
- MACD: {indicators.get('MACD')}
- Stoch RSI: {indicators.get('StochRSI')}
- EMA(9): {indicators.get('EMA9')}
- EMA(20): {indicators.get('EMA20')}
- EMA(50): {indicators.get('EMA50')}
- MA Summary: {indicators.get('MA_summary')} (Покупка: {indicators.get('MA_buy')}, Продажа: {indicators.get('MA_sell')})
- Свечные сигналы: {indicators.get('candles')}
- Тренд: {indicators.get('trend')}
- Объём: {indicators.get('volume')}
"""
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="mistralai/Mixtral-8x7B-Instruct-v0.1",
                messages=[
                    {"role": "system", "content": "Ты эксперт по криптоанализу. На основе индикаторов оцени только направление (ЛОНГ или ШОРТ) и процент уверенности. Не добавляй других пояснений, только направление и процент. Пиши на русском."},
                    {"role": "user", "content": prompt.strip()}
                ],
                temperature=0.5,
                max_tokens=20
            )
        )
        content = response.choices[0].message.content
        return content.strip() if content else "—"
    except Exception as e:
        logging.exception(f"[TOGETHER AI] Ошибка при получении направления и вероятности: {e}")
        return "—"


def build_full_forecast_prompt(symbol: str, indicators_15m: dict, indicators_1h: dict, indicators_4h: dict) -> str:
    return f"""
Ты — криптовалютный аналитик. На основе индикаторов для {symbol} составь структурированный прогноз по шаблону:

1. Для каждого таймфрейма (15 минут, 1 час, 4 часа):
   - Краткий вывод (1-2 предложения)
   - Вероятность и направление (ЛОНГ/ШОРТ и %)
   - Основные индикаторы (RSI, MACD, Stoch RSI, EMA(9/20/50), MA Summary, Свечные сигналы, Тренд)

2. В конце — общий вывод по всем таймфреймам (1-2 предложения, только по делу, с акцентом на неопределённость/силу сигнала, если она есть).

Данные для анализа:

15 минут:
- Итоговый сигнал: {indicators_15m.get('final_signal')}
- Seven days: {indicators_15m.get('SevenDays')}
- Рекомендация: {indicators_15m.get('recommendation')}
- RSI: {indicators_15m.get('RSI')}
- MACD: {indicators_15m.get('MACD')}
- Stoch RSI: {indicators_15m.get('StochRSI')}
- EMA(9): {indicators_15m.get('EMA9')}
- EMA(20): {indicators_15m.get('EMA20')}
- EMA(50): {indicators_15m.get('EMA50')}
- MA Summary: {indicators_15m.get('MA_summary')} (Покупка: {indicators_15m.get('MA_buy')}, Продажа: {indicators_15m.get('MA_sell')})
- Свечные сигналы: {indicators_15m.get('candles')}
- Тренд: {indicators_15m.get('trend')}

1 час:
- Итоговый сигнал: {indicators_1h.get('final_signal')}
- Seven days: {indicators_1h.get('SevenDays')}
- Рекомендация: {indicators_1h.get('recommendation')}
- RSI: {indicators_1h.get('RSI')}
- MACD: {indicators_1h.get('MACD')}
- Stoch RSI: {indicators_1h.get('StochRSI')}
- EMA(9): {indicators_1h.get('EMA9')}
- EMA(20): {indicators_1h.get('EMA20')}
- EMA(50): {indicators_1h.get('EMA50')}
- MA Summary: {indicators_1h.get('MA_summary')} (Покупка: {indicators_1h.get('MA_buy')}, Продажа: {indicators_1h.get('MA_sell')})
- Свечные сигналы: {indicators_1h.get('candles')}
- Тренд: {indicators_1h.get('trend')}

4 часа:
- Итоговый сигнал: {indicators_4h.get('final_signal')}
- Seven days: {indicators_4h.get('SevenDays')}
- Рекомендация: {indicators_4h.get('recommendation')}
- RSI: {indicators_4h.get('RSI')}
- MACD: {indicators_4h.get('MACD')}
- Stoch RSI: {indicators_4h.get('StochRSI')}
- EMA(9): {indicators_4h.get('EMA9')}
- EMA(20): {indicators_4h.get('EMA20')}
- EMA(50): {indicators_4h.get('EMA50')}
- MA Summary: {indicators_4h.get('MA_summary')} (Покупка: {indicators_4h.get('MA_buy')}, Продажа: {indicators_4h.get('MA_sell')})
- Свечные сигналы: {indicators_4h.get('candles')}
- Тренд: {indicators_4h.get('trend')}
"""

async def generate_full_forecast(symbol: str, indicators_15m: dict, indicators_1h: dict, indicators_4h: dict) -> str:
    prompt = build_full_forecast_prompt(symbol, indicators_15m, indicators_1h, indicators_4h)
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="mistralai/Mixtral-8x7B-Instruct-v0.1",
                messages=[
                    {"role": "system", "content": "Ты эксперт по криптоанализу. Строго следуй шаблону. Для каждого таймфрейма дай краткий вывод, вероятность и направление, индикаторы. В конце — общий вывод. Пиши только на русском языке, не используй английский, не вставляй англоязычные слова и фразы."},
                    {"role": "user", "content": prompt.strip()}
                ],
                temperature=0.5,
                max_tokens=900
            )
        )
        content = response.choices[0].message.content
        return content.strip() if content else "⚠️ Ответ от ИИ пустой."
    except Exception as e:
        logging.exception(f"[TOGETHER AI] Ошибка при получении полного прогноза: {e}")
        return f"⚠️ Не удалось получить полный прогноз от ИИ (Together AI): {str(e)}"
