# steam_auth_debug.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
import urllib.parse

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"
RAM_DATA = {}

# 1️⃣ Точка входа: даём пользователю ссылку на Steam через cs2run
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Пользователь получает ссылку Steam через cs2run
    """
    final_return = f"{SELF_URL}/auth/steam?chat_id={chat_id}"

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/get-url/",
            params={"return_url": final_return}
        ) as r:
            data = await r.json()

    steam_url = data.get("data", {}).get("url")
    if not steam_url:
        return {"error": "Не удалось получить ссылку Steam"}

    # Вернём URL для перехода (можно использовать RedirectResponse вместо JSON, если хочешь автоматический редирект)
    return {"redirect_url": steam_url}


# 2️⃣ Точка, куда Steam редиректит после логина
@router.get("/auth/steam")
async def auth_steam(request: Request, chat_id: int = Query(...)):
    """
    Здесь показываем все параметры, которые прислал Steam через openid
    """
    steam_params = dict(request.query_params)
    print(f"\n🧪 STEAM CALLBACK PARAMS (openid.*):\n{steam_params}\n")

    # Сохраняем временно для отладки
    RAM_DATA[chat_id] = {"steam_params": steam_params}

    # Показываем пользователю
    html = "<h2>Steam вернул следующие параметры:</h2><pre>{}</pre>".format(
        urllib.parse.unquote(str(steam_params))
    )
    return HTMLResponse(html)