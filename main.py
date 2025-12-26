import asyncio
import random
import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from datetime import timezone, timedelta, datetime
from zoneinfo import ZoneInfo
# -----------------------
# Telegram и RAM_DATA
from telegram_client import client
from telegram_bot import app as tg_app, bot, load_chatids, build_reply_keyboard, RAM_DATA, _save_to_redis_partial, send_message_to_user, ReplyKeyboardMarkup
from refresh_tokens import token_refresher_loop
from access_control import subscription_watcher, generate_key
from admin_users import AdminUsers, KEY_DURATION_OPTIONS, extract_user_id_from_refresh, fetch_site_nickname

# -----------------------
SECRET_KEY = "vAGavYNa1WzrymonUQIEJ9ZW9mEDf"
SELF_URL = os.environ.get("SELF_URL", "https://promo-zq59.onrender.com")

app_fastapi = FastAPI()
app_fastapi.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory="templates")

# -----------------------
# Настройки админа
ADMIN_LOGIN = "сахар"
ADMIN_PASSWORD = "394990!mmmn"

admin_users = AdminUsers(RAM_DATA, tg_app)
chat_ids = load_chatids()

# -----------------------
# ADMIN DEPENDENCY (ВАЖНО)
def admin_required(request: Request):
    if not request.session.get("is_admin", False):
        raise HTTPException(status_code=303, headers={"Location": "/login"})

# -----------------------
# Routes
@app_fastapi.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse("<h2>Сервер работает</h2>")

@app_fastapi.get("/healthz", response_class=HTMLResponse)
async def healthcheck():
    return HTMLResponse("OK")

# -----------------------
# Login / Logout
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
@app_fastapi.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    _: None = Depends(admin_required)
):
    users_list = []
    for chat_id in admin_users.RAM_DATA.keys():
        username = await admin_users.get_username(chat_id)  # Используем новую функцию
        users_list.append({"chat_id": chat_id, "username": username})

    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users_list, "is_admin": True}
    )


@app_fastapi.get("/admin/users/{chat_id}", response_class=HTMLResponse)
async def admin_user_detail(
    request: Request,
    chat_id: int,
    _: None = Depends(admin_required)
):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)

    username = await admin_users.get_username(chat_id)  # Вот здесь

    next_refresh = user_data.get("next_refresh_time")  
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

    raw_until = user_data.get("subscription_until")
    status_text = "приостановлен"
    display_until = None
    try:
        if not user_data.get("suspended") and raw_until:
            ts = int(float(raw_until))
            status_text = "активен"
            display_until = ts
    except Exception:
        status_text = "приостановлен"
        display_until = None
        
    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "chat_id": chat_id,
            "username": username,
            "next_refresh": next_refresh,
            "site_name": site_name,
            "profile_link": profile_link,
            "status": status_text,
            "display_until": display_until,
            "button_text": "🔄 Восстановить" if user_data.get("suspended") else "⏸ Приостановить",
            "tokens": None,
            "is_admin": True
        }
    )


@app_fastapi.post("/admin/users/{chat_id}/toggle_status")
async def admin_user_toggle_status(
    request: Request,
    chat_id: int,
    _: None = Depends(admin_required)
):
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return HTMLResponse("<h2>Пользователь не найден</h2>", status_code=404)

    # Снимаем подписку
    user_data["suspended"] = True
    _save_to_redis_partial(chat_id, {"suspended": True})

    # Отправляем уведомление пользователю
    try:
        await send_message_to_user(
            bot,
            chat_id,
            "⏸ Ваша подписка приостановлена! Доступ закрыт.\n\n Для решения данных вопросов обращайтесь к администратору.",
            reply_markup=ReplyKeyboardMarkup([["Активировать доступ"]], resize_keyboard=True)
        )
    except Exception as e:
        print(f"Ошибка при уведомлении пользователя {chat_id}: {e}")

    return RedirectResponse(f"/admin/users/{chat_id}", status_code=303)

