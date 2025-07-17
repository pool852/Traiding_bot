import mplfinance as mpf
import pandas as pd
import matplotlib.pyplot as plt
import os
import requests
from typing import List, Optional
import logging

def get_ohlcv(symbol: str, timeframe: str = "15m", limit: int = 100) -> pd.DataFrame:
    """
    Загружает исторические данные OHLCV с Binance API.
    :param symbol: Символ в формате "BTCUSDT"
    :param timeframe: Таймфрейм (например, "15m", "1h", "4h")
    :param limit: Количество свечей
    :return: DataFrame с индексом datetime
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol.upper(),
        "interval": timeframe,
        "limit": limit
    }
    logging.info(f"[BINANCE] Запрос OHLCV: {symbol} {timeframe} limit={limit}")
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data or not isinstance(data, list):
            logging.error("Пустой ответ от Binance или неверный формат данных")
            return pd.DataFrame({"open":[], "high":[], "low":[], "close":[], "volume":[]})
        df = pd.DataFrame(data)
        df.columns = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
        ]
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
        df.set_index("timestamp", inplace=True)
        cols = ["open", "high", "low", "close", "volume"]
        if df.empty:
            return pd.DataFrame({col: [] for col in cols})
        df = df.loc[:, cols]
        logging.info(f"[BINANCE] Получено {len(df)} свечей для {symbol} {timeframe}")
        return df
    except Exception as e:
        logging.exception(f"[BINANCE] Не удалось получить OHLCV для {symbol} {timeframe}: {e}")
        return pd.DataFrame({"open":[], "high":[], "low":[], "close":[], "volume":[]})

def render_dual_chart(
    df_short: pd.DataFrame,
    df_long: pd.DataFrame,
    levels: Optional[List[float]] = None,
    arrows: Optional[List[dict]] = None,
    symbol: str = "BTCUSDT"
) -> str:
    path = f"chart_{symbol}.png"
    # Тёмная тема с зелёными и красными свечами
    mc = mpf.make_marketcolors(
        up='lime', down='red',
        edge='inherit', wick='inherit', volume='inherit'
    )
    s = mpf.make_mpf_style(base_mpf_style='nightclouds', marketcolors=mc, rc={
        'axes.labelsize': 14,
        'axes.titlesize': 18,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
        'figure.facecolor': '#181c25',
        'axes.facecolor': '#181c25',
        'savefig.facecolor': '#181c25',
        'axes.edgecolor': '#888',
        'grid.color': '#333',
        'text.color': 'white',
    })
    addplots = []
    # EMA
    if not df_short.empty:
        ema_colors = {7: "orange", 50: "cyan", 100: "purple"}
        for period in [7, 50, 100]:
            ema = df_short["close"].ewm(span=period, adjust=False).mean()
            addplots.append(mpf.make_addplot(ema, color=ema_colors[period], width=2.2, linestyle='-'))
    # Уровни
    if levels is not None:
        for level in levels:
            addplots.append(mpf.make_addplot([level]*len(df_short), color='#00BFFF', width=2.0, linestyle='--'))
    # MACD (в отдельном окне)
    if not df_short.empty:
        exp12 = df_short["close"].ewm(span=12, adjust=False).mean()
        exp26 = df_short["close"].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        addplots.append(mpf.make_addplot(macd, panel=1, color='lime', width=2, ylabel='MACD'))
        addplots.append(mpf.make_addplot(signal, panel=1, color='red', width=2))
    mpf.plot(
        df_short,
        type='candle',
        style=s,
        title=f"{symbol} — График",
        volume=True,
        addplot=addplots,
        savefig=path,
        panel_ratios=(3,1) if not df_short.empty else None,
        figscale=1.3,
        tight_layout=True,
        xrotation=15,
        ylabel='Цена',
        ylabel_lower='Объём',
        returnfig=False
    )
    return path


def generate_chart(
    symbol: str,
    interval_binance: str = "15m",
    output_path: str = "chart.png",
    levels: Optional[List[float]] = None,
    arrows: Optional[List[dict]] = None
) -> str:
    try:
        logging.info(f"[CHART] generate_chart: symbol={symbol}, interval={interval_binance}, output_path={output_path}, levels={levels}")
        df_short = get_ohlcv(symbol, interval_binance)
        # Для dual chart используем 1h как long, если не совпадает
        df_long = get_ohlcv(symbol, "1h") if interval_binance != "1h" else df_short
        path = render_dual_chart(df_short, df_long, levels=levels, arrows=arrows, symbol=symbol)
        if path and path != output_path:
            os.rename(path, output_path)
            logging.info(f"[CHART] Переименован {path} -> {output_path}")
        if path:
            logging.info(f"[CHART] Итоговый путь графика: {output_path}")
            return output_path
        else:
            logging.error(f"[CHART] График не был создан для {symbol} {interval_binance}")
            return ""
    except Exception as e:
        logging.exception(f"[CHART][ERROR] Ошибка генерации графика: {e}")
        return ""
