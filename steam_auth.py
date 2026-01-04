from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import urllib.parse
import httpx
import json

from main import RAM_DATA
from steam_headless import fetch_steam_tokens_headless  # отдельная функция для headless

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# -------------------------------
# 1️⃣ Login → CS2RUN → Steam
# -------------------------------
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Пользователь нажимает "Войти через Steam".
    Получаем CS2RUN ссылку и редиректим на Steam.
    """
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    cs2run_api = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"

    async with httpx.AsyncClient() as client:
        r = await client.get(cs2run_api)
        data = r.json()

    steam_url = data.get("data", {}).get("url")
    if not steam_url:
        raise HTTPException(status_code=500, detail="❌ Не удалось получить ссылку на Steam")

    return RedirectResponse(steam_url)


# -------------------------------
# 2️⃣ Callback после Steam/CS2RUN
# -------------------------------
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    """
    Пользователь завершил авторизацию на Steam → CS2RUN callback.
    Отдаем простую страницу с инструкцией.
    """
    query_params = dict(request.query_params)
    print("🧪 CALLBACK PARAMS:", query_params)

    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Авторизация завершена</title></head>
    <body>
        <h3>✅ Авторизация Steam завершена!</h3>
        <p>Если используете Telegram WebApp, окно можно закрыть.</p>
    </body>
    </html>
    """
    return HTMLResponse(html)


# -------------------------------
# 3️⃣ Headless flow (сервер получает токены без пользователя)
# -------------------------------
@router.get("/auth/headless")
async def auth_headless(chat_id: int):
    """
    Headless flow: получаем токены напрямую через CS2RUN, без участия пользователя.
    """
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    cs2run_api = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"

    try:
        # 1. Получаем новый CS2RUN URL
        async with httpx.AsyncClient() as client:
            r = await client.get(cs2run_api)
            data = r.json()
        steam_url = data.get("data", {}).get("url")
        if not steam_url:
            raise HTTPException(status_code=500, detail="❌ Не удалось получить CS2RUN ссылку")

        # 2. Проходим headless flow через этот URL
        tokens = await fetch_steam_tokens_headless(steam_url)

        # 3. Сохраняем в RAM_DATA
        if chat_id not in RAM_DATA:
            RAM_DATA[chat_id] = {}
        RAM_DATA[chat_id]["access_token"] = tokens.get("token")
        RAM_DATA[chat_id]["refresh_token"] = tokens.get("refreshToken")

        print(f"🔥 Tokens saved for chat {chat_id}:", RAM_DATA[chat_id])
        return JSONResponse({"ok": True, "tokens": RAM_DATA[chat_id]})

    except Exception as e:
        print(f"❌ Headless auth failed for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))