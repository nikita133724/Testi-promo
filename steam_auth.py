# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"
RAM_DATA = {}

# 1️⃣ Ссылка на вход через Steam (открывает страницу Steam)
@router.get("/auth/login")
async def auth_login(chat_id: int):
    # URL, на который Steam вернёт пользователя после логина
    callback_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"

    # Формируем стандартную ссылку OpenID на Steam
    steam_url = (
        "https://steamcommunity.com/openid/login?"
        "openid.ns=http://specs.openid.net/auth/2.0&"
        "openid.mode=checkid_setup&"
        "openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select&"
        "openid.identity=http://specs.openid.net/auth/2.0/identifier_select&"
        f"openid.return_to={callback_url}&"
        "openid.realm=https://tg-bot-test-gkbp.onrender.com"
    )

    return RedirectResponse(steam_url)

# 2️⃣ Callback после входа в Steam
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    """
    Steam редиректит сюда после логина.
    Просто выводим все OpenID параметры Steam
    """
    steam_params = dict(request.query_params)
    print(f"\n🧪 STEAM CALLBACK PARAMS for chat {chat_id}:\n{steam_params}\n")

    # Сохраняем временно в RAM
    RAM_DATA[chat_id] = steam_params

    # Показываем параметры в браузере
    html_content = "<h2>✅ Параметры OpenID от Steam:</h2><pre>{}</pre>".format(
        steam_params
    )
    return HTMLResponse(html_content)