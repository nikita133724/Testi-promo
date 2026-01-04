from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

router = APIRouter()

SELF = "https://tg-bot-test-gkbp.onrender.com"
RAM_DATA = {}

# 1️⃣ старт авторизации
@router.get("/auth/start")
async def auth_start(chat_id: int):
    """
    Пользователь открывает ссылку → редирект на csgoyz.run с параметром tg_callback,
    который указывает на наш endpoint /auth/receive
    """
    tg_callback = f"{SELF}/auth/receive?chat_id={chat_id}"
    csgoyz_url = f"https://csgoyz.run/?tg_callback={tg_callback}"
    return RedirectResponse(csgoyz_url)


# 2️⃣ приём токенов
@router.post("/auth/receive")
async def auth_receive(request: Request, chat_id: int):
    """
    Сюда csgoyz.run отправляет токены после авторизации пользователя.
    """
    data = await request.json()

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access"] = data.get("token")
    RAM_DATA[chat_id]["refresh"] = data.get("refresh")

    print("🔥 TOKENS:", chat_id, RAM_DATA[chat_id])
    return JSONResponse({"ok": True})