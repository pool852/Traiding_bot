from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Dict, Any
import logging

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

main_menu = ReplyKeyboardMarkup(resize_keyboard=True)  # type: ignore
for sym in symbols:
    main_menu.add(KeyboardButton(text=sym, request_contact=False, request_location=False))

markup = InlineKeyboardMarkup()
markup.add(InlineKeyboardButton(text="15 минут", callback_data="forecast_15m"))  # type: ignore
markup.add(InlineKeyboardButton(text="⏰ 1 час", callback_data="forecast_1h"))  # type: ignore
markup.add(InlineKeyboardButton(text="🕓 4 часа", callback_data="forecast_4h"))  # type: ignore
markup.add(InlineKeyboardButton(text="📋 Полный прогноз", callback_data="forecast_full"))  # type: ignore
markup.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh"))  # type: ignore

user_state: Dict[int, str] = {} 