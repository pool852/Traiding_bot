from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from services import get_forecast, generate_signal, safe_generate_explanation, get_support_resistance
from utils import main_menu, markup, user_state, symbols
from bot_init import bot, dp
import logging
import os
from charting import get_ohlcv, generate_chart
from llm_explainer import generate_direction_and_probability, generate_full_forecast
import re

# --- Главное меню ---
def get_main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("📖 Справка по индикаторам"), KeyboardButton("💱 Выбор криптовалюты"))
    return kb

# --- Справка по индикаторам ---
INDICATOR_HELP = {
    "RSI": "RSI (Relative Strength Index) — индикатор силы и направления тренда. Он показывает, перекуплен или перепродан актив: значения выше 70 — перекупленность, ниже 30 — перепроданность. Помогает находить точки разворота и подтверждать тренд.",
    "MACD": "MACD — индикатор, основанный на разнице скользящих средних. Помогает определять силу и направление тренда, а также моменты смены тенденции. Часто используется для поиска точек входа и выхода.",
    "EMA": "EMA (Экспоненциальная скользящая средняя) — сглаживает цену, придавая больший вес последним значениям. EMA(7/50/100) показывают средние цены за разные периоды и помогают видеть краткосрочные и долгосрочные тренды. Пересечения EMA часто сигнализируют о смене тренда.",
    "Stoch RSI": "Stoch RSI — индикатор, объединяющий стохастик и RSI. Он показывает, насколько быстро и сильно меняется RSI, и помогает находить зоны перекупленности и перепроданности. Особенно полезен для поиска краткосрочных разворотов.",
    "Объём": "Объём — это количество сделок за определённый период. Высокий объём подтверждает силу движения цены, а низкий — может указывать на слабость тренда. В боте сравнивается с средним объёмом за 20 свечей для оценки активности рынка.",
}

def get_indicators_help_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    names = list(INDICATOR_HELP.keys())
    for i in range(0, len(names), 3):
        row = [KeyboardButton(name) for name in names[i:i+3]]
        kb.row(*row)
    kb.add(KeyboardButton("⬅️ Назад"))
    return kb

@dp.message_handler(lambda message: message.text == "📖 Справка по индикаторам")
async def show_indicators_help(msg: types.Message):
    await msg.answer("Выберите индикатор:", reply_markup=get_indicators_help_keyboard())

@dp.message_handler(lambda message: message.text in INDICATOR_HELP)
async def show_indicator_info(msg: types.Message):
    ind = msg.text
    text = INDICATOR_HELP.get(ind, "Описание недоступно.")
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("⬅️ К списку индикаторов"))
    await msg.answer(f"<b>{ind}</b>\n{text}", parse_mode="HTML", reply_markup=kb)

@dp.message_handler(lambda message: message.text == "⬅️ К списку индикаторов")
async def back_to_indicators_list(msg: types.Message):
    await msg.answer("Выберите индикатор:", reply_markup=get_indicators_help_keyboard())

@dp.message_handler(lambda message: message.text == "⬅️ Назад")
async def help_back_handler(msg: types.Message):
    await msg.answer("Главное меню:", reply_markup=get_main_menu())

@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    """Обработчик команды /start. Приветствие и вывод главного меню."""
    logging.info(f"[START] Пользователь {msg.from_user.id} начал работу")
    await msg.answer("\U0001F44B Привет! Я бот-прогнозист.\nВыбери действие:", reply_markup=get_main_menu())

@dp.message_handler(commands=['help'])
async def help_command(msg: types.Message):
    """Обработчик команды /help. Выводит инструкцию по использованию бота."""
    await msg.answer("\U0001F4B0 <b>Инструкция:</b>\n1. Выберите монету.\n2. Выберите таймфрейм.\n3. Получите сигнал, объяснение и график.\n\nДля возврата используйте кнопку 'Назад'.", parse_mode="HTML")

def get_symbols_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for i in range(0, len(symbols), 3):
        row = [KeyboardButton(sym) for sym in symbols[i:i+3]]
        kb.row(*row)
    kb.add(KeyboardButton("⬅️ Назад"))
    return kb

