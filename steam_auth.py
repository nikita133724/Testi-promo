# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
import aiohttp

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"  # <- твой домен для теста
RAM_DATA = {}  # пока просто в логах

@router.get("/auth/login")
async def auth_login(chat_id: int = Query(...)):
    """Генерируем ссылку на Steam/OpenID авторизацию"""
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    api_url = "https://cs2run.app/auth/1/get-url/"
    params = {"return_url": return_url}

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, params=params) as resp:
            data = await resp.json()
            steam_url = data.get("data", {}).get("url")
            if not steam_url:
                return JSONResponse({"error": "Не удалось получить ссылку на Steam"}, status_code=500)
            return RedirectResponse(steam_url)


@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    params = dict(request.query_params)
    print("Params from Steam callback:", params)
    start_sign_in_url = "https://cs2run.app/auth/1/start-sign-in/"

    async with aiohttp.ClientSession() as session:
        async with session.get(start_sign_in_url, params=params) as resp:
            try:
                data = await resp.json()
            except Exception:
                return JSONResponse({"error": "Не удалось распарсить ответ cs2run"}, status_code=500)

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if access_token and refresh_token:
        print(f"[DEBUG] Chat ID {chat_id} access_token: {access_token}")
        print(f"[DEBUG] Chat ID {chat_id} refresh_token: {refresh_token}")
    else:
        print(f"[DEBUG] Chat ID {chat_id} токены не получены, ответ cs2run: {data}")

    # Сохраняем в RAM_DATA на всякий случай (пока не используем)
    RAM_DATA.setdefault(chat_id, {})["access_token"] = access_token
    RAM_DATA[chat_id]["refresh_token"] = refresh_token

    return HTMLResponse(f"<h2>Авторизация завершена для Telegram ID {chat_id}</h2>"
                        f"<p>Токены выведены в консоль сервера.</p>")