from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
import aiohttp

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"
RAM_DATA = {}


# 1️⃣ Точка входа: даём пользователю ссылку на Steam через cs2run
@router.get("/auth/login")
async def auth_login(chat_id: int):
    import urllib.parse

    # Финальный callback, куда мы вернёмся после авторизации
    final_return = f"{SELF_URL}/auth/steam?chat_id={chat_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/get-url/",
            params={"return_url": final_return}
        ) as r:
            data = await r.json()

    steam_url = data["data"]["url"]
    return {"redirect_url": steam_url}


# 2️⃣ Точка, куда Steam редиректит после логина
@router.get("/auth/steam")
async def auth_steam(request: Request, chat_id: int = Query(...)):
    import urllib.parse

    steam_params = dict(request.query_params)
    print(f"\n🧪 STEAM CALLBACK PARAMS:\n{steam_params}\n")

    # POST к cs2run /auth/1/sign-in для получения токенов
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://cs2run.app/auth/1/sign-in",
            json=steam_params
        ) as resp:
            try:
                data = await resp.json()
            except Exception:
                return HTMLResponse("<h2>❌ Ошибка: не удалось получить токены</h2>")

    # Извлекаем токены
    access_token = data.get("data", {}).get("token")
    refresh_token = data.get("data", {}).get("refreshToken")
    one_time_token = data.get("data", {}).get("oneTimeToken")
    user_id = data.get("data", {}).get("userId")

    if not access_token:
        return HTMLResponse(f"<h2>❌ Ошибка: токены не получены</h2><pre>{data}</pre>")

    # Логируем и сохраняем временно
    print(f"\n🔥 [SUCCESS] Chat {chat_id} tokens:\nAccess: {access_token}\nRefresh: {refresh_token}\nOneTime: {one_time_token}\nUserID: {user_id}\n")

    RAM_DATA[chat_id] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "one_time_token": one_time_token,
        "user_id": user_id
    }

    return HTMLResponse("<h2>✅ Авторизация завершена. Токены выведены в консоль сервера.</h2>")