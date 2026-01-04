# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
import aiohttp

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"  # твой сервер
RAM_DATA = {}

# ---------------------
# 1️⃣ Точка входа: даём ссылку пользователю
# ---------------------
@router.get("/auth/login")
async def auth_login(chat_id: int = Query(...)):
    """
    Возвращаем ссылку Steam через cs2run
    """
    final_return = f"{SELF_URL}/auth/final?chat_id={chat_id}"  # куда cs2run вернёт после Steam

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/get-url/",
            params={"return_url": final_return}
        ) as r:
            data = await r.json()
            if not data.get("data") or not data["data"].get("url"):
                return JSONResponse({"error": "Не удалось получить ссылку Steam"}, status_code=500)
            steam_url = data["data"]["url"]

    # Перенаправляем пользователя на Steam
    return RedirectResponse(steam_url)


# ---------------------
# 2️⃣ Финальная точка после Steam + cs2run
# ---------------------
@router.get("/auth/final")
async def auth_final(request: Request, chat_id: int = Query(...)):
    """
    Steam редиректит сюда через cs2run (openid.* параметры уже в query)
    """
    openid_params = dict(request.query_params)
    print(f"\n🧪 OPENID CALLBACK PARAMS: {openid_params}\n")

    # 1️⃣ Если openid_params пустые — ошибка
    if len(openid_params) <= 1:  # обычно там как минимум chat_id
        return HTMLResponse("<h2>❌ Ошибка: openid параметры не получены</h2>")

    # 2️⃣ Отправляем параметры в cs2run /start-sign-in/
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/start-sign-in/",
            params=openid_params
        ) as r:
            try:
                data = await r.json()
            except Exception:
                return HTMLResponse("<h2>❌ Ошибка: не удалось распарсить ответ cs2run</h2>")

    # 3️⃣ Извлекаем токены
    auth_token = data.get("data", {}).get("token")
    refresh_token = data.get("data", {}).get("refreshToken")
    one_time_token = data.get("data", {}).get("oneTimeToken")

    if not auth_token:
        return HTMLResponse(f"<h2>❌ Токены не получены</h2><pre>{data}</pre>")

    # 4️⃣ Сохраняем временно
    RAM_DATA[chat_id] = {
        "auth_token": auth_token,
        "refresh_token": refresh_token,
        "one_time_token": one_time_token
    }

    print(f"\n🔥 Chat {chat_id} TOKENS:\n{RAM_DATA[chat_id]}\n")

    return HTMLResponse("<h2>✅ Авторизация завершена. Токены выведены в лог сервера.</h2>")