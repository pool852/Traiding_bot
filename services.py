import logging
from tradingview_ta import TA_Handler, Interval
from llm_explainer import generate_explanation
import pandas as pd
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    logging.warning("pandas_ta не установлен — ATR, SuperTrend, PSAR не будут рассчитываться!")
    PANDAS_TA_AVAILABLE = False
from typing import Dict, Any, Tuple, Optional
from utils import format_float
import asyncio
import numpy as np

def safe_float(val):
    try:
        if val in (None, "-", "Недостаточно данных"): return None
        return float(val)
    except Exception:
        return None

def safe_scalar_float(val):
    import numpy as np
    if np.isscalar(val) and isinstance(val, (int, float, np.floating)) and not isinstance(val, (bool, complex, str)):
        try:
            return float(val)
        except Exception:
            return None
    return None

def get_seven_days_signal(symbol: str, interval: str) -> str:
    """
    Заглушка для индикатора Seven days. Здесь должна быть ваша логика.
    Возвращает 'BUY', 'SELL' или 'HOLD'.
    """
    # TODO: Реализовать реальную логику!
    return "HOLD"

def majority_vote_signal(indicators: dict) -> str:
    votes = []

    # RSI
    try:
        rsi = float(indicators.get('RSI', 0))
        if rsi < 30:
            votes.append('BUY')
        elif rsi > 70:
            votes.append('SELL')
        else:
            votes.append('HOLD')
    except Exception:
        pass

    # MACD
    try:
        macd = float(indicators.get('MACD', 0))
        if macd > 0:
            votes.append('BUY')
        elif macd < 0:
            votes.append('SELL')
        else:
            votes.append('HOLD')
    except Exception:
        pass

    # MA Summary
    ma_summary = indicators.get('MA_summary')
    if ma_summary == 'BUY':
        votes.append('BUY')
    elif ma_summary == 'SELL':
        votes.append('SELL')
    else:
        votes.append('HOLD')

    # Объём: если объём выше среднего за 20 свечей — голос за направление RSI, иначе HOLD
    try:
        volume = float(indicators.get('volume', 0))
        avg_volume = float(indicators.get('avg_volume', 0))
        if avg_volume > 0:
            if volume > avg_volume:
                # Голос за направление RSI
                if rsi < 30:
                    votes.append('BUY')
                elif rsi > 70:
                    votes.append('SELL')
                else:
                    votes.append('HOLD')
            else:
                votes.append('HOLD')
    except Exception:
        pass

    # Подсчёт голосов
    buy = votes.count('BUY')
    sell = votes.count('SELL')
    hold = votes.count('HOLD')

    if buy > max(sell, hold):
        return 'BUY'
    elif sell > max(buy, hold):
        return 'SELL'
    else:
        return 'HOLD'

# --- EMA 50/100/200 ---
def get_ema(df, period):
    if df is not None and len(df) >= period:
        return round(df['close'].ewm(span=period, adjust=False).mean().iloc[-1], 2)
    return 'Недостаточно данных'

