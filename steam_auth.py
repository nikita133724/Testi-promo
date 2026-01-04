# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
import aiohttp

import urllib.parse

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"  # твой сервер
RAM_DATA = {}

# -----------------------------
# 1️⃣ Ссылка на вход через Steam
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Даём пользователю ссылку на Steam через cs2run.
    После Steam редиректит на /auth/callback
    """
    final_return = f"{SELF_URL}/auth/callback?chat_id={chat_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/get-url/",
            params={"return_url": final_return}
        ) as r:
            data = await r.json()

    steam_url = data["data"]["url"]
    # Перенаправляем пользователя прямо на Steam
    return RedirectResponse(steam_url)

# -----------------------------
# 2️⃣ Редирект для старой ссылки /auth/steam
@router.get("/auth/steam")
async def auth_steam_redirect(chat_id: int = Query(...)):
    """
    Просто редиректим на /auth/callback, чтобы 404 не было
    """
    return RedirectResponse(f"{SELF_URL}/auth/callback?chat_id={chat_id}")

# -----------------------------
# 3️⃣ Ловим параметры от Steam после логина
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    """
    Steam редиректит сюда после логина.
    Показываем все параметры OpenID в браузере.
    """
    steam_params = dict(request.query_params)
    print(f"\n🧪 STEAM CALLBACK PARAMS for chat {chat_id}:\n", steam_params)

    # Временно сохраняем в RAM
    RAM_DATA[chat_id] = steam_params

    # Показываем их в браузере
    html_content = "<h2>✅ Steam вернул следующие параметры OpenID:</h2><pre>{}</pre>".format(
        steam_params
    )
    return HTMLResponse(html_content)