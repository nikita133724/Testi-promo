from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import aiohttp

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"
RAM_DATA = {}


@router.get("/auth/login")
async def auth_login(chat_id: int = Query(...)):
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    api_url = "https://cs2run.app/auth/1/get-url/"

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, params={"return_url": return_url}) as resp:
            data = await resp.json()
            steam_url = data.get("data", {}).get("url")
            return RedirectResponse(steam_url)


@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    openid_query = request.url.query

    redirect_url = (
        f"https://cs2run.app/auth/1/start-sign-in/"
        f"?{openid_query}&returnUrl={SELF_URL}/auth/final?chat_id={chat_id}"
    )

    return RedirectResponse(redirect_url)


@router.get("/auth/final")
async def auth_final(request: Request, chat_id: int = Query(...)):
    auth_token = request.cookies.get("auth-token")

    if not auth_token:
        return HTMLResponse("<h2>Ошибка: auth-token не получен</h2>")

    print(f"\n[SUCCESS] Chat {chat_id} auth-token: {auth_token}\n")

    headers = {"Cookie": f"auth-token={auth_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://cs2run.app/current-state", headers=headers) as resp:
            state = await resp.json()

    print(f"[STATE] {state}\n")

    RAM_DATA[chat_id] = {
        "auth_token": auth_token,
        "state": state
    }

    return HTMLResponse("<h2>Готово. Авторизация завершена.</h2>")