@app_fastapi.post("/admin/users/{chat_id}/restore_subscription_custom")
async def restore_custom(request: Request, chat_id: int, _: None = Depends(admin_required)):
    form = await request.form()
    local_str = form["local_datetime"]
    tz_name = form["tz"]

    local_dt = datetime.fromisoformat(local_str)
    local_dt = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    utc_ts = int(local_dt.astimezone(timezone.utc).timestamp())

    user = RAM_DATA.get(chat_id)
    if not user:
        return JSONResponse({"error": "Not found"}, status_code=404)

    user["subscription_until"] = utc_ts
    user["suspended"] = False

    _save_to_redis_partial(chat_id, {
        "subscription_until": utc_ts,
        "suspended": False
    })

    # ---------------------------
    # Уведомление пользователю
    MSK = timezone(timedelta(hours=3))
    local_dt_msk = datetime.fromtimestamp(utc_ts, tz=timezone.utc).astimezone(MSK)
    subscription_text = local_dt_msk.strftime("%d.%m.%Y %H:%M") + " МСК"

    # создаём клавиатуру, так как подписка была неактивна
    await send_message_to_user(
        bot,
        chat_id,
        f"✅ Подписка активирована! Доступ открыт до {subscription_text}",
        reply_markup=build_reply_keyboard(chat_id)
    )

    return JSONResponse({"ok": True})


@app_fastapi.post("/admin/users/{chat_id}/extend_subscription_custom")
async def extend_custom(request: Request, chat_id: int, _: None = Depends(admin_required)):
    form = await request.form()
    local_str = form["local_datetime"]
    tz_name = form["tz"]

    local_dt = datetime.fromisoformat(local_str)
    local_dt = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    utc_ts = int(local_dt.astimezone(timezone.utc).timestamp())

    user = RAM_DATA.get(chat_id)
    if not user:
        return JSONResponse({"error": "Not found"}, status_code=404)

    current = float(user.get("subscription_until", 0))
    final = max(current, utc_ts)
    user["subscription_until"] = final
    user["suspended"] = False

    _save_to_redis_partial(chat_id, {
        "subscription_until": final,
        "suspended": False
    })

    # ---------------------------
    # Уведомление пользователю
    MSK = timezone(timedelta(hours=3))
    local_dt_msk = datetime.fromtimestamp(final, tz=timezone.utc).astimezone(MSK)
    subscription_text = local_dt_msk.strftime("%d.%m.%Y %H:%M") + " МСК"

    # не создаём клавиатуру, так как она уже есть
    await send_message_to_user(
        bot,
        chat_id,
        f"✅ Подписка продлена! Доступ открыт до {subscription_text}"
    )

    return JSONResponse({"ok": True})
    
@app_fastapi.post("/admin/users/{chat_id}/tokens")
async def admin_user_tokens_json(
    chat_id: int,
    _: None = Depends(admin_required)
):
    """
    Возвращает токены пользователя в формате JSON для AJAX-запроса.
    """
    user_data = admin_users.RAM_DATA.get(chat_id)
    if not user_data:
        return JSONResponse({"error": "Пользователь не найден"}, status_code=404)

    tokens = {
        "access_token": user_data.get("access_token", ""),
        "refresh_token": user_data.get("refresh_token", "")
    }

    return JSONResponse(tokens)

# -----------------------
# Admin Keys
@app_fastapi.get("/admin/keys", response_class=HTMLResponse)
async def admin_keys_page(
    request: Request,
    _: None = Depends(admin_required)
):
    return templates.TemplateResponse(
        "admin/keys.html",
        {"request": request, "durations": KEY_DURATION_OPTIONS, "key": None, "is_admin": True}
    )

