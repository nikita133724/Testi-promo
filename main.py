import asyncio
import os
import random
from fastapi import Form
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

# -----------------------
# Admin panel
# -----------------------

from admin_users import AdminUsers
from telegram_bot import RAM_DATA, app as tg_bot

admin_users = AdminUsers(RAM_DATA, tg_bot)
@app_fastapi.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    users_list = []
    for chat_id in admin_users.RAM_DATA.keys():
        username = str(chat_id)  # по умолчанию
        try:
            # пробуем получить username через бота
            user = await tg_bot.get_chat(chat_id)
            if user.username:
                username = f"@{user.username}"
        except Exception:
            pass
        users_list.append({"chat_id": chat_id, "username": username})

    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users_list}
    )


from datetime import datetime

@app_fastapi.get("/admin/users/{chat_id}", response_class=HTMLResponse)
async def admin_user_detail(request: Request, chat_id: int):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)

    # Получаем username через бота
    try:
        user = await tg_bot.get_chat(chat_id)
        username = f"@{user.username}" if user.username else str(chat_id)
    except Exception:
        username = str(chat_id)

    next_refresh = user_data.get("next_refresh_time", "не задано")

    refresh_token = user_data.get("refresh_token")
    site_name = "Неизвестно"
    profile_link = "#"
    if refresh_token:
        from admin_users import extract_user_id_from_refresh, fetch_site_nickname
        user_id = extract_user_id_from_refresh(refresh_token)
        if user_id:
            nickname = await fetch_site_nickname(user_id)
            if nickname:
                site_name = nickname
            profile_link = f"https://csgoyz.run/profile/{user_id}"

    status = "приостановлен" if user_data.get("suspended") else "активен"

    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "chat_id": chat_id,
            "username": username,
            "next_refresh": next_refresh,
            "site_name": site_name,
            "profile_link": profile_link,
            "status": status,
            "button_text": "🔄 Восстановить" if user_data.get("suspended") else "⏸ Приостановить",
            "tokens": None  # пока скрыто
        }
    )
@app_fastapi.post("/admin/users/{chat_id}/toggle_status")
async def admin_user_toggle_status(chat_id: int):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)

    # Переключаем статус
    user_data["suspended"] = not user_data.get("suspended", False)

    # Сохраняем через _save_to_redis_partial
    from telegram_bot import _save_to_redis_partial
    _save_to_redis_partial(chat_id, {"suspended": user_data["suspended"]})

    # Перенаправляем обратно на страницу пользователя
    return RedirectResponse(f"/admin/users/{chat_id}", status_code=303)
@app_fastapi.post("/admin/users/{chat_id}/tokens")
async def admin_user_tokens(chat_id: int):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)

    tokens = {
        "access_token": user_data.get("access_token", "не задан"),
        "refresh_token": user_data.get("refresh_token", "не задан")
    }

    # Перенаправляем на ту же страницу с токенами
    user_data_for_template = {
        "request": None,  # временно, FastAPI сам передаст request в route
        "chat_id": chat_id,
        "username": f"@{user_data.get('username', chat_id)}",
        "next_refresh": user_data.get("next_refresh_time", "не задано"),
        "site_name": "Неизвестно",
        "profile_link": "#",
        "status": "приостановлен" if user_data.get("suspended") else "активен",
        "button_text": "🔄 Восстановить" if user_data.get("suspended") else "⏸ Приостановить",
        "tokens": tokens
    }

    return templates.TemplateResponse("admin/user_detail.html", user_data_for_template)

from admin_users import KEY_DURATION_OPTIONS

@app_fastapi.get("/admin/keys", response_class=HTMLResponse)
async def admin_keys_page(request: Request):
    return templates.TemplateResponse(
        "admin/keys.html",
        {"request": request, "durations": KEY_DURATION_OPTIONS, "key": None}
    )
from fastapi import Form

@app_fastapi.post("/admin/keys/generate", response_class=HTMLResponse)
async def admin_generate_key(request: Request, duration: int = Form(...)):
    from access_control import generate_key

    # Берём выбранный duration из KEY_DURATION_OPTIONS
    label, delta = KEY_DURATION_OPTIONS[duration]
    key = generate_key(delta)

    return templates.TemplateResponse(
        "admin/keys.html",
        {
            "request": request,
            "durations": KEY_DURATION_OPTIONS,
            "key": key
        }
    )


# -----------------------
# Keep-alive (для Render)
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
