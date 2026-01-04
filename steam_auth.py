# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
import urllib.parse

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# 1️⃣ Вход → Steam
@router.get("/auth/login")
async def auth_login(chat_id: int):
    callback_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"

    steam_url = (
        "https://steamcommunity.com/openid/login?"
        "openid.ns=http://specs.openid.net/auth/2.0&"
        "openid.mode=checkid_setup&"
        "openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select&"
        "openid.identity=http://specs.openid.net/auth/2.0/identifier_select&"
        f"openid.return_to={urllib.parse.quote(callback_url)}&"
        f"openid.realm={urllib.parse.quote(SELF_URL)}"
    )

    return RedirectResponse(steam_url)


# 2️⃣ Возврат со Steam → сразу в cs2run
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):

    steam_params = dict(request.query_params)

    print(f"\n🧪 STEAM CALLBACK PARAMS:\n{steam_params}\n")

    # Куда пользователь попадёт уже залогиненным
    final_url = "https://csgoyz.run/auth"

    # Собираем запрос к cs2run
    query = {
        "returnUrl": final_url,
        **steam_params
    }

    encoded = urllib.parse.urlencode(query, safe=":/")

    redirect_url = f"https://cs2run.app/auth/1/start-sign-in/?{encoded}"

    print("\n🚀 REDIRECT TO CS2RUN:\n", redirect_url, "\n")

    return RedirectResponse(redirect_url)