@app_fastapi.post("/admin/keys/generate", response_class=HTMLResponse)
async def admin_generate_key(
    request: Request,
    duration: int = Form(...),
    _: None = Depends(admin_required)
):
    label, delta = KEY_DURATION_OPTIONS[duration]
    key = generate_key(delta)
    return templates.TemplateResponse(
        "admin/keys.html",
        {"request": request, "durations": KEY_DURATION_OPTIONS, "key": key, "is_admin": True}
    )

@app_fastapi.get("/admin/stats", response_class=HTMLResponse)
async def get_post_stats(
    request: Request,
    _: None = Depends(admin_required)
):
    stats = RAM_DATA.get("last_post_stats")
    if not stats:
        return HTMLResponse("<h2>Данных нет</h2>", status_code=404)

    # Пробегаем по каждому пользователю и обновляем username
    for user in stats:
        chat_id = user.get("chat_id")
        user["username"] = await admin_users.get_username(chat_id)

    return templates.TemplateResponse(
        "admin/stats.html",
        {"request": request, "stats": stats}
    )

from fastapi.responses import HTMLResponse

@app_fastapi.get("/admin/notify", response_class=HTMLResponse)
async def notify_page(request: Request, _: None = Depends(admin_required)):
    return templates.TemplateResponse("admin/notify.html", {"request": request, "is_admin": True})
    
@app_fastapi.get("/admin/search_users")
async def search_users(q: str, _: None = Depends(admin_required)):
    results = []
    for uid, user in RAM_DATA.items():
        if q.lower() in str(uid) or q.lower() in (user.get("username","").lower()) or q.lower() in (user.get("display_name","").lower()):
            results.append({"chat_id": uid, "username": user.get("username"), "display_name": user.get("display_name")})
    return JSONResponse(results)

@app_fastapi.post("/admin/notify")
async def send_notification(
    request: Request,
    recipient_type: str = Form(...),  # "all" или "single"
    target_user: str = Form(None),
    message: str = Form(...),
    _: None = Depends(admin_required)
):
    if recipient_type == "all":
        for uid, user_data in RAM_DATA.items():
            # если user_data это список, перебираем его
            if isinstance(user_data, list):
                for u in user_data:
                    try:
                        await admin_users.bot.send_message(u["chat_id"], message)
                    except:
                        pass
            else:
                try:
                    await admin_users.bot.send_message(uid, message)
                except:
                    pass

    elif recipient_type == "single":
        target_uid = None
        for uid, user_data in RAM_DATA.items():
            users_to_check = user_data if isinstance(user_data, list) else [user_data]
            for user in users_to_check:
                if str(uid) == target_user or str(user.get("chat_id")) == target_user or user.get("username") == target_user:
                    target_uid = user.get("chat_id", uid)
                    break
            if target_uid:
                break

        if not target_uid:
            return JSONResponse({"error": "Пользователь не найден"}, status_code=404)

        try:
            await admin_users.bot.send_message(target_uid, message)
        except:
            return JSONResponse({"error": "Не удалось отправить сообщение"}, status_code=500)

    return JSONResponse({"status": "ok"})
    
# -----------------------
# Фоновые задачи
async def keep_alive():
    import aiohttp
    while True:
        await asyncio.sleep(240 + random.random() * 120)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SELF_URL}/healthz") as resp:
                    print(f"Keep-alive ping: {resp.status}")
        except Exception as e:
            print(f"Keep-alive error: {e}")

async def run_token_refresher():
    asyncio.create_task(token_refresher_loop(bot))
    print("Фоновый таймер обновления токенов запущен.")

async def start_telegram():
    print("Запуск Telegram-бота...")
    await tg_app.initialize()
    await tg_app.start()
    await client.start()
    print("Telethon клиент запущен.")
    await tg_app.updater.start_polling()
    await client.run_until_disconnected()

# -----------------------
# Startup
@app_fastapi.on_event("startup")
async def startup_event():
    asyncio.create_task(keep_alive())
    asyncio.create_task(run_token_refresher())
    asyncio.create_task(subscription_watcher(bot, send_message_to_user))
    asyncio.create_task(start_telegram())