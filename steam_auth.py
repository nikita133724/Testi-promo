from fastapi import APIRouter
from fastapi.responses import RedirectResponse, JSONResponse
from csgoyz_auth import fetch_csgoyz_tokens
from main import RAM_DATA

router = APIRouter()

CLIENTS = {}

@router.get("/auth/test")
async def auth_test(chat_id: int):
    steam_url, client = await fetch_csgoyz_tokens(chat_id)
    CLIENTS[chat_id] = client
    return RedirectResponse(steam_url)


@router.get("/auth/finish")
async def auth_finish(chat_id: int):
    client = CLIENTS.pop(chat_id)

    # Берём cookies после всех редиректов
    cookies = client.cookies

    access = cookies.get("auth-token")
    refresh = cookies.get("auth-refresh-token")

    if not access or not refresh:
        return JSONResponse({"error": "Токены не получены"})

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access_token"] = access
    RAM_DATA[chat_id]["refresh_token"] = refresh

    return JSONResponse({
        "ok": True,
        "access_token": access,
        "refresh_token": refresh
    })