def get_timeframes_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("15 минут"), KeyboardButton("1 час"), KeyboardButton("4 часа"))
    kb.row(KeyboardButton("Полный прогноз"), KeyboardButton("⬅️ Назад"))
    return kb

@dp.message_handler(lambda message: message.text == "💱 Выбор криптовалюты")
async def choose_symbol_menu(msg: types.Message):
    await msg.answer("Выберите монету:", reply_markup=get_symbols_keyboard())

@dp.message_handler(lambda message: message.text in symbols)
async def choose_symbol(msg: types.Message):
    symbol = msg.text
    user_state[msg.from_user.id] = symbol
    logging.info(f"[SYMBOL] Пользователь {msg.from_user.id} выбрал {symbol}")
    await msg.answer(f"✅ Вы выбрали: {symbol}\nВыберите таймфрейм:", reply_markup=get_timeframes_keyboard())

@dp.message_handler(lambda message: message.text in ["15 минут", "1 час", "4 часа", "Полный прогноз"])
async def choose_timeframe(msg: types.Message):
    symbol = user_state.get(msg.from_user.id)
    if not symbol:
        await msg.answer("Сначала выберите монету!", reply_markup=get_symbols_keyboard())
        return
    tf_map = {
        "15 минут": "15m",
        "1 час": "1h",
        "4 часа": "4h",
        "Полный прогноз": "full"
    }
    tf = tf_map[msg.text]
    try:
        import time
        user_id = msg.from_user.id
        loader_msg = await msg.answer("⏳ Анализируем... Пожалуйста, подождите", reply_markup=ReplyKeyboardRemove())
        if tf == "full":
            # Получаем данные для всех таймфреймов
            tf_data_15m = get_forecast(symbol, "15m")
            tf_data_1h = get_forecast(symbol, "1h")
            tf_data_4h = get_forecast(symbol, "4h")
            # Получаем вероятности и направления для каждого таймфрейма
            prob_15m = await generate_direction_and_probability(tf_data_15m["indicators"], "15m", symbol)
            prob_1h = await generate_direction_and_probability(tf_data_1h["indicators"], "1h", symbol)
            prob_4h = await generate_direction_and_probability(tf_data_4h["indicators"], "4h", symbol)
            probs = {"15m": prob_15m, "1h": prob_1h, "4h": prob_4h}
            # Получаем уровни поддержки/сопротивления
            df_15m = get_ohlcv(symbol, "15m", limit=300)
            support_15m, resistance_15m = get_support_resistance(df_15m)
            df_1h = get_ohlcv(symbol, "1h", limit=300)
            support_1h, resistance_1h = get_support_resistance(df_1h)
            df_4h = get_ohlcv(symbol, "4h", limit=300)
            support_4h, resistance_4h = get_support_resistance(df_4h)
            # Генерируем графики
            chart_path_15m = generate_chart(symbol, interval_binance="15m", output_path=f"chart_15m_{user_id}_{int(time.time())}.png", levels=[support_15m, resistance_15m])
            chart_path_1h = generate_chart(symbol, interval_binance="1h", output_path=f"chart_1h_{user_id}_{int(time.time())}.png", levels=[support_1h, resistance_1h])
            chart_path_4h = generate_chart(symbol, interval_binance="4h", output_path=f"chart_4h_{user_id}_{int(time.time())}.png", levels=[support_4h, resistance_4h])
            # Новый: один LLM-запрос для всего анализа
            full_forecast = await generate_full_forecast(symbol, tf_data_15m["indicators"], tf_data_1h["indicators"], tf_data_4h["indicators"])
            formatted_forecast = format_full_forecast_text(full_forecast, probs=probs)
            await msg.answer(f"<b>{symbol} — Полный прогноз</b>\n" + formatted_forecast, parse_mode="HTML")
            # Отправляем графики
            if chart_path_15m:
                if os.path.exists(chart_path_15m):
                    with open(chart_path_15m, "rb") as photo:
                        await msg.answer_photo(photo, caption="График 15 минут")
                    try:
                        os.remove(chart_path_15m)
                    except Exception as e:
                        logging.warning(f"[CLEANUP] Не удалось удалить {chart_path_15m}: {e}")
                else:
                    await msg.answer("⚠️ Не удалось построить график 15 минут.")
            if chart_path_1h:
                if os.path.exists(chart_path_1h):
                    with open(chart_path_1h, "rb") as photo:
                        await msg.answer_photo(photo, caption="График 1 час")
                    try:
                        os.remove(chart_path_1h)
                    except Exception as e:
                        logging.warning(f"[CLEANUP] Не удалось удалить {chart_path_1h}: {e}")
                else:
                    await msg.answer("⚠️ Не удалось построить график 1 час.")
            if chart_path_4h:
                if os.path.exists(chart_path_4h):
                    with open(chart_path_4h, "rb") as photo:
                        await msg.answer_photo(photo, caption="График 4 часа")
                    try:
                        os.remove(chart_path_4h)
                    except Exception as e:
                        logging.warning(f"[CLEANUP] Не удалось удалить {chart_path_4h}: {e}")
                else:
                    await msg.answer("⚠️ Не удалось построить график 4 часа.")
        else:
            # Для отдельного таймфрейма логика прежняя
            tf_data = get_forecast(symbol, tf)
            short_comment = await safe_generate_short_comment(tf_data["indicators"], tf, symbol)
            df = get_ohlcv(symbol, tf, limit=300)
            support, resistance = get_support_resistance(df)
            chart_path = generate_chart(symbol, interval_binance=tf, output_path=f"chart_{tf}_{user_id}_{int(time.time())}.png", levels=[support, resistance])
            block = await format_analysis_block(symbol, tf, tf_data["indicators"], short_comment, support, resistance)
            await msg.answer(block, parse_mode="HTML")
            if chart_path:
                if os.path.exists(chart_path):
                    with open(chart_path, "rb") as photo:
                        await msg.answer_photo(photo, caption=f"График {msg.text}")
                    try:
                        os.remove(chart_path)
                    except Exception as e:
                        logging.warning(f"[CLEANUP] Не удалось удалить {chart_path}: {e}")
                else:
                    await msg.answer(f"⚠️ Не удалось построить график {msg.text}.")
        await msg.answer("Выберите таймфрейм:", reply_markup=get_timeframes_keyboard())
    except Exception as e:
        await msg.answer(f"Ошибка анализа: {e}", reply_markup=get_timeframes_keyboard())

