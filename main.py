import asyncio
import importlib
import subprocess
import sys
import os
import random

# -----------------------
# Импорты после установки пакетов
# -----------------------
from aiohttp import web, ClientSession
from telegram_client import client
from telegram_bot import app, bot, load_chatids, build_reply_keyboard
from refresh_tokens import token_refresher_loop
from access_control import subscription_watcher

# -----------------------
# HTTP-сервер (для Render)
# -----------------------
async def start_web_server():
    web_app = web.Application()

    async def healthcheck(request):
        return web.Response(text="OK")

    web_app.router.add_get("/", healthcheck)
    web_app.router.add_get("/healthz", healthcheck)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP-сервер запущен на порту {port}")

# -----------------------
# Keep-alive для Render
# -----------------------
SELF_URL = "https://promo-zq59.onrender.com"

async def keep_alive():
    if not SELF_URL:
        print("SELF_URL не задан, keep-alive не будет работать")
        return

    while True:
        delay = 240 + random.random() * 120
        await asyncio.sleep(delay)

        try:
            async with ClientSession() as session:
                async with session.get(f"{SELF_URL}/healthz", headers={
                    "User-Agent": "Python/KeepAlive",
                    "X-Keep-Alive": str(random.random())
                }) as resp:
                    if resp.status == 200:
                        print("Keep-alive ping OK")
                    else:
                        print(f"Keep-alive ping вернул статус {resp.status}")
        except Exception as e:
            print(f"Keep-alive error: {e}")

# -----------------------
# Загрузка ChatID
# -----------------------
chat_ids = load_chatids()

# -----------------------
# Фоновый таймер токенов
# -----------------------
async def run_token_refresher():
    asyncio.create_task(token_refresher_loop())
    print("Фоновый таймер обновления токенов запущен.")

# -----------------------
# Функция для отправки сообщений всем пользователям
# -----------------------
async def send_message_to_all(text, keyboard=False):
    for chat_id in chat_ids:
        try:
            reply_markup = build_reply_keyboard(chat_id) if keyboard else None
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        except Exception as e:
            print(f"Ошибка отправки сообщения {chat_id}: {e}")

# -----------------------
# Основная логика
# -----------------------
# -----------------------
# Основная логика
# -----------------------
async def main():
    # 🔹 HTTP-сервер и keep-alive
    asyncio.create_task(start_web_server())
    asyncio.create_task(keep_alive())

    # 🔹 Таймер токенов
    asyncio.create_task(run_token_refresher())

    # 🔹 Фоновый таймер подписок
    asyncio.create_task(subscription_watcher(bot))

    # 🔹 Запуск Telegram-бота асинхронно
    print("Запуск Telegram-бота...")
    await app.initialize()
    await app.start()
    
    # 🔹 Telethon
    await client.start()
    print("Telethon клиент запущен, ждём сообщений...")

    # 🔹 Ожидание работы бота и Telethon
    try:
        await asyncio.gather(
            app.updater.start_polling(),  # правильно для async запуска
            client.run_until_disconnected()
        )
    finally:
        # graceful shutdown
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

# -----------------------
# Запуск
# -----------------------
if __name__ == "__main__":
    asyncio.run(main())
