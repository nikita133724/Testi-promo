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
    # 1️⃣ Получаем openid параметры от Steam
    openid_params = dict(request.query_params)
    print(f"[DEBUG] Chat ID {chat_id} - OpenID params from Steam callback:", openid_params)

    # 2️⃣ Создаём сессию aiohttp, передаём cookies пользователя (из запроса)
    async with aiohttp.ClientSession() as session:
        # 3️⃣ Делаем GET к cs2run, имитируя браузер
        start_sign_in_url = "https://cs2run.app/auth/1/start-sign-in/"
        async with session.get(start_sign_in_url, params=openid_params) as resp:
            # 4️⃣ Читаем cookies, особенно auth-token
            auth_token = resp.cookies.get("auth-token")
            if auth_token:
                auth_token = auth_token.value
                print(f"[DEBUG] Chat ID {chat_id} - auth-token (JWT): {auth_token}")
            else:
                print(f"[DEBUG] Chat ID {chat_id} - auth-token не получен")
            
            # 5️⃣ Дополнительно можно вызвать current-state, если нужно centrifugeToken и user info
            headers = {"Cookie": f"auth-token={auth_token}"} if auth_token else {}
            async with session.get("https://cs2run.app/current-state", headers=headers) as state_resp:
                try:
                    state_data = await state_resp.json()
                    print(f"[DEBUG] Chat ID {chat_id} - current-state:", state_data)
                except Exception:
                    print(f"[DEBUG] Chat ID {chat_id} - не удалось получить current-state")

    # 6️⃣ RAM_DATA для временного хранения
    RAM_DATA.setdefault(chat_id, {})["auth_token"] = auth_token
    RAM_DATA[chat_id]["current_state"] = state_data if 'state_data' in locals() else None

    return HTMLResponse(f"<h2>Авторизация завершена для Telegram ID {chat_id}</h2>"
                        f"<p>Токены выведены в лог сервера.</p>")