@dp.message_handler(lambda message: message.text == "⬅️ Назад")
async def universal_back(msg: types.Message):
    # Определяем, где пользователь: если только что выбирал таймфрейм — возвращаем к монетам, если монеты — в главное меню
    if msg.reply_to_message and msg.reply_to_message.text and "Выберите таймфрейм" in msg.reply_to_message.text:
        await msg.answer("Выберите монету:", reply_markup=get_symbols_keyboard())
    elif msg.reply_to_message and msg.reply_to_message.text and "Выберите монету" in msg.reply_to_message.text:
        await msg.answer("Главное меню:", reply_markup=get_main_menu())
    else:
        # По умолчанию возвращаем главное меню
        await msg.answer("Главное меню:", reply_markup=get_main_menu())

@dp.callback_query_handler(lambda c: c.data.startswith("forecast_"))
async def handle_forecast_query(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    symbol = user_state.get(user_id)
    if not symbol:
        await callback_query.answer("Сначала выберите монету!", show_alert=True)
        return
    try:
        await callback_query.answer()
        tf = callback_query.data  # forecast_15m, forecast_1h, forecast_full
        logging.info(f"[FORECAST] Пользователь {user_id} запросил прогноз по {symbol} ({tf})")
        import time
        if tf == "forecast_15m":
            tf15 = get_forecast(symbol, "15m")
            short_comment_15m = await safe_generate_short_comment(tf15["indicators"], "15m", symbol)
            df_short = get_ohlcv(symbol, "15m", limit=300)
            support, resistance = get_support_resistance(df_short)
            levels = [float(support), float(resistance)]
            chart_path_15m = None
            try:
                chart_path_15m = generate_chart(symbol, interval_binance="15m", output_path=f"chart_15m_{user_id}_{int(time.time())}.png", levels=levels)
            except Exception as e:
                logging.error(f"Ошибка генерации графика: {e}")
            block = await format_analysis_block(symbol, '15m', tf15["indicators"], short_comment_15m, support, resistance)
            await bot.send_message(user_id, block, parse_mode="HTML")
            if chart_path_15m and os.path.exists(chart_path_15m):
                await bot.send_photo(user_id, InputFile(chart_path_15m), caption="📉 График 15m", parse_mode="HTML")
                try:
                    os.remove(chart_path_15m)
                except Exception as e:
                    logging.warning(f"[CLEANUP] Не удалось удалить {chart_path_15m}: {e}")
            elif not chart_path_15m:
                await bot.send_message(user_id, "⚠️ Не удалось построить график.")
        elif tf == "forecast_1h":
            tf1h = get_forecast(symbol, "1h")
            short_comment_1h = await safe_generate_short_comment(tf1h["indicators"], "1h", symbol)
            df_short = get_ohlcv(symbol, "1h", limit=300)
            support, resistance = get_support_resistance(df_short)
            levels = [float(support), float(resistance)]
            chart_path_1h = None
            try:
                chart_path_1h = generate_chart(symbol, interval_binance="1h", output_path=f"chart_1h_{user_id}_{int(time.time())}.png", levels=levels)
            except Exception as e:
                logging.error(f"Ошибка генерации графика: {e}")
            block = await format_analysis_block(symbol, '1h', tf1h["indicators"], short_comment_1h, support, resistance)
            await bot.send_message(user_id, block, parse_mode="HTML")
            if chart_path_1h and os.path.exists(chart_path_1h):
                await bot.send_photo(user_id, InputFile(chart_path_1h), caption="⏰ График 1h", parse_mode="HTML")
                try:
                    os.remove(chart_path_1h)
                except Exception as e:
                    logging.warning(f"[CLEANUP] Не удалось удалить {chart_path_1h}: {e}")
            elif not chart_path_1h:
                await bot.send_message(user_id, "⚠️ Не удалось построить график.")
        elif tf == "forecast_4h":
            tf4h = get_forecast(symbol, "4h")
            short_comment_4h = await safe_generate_short_comment(tf4h["indicators"], "4h", symbol)
            df_short = get_ohlcv(symbol, "4h", limit=300)
            support, resistance = get_support_resistance(df_short)
            levels = [float(support), float(resistance)]
            chart_path_4h = None
            import time
            try:
                chart_path_4h = generate_chart(symbol, interval_binance="4h", output_path=f"chart_4h_{user_id}_{int(time.time())}.png", levels=levels)
            except Exception as e:
                logging.error(f"Ошибка генерации графика: {e}")
            block = await format_analysis_block(symbol, '4h', tf4h["indicators"], short_comment_4h, support, resistance)
            await bot.send_message(user_id, block, parse_mode="HTML")
            if chart_path_4h and os.path.exists(chart_path_4h):
                await bot.send_photo(user_id, InputFile(chart_path_4h), caption="🕓 График 4h", parse_mode="HTML")
                try:
                    os.remove(chart_path_4h)
                except Exception as e:
                    logging.warning(f"[CLEANUP] Не удалось удалить {chart_path_4h}: {e}")
            elif not chart_path_4h:
                await bot.send_message(user_id, "⚠️ Не удалось построить график.")
        else:  # forecast_full
            tf15 = get_forecast(symbol, "15m")
            tf1h = get_forecast(symbol, "1h")
            tf4h = get_forecast(symbol, "4h")
            short_comment_15m = await safe_generate_short_comment(tf15["indicators"], "15m", symbol)
            short_comment_1h = await safe_generate_short_comment(tf1h["indicators"], "1h", symbol)
            short_comment_4h = await safe_generate_short_comment(tf4h["indicators"], "4h", symbol)
            df_15m = get_ohlcv(symbol, "15m", limit=300)
            support_15m, resistance_15m = get_support_resistance(df_15m)
            df_1h = get_ohlcv(symbol, "1h", limit=300)
            support_1h, resistance_1h = get_support_resistance(df_1h)
            df_4h = get_ohlcv(symbol, "4h", limit=300)
            support_4h, resistance_4h = get_support_resistance(df_4h)
            chart_path_15m = None
            chart_path_1h = None
            chart_path_4h = None
            try:
                chart_path_15m = generate_chart(symbol, interval_binance="15m", output_path=f"chart_15m_{user_id}_{int(time.time())}.png", levels=[float(support_15m), float(resistance_15m)])
                chart_path_1h = generate_chart(symbol, interval_binance="1h", output_path=f"chart_1h_{user_id}_{int(time.time())}.png", levels=[float(support_1h), float(resistance_1h)])
                chart_path_4h = generate_chart(symbol, interval_binance="4h", output_path=f"chart_4h_{user_id}_{int(time.time())}.png", levels=[float(support_4h), float(resistance_4h)])
            except Exception as e:
                logging.error(f"Ошибка генерации графиков: {e}")
            blocks = [
                (await format_analysis_block(symbol, '15m', tf15["indicators"], short_comment_15m, support_15m, resistance_15m), chart_path_15m, "📉 График 15m"),
                (await format_analysis_block(symbol, '1h', tf1h["indicators"], short_comment_1h, support_1h, resistance_1h), chart_path_1h, "⏰ График 1h"),
                (await format_analysis_block(symbol, '4h', tf4h["indicators"], short_comment_4h, support_4h, resistance_4h), chart_path_4h, "🕓 График 4h")
            ]
            for block, chart_path, chart_caption in blocks:
                await bot.send_message(user_id, block, parse_mode="HTML")
                if chart_path and os.path.exists(chart_path):
                    await bot.send_photo(user_id, InputFile(chart_path), caption=chart_caption, parse_mode="HTML")
                    try:
                        os.remove(chart_path)
                    except Exception as e:
                        logging.warning(f"[CLEANUP] Не удалось удалить {chart_path}: {e}")
            await bot.send_message(user_id, "💡 <b>Общий вывод:</b>\nПодтверждайте вход сигналом. Не используйте высокое плечо на слабом тренде.", parse_mode="HTML")
        logging.info(f"[FORECAST_SUCCESS] Анализ и графики по {symbol} отправлены пользователю {user_id}")
    except Exception as e:
        if 'insufficient_quota' in str(e):
            await bot.send_message(user_id, "🚫 Ошибка: превышен лимит OpenAI. Пополните баланс или используйте другой ключ.")
        else:
            logging.exception(f"[ERROR] Ошибка при анализе {symbol} для пользователя {user_id}")
            await bot.send_message(user_id, f"🚫 Ошибка при анализе: {e}")

@dp.callback_query_handler(lambda c: c.data == "refresh")
async def handle_refresh(callback_query: types.CallbackQuery):
    """Обработчик inline-кнопки 'Обновить'."""
    user_id = callback_query.from_user.id
    symbol = user_state.get(user_id)
    if not symbol:
        await callback_query.answer("Сначала выберите монету!", show_alert=True)
        return
    await callback_query.answer("Обновляю данные...")
    # Создаем новый callback_query для прогноза
    new_callback = types.CallbackQuery(
        id=callback_query.id,
        from_user=callback_query.from_user,
        chat_instance=callback_query.chat_instance,
        message=callback_query.message,
        data="forecast_15m"
    )
    await handle_forecast_query(new_callback)

def get_bold_header(symbol: str, tf: str) -> str:
    tf_map = {"15m": "15 минут", "1h": "1 час", "4h": "4 часа"}
    return f"<b>Аналитика {symbol} на таймфрейме {tf_map.get(tf, tf)}:</b>"

def ensure_short_comment(explanation: str) -> str:
    if "Краткий вывод:" not in explanation:
        return explanation.strip() + "\nКраткий вывод: —"
    return explanation.strip()

def build_indicators_block(symbol: str, indicators: dict) -> str:
    # Корректно формируем строку EMA(50/100/200)
    def format_ema(val):
        return val if val != "Недостаточно данных" else "Недостаточно данных"
    ema50 = format_ema(indicators.get('EMA50', '-'))
    ema100 = format_ema(indicators.get('EMA100', '-'))
    ema200 = format_ema(indicators.get('EMA200', '-'))
    # Новый блок: объём в USDT
    volume = indicators.get('volume', '-')
    close = indicators.get('close')
    try:
        if volume not in (None, '-', 'Недостаточно данных') and close not in (None, '-', 'Недостаточно данных'):
            volume_usdt = float(volume) * float(close)
            volume_str = f"Trade volume (USDT): {volume_usdt:,.2f}"
        else:
            volume_str = f"Trade volume: {volume}"
    except Exception:
        volume_str = f"Trade volume: {volume}"
    return (
        f"RSI: {indicators.get('RSI', '-')}\n"
        f"MACD: {indicators.get('MACD', '-')}\n"
        f"{volume_str}\n"
        f"Stoch RSI: {indicators.get('StochRSI', '-')}\n"
        f"EMA(50/100/200): {ema50} / {ema100} / {ema200}\n"
        f"Текущий тренд: {indicators.get('trend', '-')}"
    )

async def safe_generate_short_comment(indicators: dict, timeframe: str, symbol: str, max_retries: int = 3, delay: int = 2) -> str:
    from llm_explainer import generate_short_comment
    for attempt in range(max_retries):
        try:
            return await generate_short_comment(indicators, timeframe, symbol)
        except Exception as e:
            import asyncio
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
            else:
                return "—"
    return "—"

async def generate_general_summary(symbol: str, indicators_15m: dict, indicators_1h: dict, indicators_4h: dict) -> str:
    # Получаем прогноз направления и вероятности для каждого таймфрейма через LLM
    pred_15m = await generate_direction_and_probability(indicators_15m, '15m', symbol)
    pred_1h = await generate_direction_and_probability(indicators_1h, '1h', symbol)
    pred_4h = await generate_direction_and_probability(indicators_4h, '4h', symbol)
    # Определяем направление и вероятность для каждого таймфрейма
    def parse_pred(pred):
        if 'ШОРТ' in pred.upper():
            return 'Шорт', int(''.join(filter(str.isdigit, pred))) if any(c.isdigit() for c in pred) else 0
        else:
            return 'Лонг', int(''.join(filter(str.isdigit, pred))) if any(c.isdigit() for c in pred) else 0
    dir_15m, prob_15m = parse_pred(pred_15m)
    dir_1h, prob_1h = parse_pred(pred_1h)
    dir_4h, prob_4h = parse_pred(pred_4h)
    # Формируем строки с эмодзи
    def emoji_line(tf, direction, prob):
        if direction == 'Лонг':
            return f"{tf}: 🟢 ЛОНГ ({prob}%)"
        else:
            return f"{tf}: 🔴 ШОРТ ({prob}%)"
    lines = [
        emoji_line('15м', dir_15m, prob_15m),
        emoji_line('1ч', dir_1h, prob_1h),
        emoji_line('4ч', dir_4h, prob_4h)
    ]
    # Итоговая рекомендация
    long_count = [dir_15m, dir_1h, dir_4h].count('Лонг')
    short_count = [dir_15m, dir_1h, dir_4h].count('Шорт')
    if long_count > short_count:
        rec = "🟢 Преобладает сигнал на ЛОНГ. Можно рассматривать покупки, но учитывайте риски."
    elif short_count > long_count:
        rec = "🔴 Преобладает сигнал на ШОРТ. Можно рассматривать продажи, но учитывайте риски."
    else:
        # Если равенство — по максимальной вероятности
        if max(prob_15m, prob_1h, prob_4h) == prob_15m:
            rec = emoji_line('15м', dir_15m, prob_15m) + ". Сигналы равны, ориентируйтесь на этот таймфрейм."
        elif max(prob_15m, prob_1h, prob_4h) == prob_1h:
            rec = emoji_line('1ч', dir_1h, prob_1h) + ". Сигналы равны, ориентируйтесь на этот таймфрейм."
        else:
            rec = emoji_line('4ч', dir_4h, prob_4h) + ". Сигналы равны, ориентируйтесь на этот таймфрейм."
    return '\n'.join(lines) + '\n' + rec

def generate_trade_recommendation(indicators: dict) -> str:
    """
    Формирует торговую рекомендацию на основе всех индикаторов (включая ATR, SuperTrend, PSAR).
    Возвращает только тело рекомендации (без заголовка и предупреждения).
    """
    prob = indicators.get("probability", 0)
    prob_dir = indicators.get("prob_direction", "Нейтрально")
    leverage = indicators.get("leverage", 5)

    if prob_dir == "Лонг":
        direction_text = "Вверх (лонг)"
    elif prob_dir == "Шорт":
        direction_text = "Вниз (шорт)"
    else:
        direction_text = "Нейтрально"

    rec = f"Вероятность движения: {direction_text} с вероятностью {int(prob)}%\n"
    rec += f"Стоп-лосс: 3%\n"
    rec += f"Тейк-профит: 10%\n"
    rec += f"Кредитное плечо: от 5 до 10"
    return rec

# format_analysis_block — структура: аналитика, индикаторы, краткий вывод, ОДИН заголовок "Торговая рекомендация:", тело рекомендации, ОДНО предупреждение, ссылка

async def format_analysis_block(symbol: str, tf: str, indicators: dict, short_comment: str, support: float, resistance: float) -> str:
    tf_map = {"15m": "15 минут", "1h": "1 час", "4h": "4 часа"}
    # --- Индикаторы ---
    def build_indicators_block(symbol: str, indicators: dict) -> str:
        def format_ema(val):
            return val if val != "Недостаточно данных" else "Недостаточно данных"
        ema50 = format_ema(indicators.get('EMA50', '-'))
        ema100 = format_ema(indicators.get('EMA100', '-'))
        ema200 = format_ema(indicators.get('EMA200', '-'))
        return (
            f"RSI: {indicators.get('RSI', '-')}\n"
            f"MACD: {indicators.get('MACD', '-')}\n"
            f"Trade volume: {indicators.get('volume', '-')}\n"
            f"Stoch RSI: {indicators.get('StochRSI', '-')}\n"
            f"EMA(50/100/200): {ema50} / {ema100} / {ema200}\n"
            f"Текущий тренд: {indicators.get('trend', '-')}"
        )
    indicators_block = build_indicators_block(symbol, indicators)
    short_comment = short_comment.strip()
    # --- Вероятность и направление ---
    prob_block = await generate_direction_and_probability(indicators, tf, symbol)
    import re
    prob_block_upper = prob_block.upper()
    if "ЛОНГ" in prob_block_upper:
        direction = "ЛОНГ"
        emoji = "🟢"
    elif "ШОРТ" in prob_block_upper:
        direction = "ШОРТ"
        emoji = "🔴"
    else:
        direction = "-"
        emoji = "⚪"
    match = re.search(r"(\d{2,3})", prob_block)
    percent = match.group(1) if match else "-"
    probability_line = f"☑️ Сигнал: {emoji} {direction} ({percent}%)"
    stop_loss_block = "⛔️ Стоп-лосс: 3%"
    take_profit_block = "🎯 Тейк-профит: 10%"
    leverage_block = "💸 Кредитное плечо: от 5 до 10"
    # --- Риски ---
    risk_block = "Торговля с плечом и без стоп-лосса может привести к значительным потерям. Используйте рекомендации с осторожностью."
    result = (
        f"<b>📊 Аналитика {symbol} на таймфрейме {tf_map.get(tf, tf)}:</b>\n"
        f"{indicators_block}\n\n"
        f"<b>🟦 Уровни:</b>\nПоддержка: {support}\nСопротивление: {resistance}\n\n"
        f"<b>📝 Краткий вывод:</b>\n{short_comment}\n\n"
        f"<b>📈 Вероятность движения:</b>\n"
        f"{probability_line}\n"
        f"{stop_loss_block}\n"
        f"{take_profit_block}\n"
        f"{leverage_block}\n\n"
        f"<b>⚠️ Риски:</b>\n{risk_block}"
    )
    return result

def format_full_forecast_text(raw: str, probs: dict = None) -> str:
    """
    Форматирует текст полного прогноза от LLM для Telegram (HTML):
    - Выделяет заголовки таймфреймов и общий вывод
    - Жирный шрифт для ключевых блоков
    - Добавляет эмодзи BUY/SELL/HOLD
    - Вставляет разделители между блоками
    - Вставляет отдельный блок индикаторов для каждого таймфрейма (без эмодзи)
    - Подставляет значения вероятности и направления, если переданы через probs
    """
    import re
    def emoji(line):
        if re.search(r'BUY|ПОКУП', line, re.I):
            return '🟢'
        if re.search(r'SELL|ПРОДА', line, re.I):
            return '🔴'
        if re.search(r'HOLD|НЕЙТР', line, re.I):
            return '⚪'
        return ''

    header_map = {
        '15 минут:': '🕒 <b>15 минут:</b>',
        '1 час:': '⏰ <b>1 час:</b>',
        '4 часа:': '🕓 <b>4 часа:</b>',
        'Общий вывод:': '💡 <b>Общий вывод:</b>'
    }
    replacements = [
        (r'^(15 минут:)', header_map['15 минут:']),
        (r'^(1 час:)', header_map['1 час:']),
        (r'^(4 часа:)', header_map['4 часа:']),
        (r'^(Общий вывод:)', header_map['Общий вывод:']),
        (r'\* Краткий вывод:', r'• <b>Краткий вывод:</b>'),
        (r'\* Вероятность и направление:', r'• <b>Вероятность и направление:</b>'),
        (r'\* Основные индикаторы:', r'• <b>Основные индикаторы:</b>'),
    ]
    lines = raw.split('\n')
    out = []
    indicators_block = []
    in_indicators = False
    current_tf = None
    for i, line in enumerate(lines):
        orig = line
        for pat, repl in replacements:
            line = re.sub(pat, repl, line)
        if i > 0 and (line.startswith('🕒') or line.startswith('⏰') or line.startswith('🕓')):
            out.append('<b>──────────────</b>')
        if line.startswith('💡'):
            out.append('<b>══════════════</b>')
        # Определяем текущий таймфрейм для подстановки вероятности
        if line.startswith('🕒'):
            current_tf = '15m'
        elif line.startswith('⏰'):
            current_tf = '1h'
        elif line.startswith('🕓'):
            current_tf = '4h'
        # Подставляем вероятность и направление, если есть
        if '<b>Вероятность и направление:</b>' in line and probs and current_tf in probs:
            prob_line = probs[current_tf]
            em = emoji(prob_line)
            line = f"{em} • <b>Вероятность и направление:</b> {prob_line}"
        elif '<b>Вероятность и направление:</b>' in line:
            em = emoji(line)
            if em and em not in line:
                line = f"{em} {line}"
        if '<b>Краткий вывод:</b>' in line:
            em = emoji(line)
            if em and em not in line:
                line = f"{em} {line}"
        # Индикаторы: ищем значения и выводим в формате 'RSI: значение'
        if '<b>Основные индикаторы:</b>' in line:
            in_indicators = True
            indicators_block = [f'<b>Индикаторы:</b>']
            # Вытаскиваем пары "название: значение"
            # Пример: 'RSI умеренный, MACD немного повышен, ...'
            ind_match = re.findall(r'(RSI [^,]+|MACD [^,]+|Stoch RSI [^,]+|EMA\(50\) [^,]+|MA Summary [^,]+|тенденция [^.,]+)', line)
            for ind in ind_match:
                # Только жирное выделение названий, без эмодзи
                ind = ind.replace('RSI', '<b>RSI</b>:').replace('MACD', '<b>MACD</b>:').replace('Stoch RSI', '<b>Stoch RSI</b>:')
                ind = ind.replace('EMA(50)', '<b>EMA(50)</b>:').replace('MA Summary', '<b>MA Summary</b>:').replace('тенденция', '<b>Тенденция</b>:')
                indicators_block.append(ind.strip())
            continue
        elif in_indicators and (line.strip() == '' or line.startswith('•')):
            if indicators_block:
                out.extend(indicators_block)
                indicators_block = []
            in_indicators = False
        out.append(line)
    if indicators_block:
        out.extend(indicators_block)
    formatted = '\n'.join([l for l in out if l.strip() != ''])
    return formatted

# --- В обработчике полного прогноза ---
# После получения tf_data_15m, tf_data_1h, tf_data_4h:
# Получить вероятности для каждого таймфрейма через generate_direction_and_probability
# probs = { '15m': ..., '1h': ..., '4h': ... }
# formatted_forecast = format_full_forecast_text(full_forecast, probs=probs)

@dp.message_handler()
async def unknown_message(msg: types.Message):
    """Обработчик неизвестных сообщений. Просит выбрать монету или использовать /help."""
    await msg.answer("Пожалуйста, выберите монету из списка или используйте /help.") 