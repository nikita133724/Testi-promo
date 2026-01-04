# steam_auth.py
from fastapi import APIRouter, Query
import httpx
import urllib.parse
import json

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"


# -------------------------------
# 1️⃣ Login → Steam → CS2RUN
# -------------------------------
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Генерируем ссылку на Steam OpenID через CS2RUN,
    чтобы пользователь мог войти через Steam.
    """
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    cs2run_get_url = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"
    return {"cs2run_url": cs2run_get_url}


# -------------------------------
# 2️⃣ Callback после Steam
# -------------------------------
@router.get("/auth/callback")
async def auth_callback(
    chat_id: int,
    openid_ns: str = Query(..., alias="openid.ns"),
    openid_mode: str = Query(..., alias="openid.mode"),
    openid_op_endpoint: str = Query(..., alias="openid.op_endpoint"),
    openid_claimed_id: str = Query(..., alias="openid.claimed_id"),
    openid_identity: str = Query(..., alias="openid.identity"),
    openid_return_to: str = Query(..., alias="openid.return_to"),
    openid_response_nonce: str = Query(..., alias="openid.response_nonce"),
    openid_assoc_handle: str = Query(..., alias="openid.assoc_handle"),
    openid_signed: str = Query(..., alias="openid.signed"),
    openid_sig: str = Query(..., alias="openid.sig")
):
    """
    Получаем параметры OpenID от Steam.
    Делаем POST к CS2RUN для получения токенов.
    """
    openid_params = {
        "openid.ns": openid_ns,
        "openid.mode": openid_mode,
        "openid.op_endpoint": openid_op_endpoint,
        "openid.claimed_id": openid_claimed_id,
        "openid.identity": openid_identity,
        "openid.return_to": openid_return_to,
        "openid.response_nonce": openid_response_nonce,
        "openid.assoc_handle": openid_assoc_handle,
        "openid.signed": openid_signed,
        "openid.sig": openid_sig
    }

    # Делаем POST к CS2RUN
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://cs2run.app/auth/1/sign-in",
            json=openid_params,
        )
        if resp.status_code != 200:
            return {"error": "Failed to fetch tokens from CS2RUN", "status": resp.status_code}

        data = resp.json()  # Тут уже токены
        tokens = data.get("data", {})

        # Отправляем токены на сервер для бота
        await client.post(
            f"{SELF_URL}/bot/receive?chat_id={chat_id}",
            json=tokens
        )

    return {"ok": True, "message": "Tokens fetched and sent to bot", "tokens": tokens}


# -------------------------------
# 3️⃣ Сервер принимает токены
# -------------------------------
@router.post("/bot/receive")
async def receive_tokens(chat_id: int, payload: dict):
    """
    Получаем токены от CS2RUN для использования в боте.
    """
    print(f"\n🔥 GOT TOKENS FOR CHAT {chat_id}:\n", json.dumps(payload, indent=2))
    # Здесь можно положить токены в RAM или в базу
    return {"ok": True}