from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import urllib.parse
import json
import httpx

from main import RAM_DATA
from steam_headless import fetch_steam_tokens

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# -------------------------------
# 1️⃣ Login → CS2RUN → Steam
# -------------------------------
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Пользователь нажимает "Войти через Steam".
    Получаем ссылку на Steam через CS2RUN и редиректим пользователя.
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
    Получаем OpenID параметры от Steam после редиректа.
    Передаём их в headless модуль CS2RUN для финального получения токенов.
    """
    query_params = dict(request.query_params)
    print("\n🧪 CALLBACK PARAMS:", query_params)

    try:
        # Серверный headless завершаем авторизацию
        tokens = await fetch_steam_tokens(query_params)

        # Сохраняем токены в RAM_DATA
        if chat_id not in RAM_DATA:
            RAM_DATA[chat_id] = {}
        RAM_DATA[chat_id]["access_token"] = tokens.get("token")
        RAM_DATA[chat_id]["refresh_token"] = tokens.get("refreshToken")

        print(f"\n🔥 Tokens saved for chat {chat_id}:", RAM_DATA[chat_id])

        # Страница для пользователя
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Авторизация завершена</title></head>
        <body>
        <h3>✅ Авторизация завершена!</h3>
        <p>Вы можете закрыть это окно.</p>
        </body>
        </html>
        """)

    except Exception as e:
        print(f"❌ Headless auth failed for chat {chat_id}: {e}")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка авторизации</title></head>
        <body>
        <h3>❌ Ошибка авторизации: {e}</h3>
        <p>Попробуйте ещё раз</p>
        </body>
        </html>
        """)