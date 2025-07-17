from aiogram import Bot, Dispatcher
import os

token = os.getenv("BOT_TOKEN")
if not token:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")
bot = Bot(token=token)
dp = Dispatcher(bot)
