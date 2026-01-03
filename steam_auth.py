# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
import aiohttp
import urllib.parse

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"  # твой сервер
RAM_DATA = {}  # временно для логов

@router.get("/auth/login")
async def auth_login(chat_id: int = Query(...)):
    """
    1️⃣ Генерация ссылки Steam/OpenID через cs2run
    """
    # Ссылка на callback на твоём сервере
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    api_url = "https://cs2run.app/auth/1/get-url/"
    params = {"return_url": return_url}

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, params=params) as resp:
            data = await resp.json()
            steam_url = data.get("data", {}).get("url")
            if not steam_url:
                return JSONResponse({"error": "Не удалось получить ссылку на Steam"}, status_code=500)

            # Перенаправляем пользователя на Steam
            return RedirectResponse(steam_url)


@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    """
    2️⃣ Callback после входа через Steam
    """
    # Получаем все параметры OpenID от Steam
    openid_params = dict(request.query_params)
    print(f"[DEBUG] Chat ID {chat_id} - OpenID params from Steam callback:", openid_params)

    # 3️⃣ Запрос к cs2run /start-sign-in/ для получения токенов
    start_sign_in_url = "https://cs2run.app/auth/1/start-sign-in/"

    # Важно: передаём **все параметры OpenID**
    async with aiohttp.ClientSession() as session:
        async with session.get(start_sign_in_url, params=openid_params) as resp:
            try:
                data = await resp.json()
            except Exception:
                return JSONResponse({"error": "Не удалось распарсить ответ cs2run"}, status_code=500)

    # Извлекаем токены cs2run
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if access_token and refresh_token:
        print(f"[DEBUG] Chat ID {chat_id} - access_token: {access_token}")
        print(f"[DEBUG] Chat ID {chat_id} - refresh_token: {refresh_token}")
    else:
        print(f"[DEBUG] Chat ID {chat_id} - токены не получены, ответ cs2run:", data)

    # Временное сохранение в RAM_DATA
    RAM_DATA.setdefault(chat_id, {})["access_token"] = access_token
    RAM_DATA[chat_id]["refresh_token"] = refresh_token

    return HTMLResponse(f"<h2>Авторизация завершена для Telegram ID {chat_id}</h2>"
                        f"<p>Токены выведены в лог сервера.</p>")