from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import urllib.parse

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"
RAM_DATA = {}


# 1️⃣ Точка входа: даём пользователю ссылку
@router.get("/auth/login")
async def auth_login(chat_id: int):
    import aiohttp

    # ЭТО — финальная точка, куда cs2run вернёт пользователя
    final_return = f"{SELF_URL}/auth/final?chat_id={chat_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://cs2run.app/auth/1/get-url/",
            params={"return_url": final_return}
        ) as r:
            data = await r.json()

    steam_url = data["data"]["url"]
    return RedirectResponse(steam_url)

# 2️⃣ Сюда cs2run + Steam возвращают пользователя
@router.get("/auth/steam")
async def auth_steam(request: Request, chat_id: int = Query(...)):
    # Все параметры OpenID от Steam
    steam_query = request.url.query
    print("\n🧪 STEAM CALLBACK PARAMS:\n", steam_query, "\n")

    # Куда cs2run должен вернуть пользователя ПОСЛЕ установки cookie
    final_return = f"{SELF_URL}/auth/final?chat_id={chat_id}"
    final_return = urllib.parse.quote(final_return)

    # Передаём параметры обратно cs2run
    redirect_url = (
        f"https://cs2run.app/auth/1/start-sign-in/"
        f"?{steam_query}&returnUrl={final_return}"
    )

    return RedirectResponse(redirect_url)


# 3️⃣ Финальная точка — тут у тебя уже есть JWT
@router.get("/auth/final")
async def auth_final(request: Request, chat_id: int):
    auth_token = request.cookies.get("auth-token")

    if not auth_token:
        return HTMLResponse("❌ auth-token не получен")

    print(f"\n🔥 AUTH TOKEN FOR {chat_id}:\n{auth_token}\n")

    return HTMLResponse("✅ Авторизация завершена, можно закрыть страницу.")