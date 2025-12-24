import asyncio
import os
import random
from fastapi import Form, FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import uvicorn
from aiohttp import ClientSession
from functools import wraps

# -----------------------
# Telegram и RAM_DATA
# -----------------------
from telegram_client import client
from telegram_bot import app as tg_app, bot, load_chatids, build_reply_keyboard, RAM_DATA, _save_to_redis_partial
from refresh_tokens import token_refresher_loop
from access_control import subscription_watcher, generate_key
from admin_users import AdminUsers, KEY_DURATION_OPTIONS, extract_user_id_from_refresh, fetch_site_nickname


# -----------------------
# Middleware для шаблонов
# -----------------------
from starlette.middleware.sessions import SessionMiddleware
SECRET_KEY = "vAGavYNa1WzrymonUQIEJ9ZW9mEDf"

# 1️⃣ Создаем приложение
app_fastapi = FastAPI()

# 2️⃣ Подключаем middleware сессий
app_fastapi.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 3️⃣ Jinja2Templates
templates = Jinja2Templates(directory="templates")

# 4️⃣ Middleware, которое использует request.session
@app_fastapi.middleware("http")
async def add_is_admin_to_request(request: Request, call_next):
    is_admin = request.session.get("is_admin", False)
    request.state.is_admin = is_admin
    response = await call_next(request)
    return response



def admin_required(func):
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("is_admin", False):
            return RedirectResponse("/login", status_code=303)
        return await func(request, *args, **kwargs)
    return wrapper



# -----------------------
# Настройки админа
# -----------------------
ADMIN_LOGIN = "сахар"
ADMIN_PASSWORD = "394990!mmmn"

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
# Login/Logout
# -----------------------
@app_fastapi.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app_fastapi.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        request.session["is_admin"] = True
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})

@app_fastapi.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# -----------------------
# Admin Users
# -----------------------
admin_users = AdminUsers(RAM_DATA, tg_app)

@app_fastapi.get("/admin/users", response_class=HTMLResponse)
@admin_required
async def admin_users_page(request: Request):
    users_list = []
    for chat_id in admin_users.RAM_DATA.keys():
        username = str(chat_id)
        try:
            user = await tg_app.get_chat(chat_id)
            if user.username:
                username = f"@{user.username}"
        except:
            pass
        users_list.append({"chat_id": chat_id, "username": username})

    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "users": users_list,
        "is_admin": True
    })

@app_fastapi.get("/admin/users/{chat_id}", response_class=HTMLResponse)
@admin_required
async def admin_user_detail(request: Request, chat_id: int):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)

    try:
        user = await tg_app.get_chat(chat_id)
        username = f"@{user.username}" if user.username else str(chat_id)
    except:
        username = str(chat_id)

    next_refresh = user_data.get("next_refresh_time", "не задано")
    refresh_token = user_data.get("refresh_token")
    site_name = "Неизвестно"
    profile_link = "#"
    if refresh_token:
        user_id = extract_user_id_from_refresh(refresh_token)
        if user_id:
            nickname = await fetch_site_nickname(user_id)
            if nickname:
                site_name = nickname
            profile_link = f"https://csgoyz.run/profile/{user_id}"

    status = "приостановлен" if user_data.get("suspended") else "активен"

    return templates.TemplateResponse("admin/user_detail.html", {
        "request": request,
        "chat_id": chat_id,
        "username": username,
        "next_refresh": next_refresh,
        "site_name": site_name,
        "profile_link": profile_link,
        "status": status,
        "button_text": "🔄 Восстановить" if user_data.get("suspended") else "⏸ Приостановить",
        "tokens": None,
        "is_admin": True
    })

@app_fastapi.post("/admin/users/{chat_id}/toggle_status")
@admin_required
async def admin_user_toggle_status(request: Request, chat_id: int):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)
    user_data["suspended"] = not user_data.get("suspended", False)
    _save_to_redis_partial(chat_id, {"suspended": user_data["suspended"]})
    return RedirectResponse(f"/admin/users/{chat_id}", status_code=303)


@app_fastapi.post("/admin/users/{chat_id}/tokens")
@admin_required
async def admin_user_tokens(request: Request, chat_id: int):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)

    tokens = {
        "access_token": user_data.get("access_token", "не задан"),
        "refresh_token": user_data.get("refresh_token", "не задан")
    }

    return templates.TemplateResponse("admin/user_detail.html", {
        "request": request,
        "chat_id": chat_id,
        "username": f"@{user_data.get('username', chat_id)}",
        "next_refresh": user_data.get("next_refresh_time", "не задано"),
        "site_name": "Неизвестно",
        "profile_link": "#",
        "status": "приостановлен" if user_data.get("suspended") else "активен",
        "button_text": "🔄 Восстановить" if user_data.get("suspended") else "⏸ Приостановить",
        "tokens": tokens,
        "is_admin": True
    })

# -----------------------
# Admin Keys
# -----------------------
@app_fastapi.get("/admin/keys", response_class=HTMLResponse)
@admin_required
async def admin_keys_page(request: Request):
    return templates.TemplateResponse("admin/keys.html", {
        "request": request,
        "durations": KEY_DURATION_OPTIONS,
        "key": None,
        "is_admin": True
    })

@app_fastapi.post("/admin/keys/generate", response_class=HTMLResponse)
@admin_required
async def admin_generate_key(request: Request, duration: int = Form(...)):
    label, delta = KEY_DURATION_OPTIONS[duration]
    key = generate_key(delta)
    return templates.TemplateResponse("admin/keys.html", {
        "request": request,
        "durations": KEY_DURATION_OPTIONS,
        "key": key,
        "is_admin": True
    })

# -----------------------
# Keep-alive
# -----------------------
SELF_URL = "https://promo-zq59.onrender.com"

async def keep_alive():
    if not SELF_URL:
        return
    while True:
        await asyncio.sleep(240 + random.random() * 120)
        try:
            async with ClientSession() as session:
                async with session.get(f"{SELF_URL}/healthz") as resp:
                    print(f"Keep-alive ping: {resp.status}")
        except Exception as e:
            print(f"Keep-alive error: {e}")

# -----------------------
# Telegram bot helpers
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
# FastAPI запуск
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
    # FastAPI
    asyncio.create_task(start_fastapi())
    asyncio.create_task(keep_alive())

    # Таймеры
    asyncio.create_task(run_token_refresher())
    asyncio.create_task(subscription_watcher(bot))

    # Telegram
    print("Запуск Telegram-бота...")
    await tg_app.initialize()
    await tg_app.start()

    # Telethon
    await client.start()
    print("Telethon клиент запущен.")

    try:
        await asyncio.gather(
            tg_app.updater.start_polling(),
            client.run_until_disconnected()
        )
    finally:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()

# -----------------------
# Запуск
# -----------------------
if __name__ == "__main__":
    asyncio.run(main())
