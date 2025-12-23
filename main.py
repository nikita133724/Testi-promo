import asyncio
import os
import random

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn
from aiohttp import ClientSession

# -----------------------
# Импорты Telegram и RAM_DATA
# -----------------------
from telegram_client import client
from telegram_bot import app, bot, load_chatids, build_reply_keyboard, RAM_DATA
from refresh_tokens import token_refresher_loop
from access_control import subscription_watcher

# -----------------------
# Настройка FastAPI и Jinja2
# -----------------------
app_fastapi = FastAPI()
templates = Jinja2Templates(directory="templates")  # папка с stats.html
from admin_users import get_all_users, refresh_user_token
from access_control import get_all_keys, create_key
from fastapi import Form
from fastapi.responses import RedirectResponse

# -----------------------
# Маршруты
# -----------------------
@app_fastapi.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse("<h2>Сервер работает</h2>")

@app_fastapi.get("/healthz", response_class=HTMLResponse)
async def healthcheck():
    return HTMLResponse("OK")

@app_fastapi.get("/stats", response_class=HTMLResponse)
async def get_post_stats(request: Request):
    stats = RAM_DATA.get("last_post_stats")
    if not stats:
        return HTMLResponse("<h2>Данных нет</h2>", status_code=404)
    return templates.TemplateResponse("stats.html", {"request": request, "stats": stats})

# ------------------ Пользователи ------------------
@app_fastapi.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    users_list = get_all_users()
    return templates.TemplateResponse("users.html", {"request": request, "users": users_list})

@app_fastapi.post("/users/refresh")
async def refresh_user_token_route(chat_id: str = Form(...)):
    refresh_user_token(chat_id)
    return RedirectResponse(url="/users", status_code=303)

# ------------------ Ключи ------------------
@app_fastapi.get("/keys", response_class=HTMLResponse)
async def keys_page(request: Request):
    keys_list = get_all_keys()
    return templates.TemplateResponse("keys.html", {"request": request, "keys": keys_list})

@app_fastapi.post("/keys/create")
async def create_key_route(code: str = Form(...)):
    create_key(code)
    return RedirectResponse(url="/keys", status_code=303)

# -----------------------
# Keep-alive (для Render)
# -----------------------
SELF_URL = os.environ.get("SELF_URL", "")
async def keep_alive():
    if not SELF_URL:
        print("SELF_URL не задан, keep-alive не будет работать")
        return
    while True:
        delay = 240 + random.random() * 120
        await asyncio.sleep(delay)
        try:
            async with ClientSession() as session:
                async with session.get(f"{SELF_URL}/healthz") as resp:
                    if resp.status == 200:
                        print("Keep-alive ping OK")
                    else:
                        print(f"Keep-alive ping вернул статус {resp.status}")
        except Exception as e:
            print(f"Keep-alive error: {e}")

# -----------------------
# Функции для Telegram
# -----------------------
chat_ids = load_chatids()

async def run_token_refresher():
    asyncio.create_task(token_refresher_loop())
    print("Фоновый таймер обновления токенов запущен.")

async def send_message_to_all(text, keyboard=False):
    for chat_id in chat_ids:
        try:
            reply_markup = build_reply_keyboard(chat_id) if keyboard else None
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        except Exception as e:
            print(f"Ошибка отправки сообщения {chat_id}: {e}")

# -----------------------
# Запуск FastAPI сервера (uvicorn)
# -----------------------
async def start_fastapi():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app_fastapi, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

# -----------------------
# Основная логика
# -----------------------
async def main():
    # 🔹 FastAPI сервер
    asyncio.create_task(start_fastapi())
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
            app.updater.start_polling(),
            client.run_until_disconnected()
        )
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

# -----------------------
# Запуск
# -----------------------
if __name__ == "__main__":
    asyncio.run(main())
