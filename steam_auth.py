from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"


# 1️⃣ Точка входа: даём пользователю ссылку на Steam через cs2run
@router.get("/auth/login")
async def auth_login(chat_id: int):
    import aiohttp
    import urllib.parse
    final_return = f"{SELF_URL}/auth/steam?chat_id={chat_id}"
    encoded_return = urllib.parse.quote(final_return, safe='')  # ⚠️ важно: закодировать полностью
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/get-url/",
            params={"return_url": encoded_return}
        ) as r:
            data = await r.json()
    
    steam_url = data["data"]["url"]
    return RedirectResponse(steam_url)


# 2️⃣ Точка, куда Steam вернёт пользователя после логина
@router.get("/auth/steam")
async def auth_steam(request, chat_id: int = Query(...)):
    # Здесь уже реально придут параметры от Steam после логина
    steam_params = dict(request.query_params)
    print(f"\n🧪 STEAM CALLBACK PARAMS for chat {chat_id}:\n", steam_params, "\n")

    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        f"<h2>Steam вернул параметры:</h2><pre>{steam_params}</pre>"
    )