def smart_trade_signal(indicators: dict, price=None, support=None, resistance=None) -> dict:
    """
    Возвращает dict: {'signal': 'BUY/SELL/HOLD', 'leverage': int, 'stop_loss': float, 'take_profit': float, 'reason': str}
    """
    probability = 0
    prob_direction = 'Нейтрально'
    # Сбор данных
    ema50 = safe_float(indicators.get('EMA50'))
    ema100 = safe_float(indicators.get('EMA100'))
    ema200 = safe_float(indicators.get('EMA200'))
    rsi = safe_float(indicators.get('RSI'))
    macd_val = safe_float(indicators.get('MACD'))
    if macd_val is None:
        macd_val = safe_float(indicators.get('MACD.macd'))
    atr = safe_float(indicators.get('ATR'))
    volume = safe_float(indicators.get('volume'))
    avg_volume = safe_float(indicators.get('avg_volume'))
    trend = indicators.get('trend', '')
    # --- Голоса ---
    votes = []
    # RSI
    if rsi is not None:
        if rsi < 35:
            votes.append('BUY')
        elif rsi > 65:
            votes.append('SELL')
    # MACD
    if macd_val is not None:
        if macd_val > 0:
            votes.append('BUY')
        elif macd_val < 0:
            votes.append('SELL')
    # EMA 50/100/200
    if ema50 and ema100 and ema200:
        if ema50 > ema100 > ema200:
            votes.append('BUY')
        elif ema50 < ema100 < ema200:
            votes.append('SELL')
    # Объём
    if volume is not None and avg_volume is not None:
        if volume > avg_volume:
            votes.append('BUY')
        elif volume < avg_volume:
            votes.append('SELL')
    # SuperTrend
    supertrend = indicators.get('SuperTrend')
    if supertrend == 'BUY':
        votes.append('BUY')
    elif supertrend == 'SELL':
        votes.append('SELL')
    # PSAR
    psar = indicators.get('PSAR')
    if psar == 'BUY':
        votes.append('BUY')
    elif psar == 'SELL':
        votes.append('SELL')
    # --- Фильтры по тренду ---
    if trend and 'Медвежий' in trend and votes.count('BUY') > 0:
        return {'signal': 'HOLD', 'leverage': 0, 'stop_loss': None, 'take_profit': None, 'reason': 'Бычий сигнал на медвежьем рынке'}
    if trend and 'Бычий' in trend and votes.count('SELL') > 0:
        return {'signal': 'HOLD', 'leverage': 0, 'stop_loss': None, 'take_profit': None, 'reason': 'Медвежий сигнал на бычьем рынке'}
    # --- Вероятность и направление без нейтрального состояния ---
    long_votes = 0
    short_votes = 0
    total_votes = 0
    last_vote = None
    # RSI
    if rsi is not None:
        total_votes += 1
        if rsi < 35:
            long_votes += 1
            last_vote = 'Лонг'
        elif rsi > 65:
            short_votes += 1
            last_vote = 'Шорт'
    # MACD
    if macd_val is not None:
        total_votes += 1
        if macd_val > 0:
            long_votes += 1
            last_vote = 'Лонг'
        elif macd_val < 0:
            short_votes += 1
            last_vote = 'Шорт'
    # EMA 50/100/200
    if ema50 and ema100 and ema200:
        total_votes += 1
        if ema50 > ema100 > ema200:
            long_votes += 1
            last_vote = 'Лонг'
        elif ema50 < ema100 < ema200:
            short_votes += 1
            last_vote = 'Шорт'
    # Объём
    if volume is not None and avg_volume is not None:
        total_votes += 1
        if volume > avg_volume:
            long_votes += 1
            last_vote = 'Лонг'
        elif volume < avg_volume:
            short_votes += 1
            last_vote = 'Шорт'
    # SuperTrend
    supertrend = indicators.get('SuperTrend')
    if supertrend == 'BUY':
        total_votes += 1
        long_votes += 1
        last_vote = 'Лонг'
    elif supertrend == 'SELL':
        total_votes += 1
        short_votes += 1
        last_vote = 'Шорт'
    # PSAR
    psar = indicators.get('PSAR')
    if psar == 'BUY':
        total_votes += 1
        long_votes += 1
        last_vote = 'Лонг'
    elif psar == 'SELL':
        total_votes += 1
        short_votes += 1
        last_vote = 'Шорт'
    # --- Итоговый сигнал ---
    buy_votes = votes.count('BUY')
    sell_votes = votes.count('SELL')
    if buy_votes >= 2:
        signal = 'BUY'
    elif sell_votes >= 2:
        signal = 'SELL'
    else:
        signal = 'HOLD'
    # --- Вероятность и направление ---
    if total_votes > 0:
        prob_val = int(round(100 * max(long_votes, short_votes) / total_votes))
        probability = max(prob_val, 50)
        if long_votes > short_votes:
            prob_direction = 'Лонг'
        elif short_votes > long_votes:
            prob_direction = 'Шорт'
        else:
            prob_direction = last_vote if last_vote else 'Лонг'
    else:
        probability = 50
        prob_direction = 'Лонг'
    # --- Кредитное плечо ---
    leverage = 5
    # --- Стоп-лосс и тейк-профит ---
    if not price or price is None:
        stop_loss = take_profit = None
    else:
        stop_loss_atr = atr*1.5 if atr else price*0.015
        stop_loss_level = abs(price-support) if support is not None else stop_loss_atr
        stop_loss = min(stop_loss_atr, stop_loss_level)
        stop_loss = max(stop_loss, price*0.005)
        take_profit = stop_loss*2
    return {'signal': signal, 'leverage': leverage, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': '', 'probability': probability, 'prob_direction': prob_direction}

def get_forecast(symbol: str, interval: str) -> Dict[str, Any]:
    """
    Получает прогноз по монете и таймфрейму с помощью TradingView TA_Handler.
    Возвращает словарь с текстом и индикаторами.
    """
    logging.info(f"[ANALYSIS] Запрос анализа {symbol} @ {interval}")
    try:
        handler = TA_Handler(
            symbol=symbol,
            screener="crypto",
            exchange="BINANCE",
            interval=interval
        )
        analysis = handler.get_analysis()
        if not analysis:
            return {"text": "Нет данных по монете.", "indicators": {}}
        logging.info(f"INDICATORS: {analysis.indicators}")
        logging.info(f"MA: {analysis.moving_averages}")
        r = analysis.summary.get("RECOMMENDATION", "—")
        rsi = format_float(analysis.indicators.get("RSI"))
        macd = format_float(analysis.indicators.get("MACD.macd"))
        stoch_rsi = format_float(analysis.indicators.get("Stoch.RSI.K"))
        ema_50 = format_float(analysis.indicators.get("EMA50"))
        ema_100 = format_float(analysis.indicators.get("EMA100"))
        ema_200 = format_float(analysis.indicators.get("EMA200"))
        ma_summary = analysis.moving_averages.get("RECOMMENDATION", "—")
        ma_buy = analysis.moving_averages.get("BUY", 0)
        ma_sell = analysis.moving_averages.get("SELL", 0)
        trend = "\U0001F4C8 Бычий" if ma_buy > ma_sell else "\U0001F4C9 Медвежий"
        seven_days_signal = get_seven_days_signal(symbol, interval)
        from charting import get_ohlcv
        try:
            df = get_ohlcv(symbol, interval, limit=300)
            if df is not None and len(df) > 0:
                volume = format_float(df["volume"].iloc[-1])
                avg_volume = format_float(df["volume"].mean())
                price = safe_scalar_float(df["close"].iloc[-1])
                support_val = df["low"].min()
                if hasattr(support_val, 'item'):
                    support_val = support_val.item()
                support = safe_scalar_float(support_val)
                resistance_val = df["high"].max()
                if hasattr(resistance_val, 'item'):
                    resistance_val = resistance_val.item()
                resistance = safe_scalar_float(resistance_val)
                # EMA 50/100/200
                ema_50 = get_ema(df, 50)
                ema_100 = get_ema(df, 100)
                ema_200 = get_ema(df, 200)
            else:
                volume = "—"
                avg_volume = "—"
                price = support = resistance = None
                ema_50 = ema_100 = ema_200 = 'Недостаточно данных'
        except Exception:
            volume = "—"
            avg_volume = "—"
            price = support = resistance = None
            ema_50 = ema_100 = ema_200 = 'Недостаточно данных'
        # --- Новые индикаторы ---
        try:
            if PANDAS_TA_AVAILABLE and not df.empty:
                # ATR
                atr_val = df.ta.atr(length=14).iloc[-1]
                atr = float(atr_val) if pd.notnull(atr_val) else None
                # SuperTrend
                st = df.ta.supertrend(length=10, multiplier=3.0)
                supertrend_dir = st[f'SUPERTd_10_3.0'].iloc[-1] if f'SUPERTd_10_3.0' in st else None
                supertrend = 'BUY' if supertrend_dir == 1 else ('SELL' if supertrend_dir == -1 else None)
                # Parabolic SAR
                psar = df.ta.psar(step=0.02, max_step=0.2)
                psar_dir = psar['PSARd_0.02_0.2'].iloc[-1] if 'PSARd_0.02_0.2' in psar else None
                psar_signal = 'BUY' if psar_dir == 1 else ('SELL' if psar_dir == -1 else None)
            else:
                atr = None
                supertrend = None
                psar_signal = None
        except Exception as e:
            logging.warning(f"[TA] Ошибка расчёта ATR/SuperTrend/PSAR: {e}")
            atr = None
            supertrend = None
            psar_signal = None
        indicators = {
            "recommendation": r,
            "SevenDays": seven_days_signal,
            "RSI": rsi,
            "MACD": macd,
            "StochRSI": stoch_rsi,
            "EMA50": ema_50,
            "EMA100": ema_100,
            "EMA200": ema_200,
            "MA_summary": ma_summary,
            "MA_buy": ma_buy,
            "MA_sell": ma_sell,
            "trend": trend,
            "volume": volume,
            "avg_volume": avg_volume,
            # Новые индикаторы:
            "ATR": atr,
            "SuperTrend": supertrend,
            "PSAR": psar_signal
        }
        # --- Новый сигнал ---
        trade_sig = smart_trade_signal(
            indicators,
            price=price if price is not None else 0.0,
            support=support if support is not None else 0.0,
            resistance=resistance if resistance is not None else 0.0
        )
        indicators["final_signal"] = trade_sig['signal']
        indicators["leverage"] = trade_sig['leverage']
        indicators["stop_loss"] = trade_sig['stop_loss']
        indicators["take_profit"] = trade_sig['take_profit']
        indicators["signal_reason"] = trade_sig['reason']
        indicators["probability"] = trade_sig.get('probability', 0)
        indicators["prob_direction"] = trade_sig.get('prob_direction', 'Нейтрально')
        # Формируем текст анализа
        analysis_lines = [
            f"• Рекомендация: {r}",
            f"• Seven days: {seven_days_signal}",
            f"• RSI: {rsi}",
            f"• MACD: {macd}",
            f"• Объём: {volume}",
            f"• Stoch RSI: {stoch_rsi}",
            f"• EMA(50/100/200): {ema_50} / {ema_100} / {ema_200}",
            f"• MA Summary: {ma_summary} ({ma_buy} Buy / {ma_sell} Sell)",
            f"• Текущий тренд: {trend}"
        ]
        

        
        return {
            "text": '\n'.join(analysis_lines),
            "indicators": indicators
        }
    except Exception as e:
        logging.exception(f"Ошибка анализа {symbol}: {e}")
        return {"text": f"Ошибка анализа: {e}", "indicators": {}}

def generate_signal(indicators: Dict[str, Any]) -> str:
    """
    Генерирует торговый сигнал на основе индикаторов.
    """
    try:
        rsi = float(indicators.get("RSI", 0))
        trend = indicators.get("trend", "")
        if rsi < 30 and "Бычий" in trend:
            return "🟢 Сигнал на покупку (перепроданность + бычий тренд)"
        elif rsi > 70 and "Медвежий" in trend:
            return "🔴 Сигнал на продажу (перекупленность + медвежий тренд)"
        else:
            return "⚪ Нет явного сигнала (ожидание)"
    except Exception:
        return "⚪ Недостаточно данных для сигнала"

async def safe_generate_explanation(indicators: dict, timeframe: str, symbol: str, max_retries: int = 3, delay: int = 2) -> str:
    for attempt in range(max_retries):
        try:
            return await generate_explanation(indicators, timeframe, symbol)
        except Exception as e:
            logging.warning(f"Ошибка LLM (попытка {attempt+1}): {e}")
            await asyncio.sleep(delay)
    return "⚠️ Не удалось получить пояснение от ИИ после нескольких попыток."

def get_support_resistance(df: pd.DataFrame, n: int = 20) -> Tuple[float, float]:
    """
    Вычисляет уровни поддержки и сопротивления по последним n свечам.
    """
    recent_lows = df['low'].tail(n)
    recent_highs = df['high'].tail(n)
    support = recent_lows.min()
    resistance = recent_highs.max()
    return float(support), float(resistance) 