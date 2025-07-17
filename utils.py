from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Dict, Any

symbols = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "AAVEUSDT",
    "ADAUSDT", "WIFUSDT", "AVAXUSDT", "SUIUSDT"
]

def format_float(value):
    try:
        if value is None:
            return "-"
        if isinstance(value, (int, float)):
            return f"{value:.2f}"
        if isinstance(value, str):
            try:
                fval = float(value)
                return f"{fval:.2f}"
            except Exception:
                return value
        return str(value)
    except Exception:
        return "-"

user_state: Dict[int, str] = {} 