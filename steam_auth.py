from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

router = APIRouter()

SELF = "https://tg-bot-test-gkbp.onrender.com"

RAM_DATA = {}

# 1️⃣ старт авторизации
@router.get("/auth/start")
async def auth_start(chat_id: int):
    redirect = (
        "https://csgoyz.run/?"
        f"tg_callback={SELF}/auth/receive?chat_id={chat_id}"
    )
    return RedirectResponse(redirect)


# 2️⃣ приём токенов
@router.post("/auth/receive")
async def auth_receive(request: Request, chat_id: int):
    data = await request.json()

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access"] = data["token"]
    RAM_DATA[chat_id]["refresh"] = data["refresh"]

    print("🔥 TOKENS:", chat_id, RAM_DATA[chat_id])
    return JSONResponse({"ok": True})