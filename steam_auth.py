from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"


# 1️⃣ Точка входа: даём пользователю ссылку на Steam через cs2run
@router.get("/auth/login")
async def auth_login(chat_id: int):
    import aiohttp, urllib.parse

    # Финальная точка, куда вернёмся после Steam
    final_return = f"{SELF_URL}/auth/steam?chat_id={chat_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/get-url/",
            params={"return_url": final_return}
        ) as r:
            data = await r.json()

    steam_url = data["data"]["url"]
    # Возвращаем ссылку на Steam
    return {"redirect_url": steam_url}


# 2️⃣ Точка, куда Steam редиректит после логина
@router.get("/auth/steam")
async def auth_steam(request: Request, chat_id: int = Query(...)):
    # Смотрим все параметры, которые Steam прислал
    steam_params = dict(request.query_params)
    print(f"\n🧪 STEAM CALLBACK PARAMS for chat {chat_id}:\n", steam_params, "\n")

    # Показываем их на странице
    html = "<h2>Steam вернул следующие параметры:</h2><pre>{}</pre>".format(
        steam_params
    )
    return HTMLResponse(html)