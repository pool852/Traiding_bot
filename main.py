import os
import logging
from dotenv import load_dotenv
load_dotenv()

# Проверка переменных окружения
API_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Проверка и вывод токена (замаскированного)
if API_TOKEN:
    print(f"[DEBUG] BOT_TOKEN загружен: {API_TOKEN[:6]}...{API_TOKEN[-4:]}")
else:
    print("[DEBUG] BOT_TOKEN не найден!")

if not API_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")
if not OPENAI_API_KEY:
    raise ValueError("Переменная окружения OPENAI_API_KEY не задана!")

from handlers import *

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler("bot.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logging.info('[STARTUP] Бот запущен')
    from aiogram.utils import executor
    executor.start_polling(dp, skip_updates=True) 