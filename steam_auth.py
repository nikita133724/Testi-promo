# steam_auth.py
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import urllib.parse
import json

from main import RAM_DATA  # <-- твой словарь для хранения токенов
from steam_headless import fetch_steam_tokens  # headless браузер

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# -------------------------------
# 1️⃣ Login → CS2RUN → Steam
# -------------------------------
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Пользователь нажимает "Войти через Steam".
    Редиректим на CS2RUN для генерации ссылки на Steam.
    """
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    cs2run_url = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"
    return RedirectResponse(cs2run_url)


# -------------------------------
# 2️⃣ Callback после Steam/CS2RUN
# -------------------------------
@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    """
    Веб-страница, которая ждёт токены в localStorage.
    """
    query_params = dict(request.query_params)
    print("\n🧪 CALLBACK PARAMS:", query_params)

    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>Авторизация…</title></head>
<body>
<h3>🔐 Пожалуйста, дождитесь окончания авторизации</h3>
<p>После получения токенов окно закроется автоматически</p>

<script>
(async function() {{
    function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}

    let token, refresh;
    for(let i=0;i<20;i++){{
        token = localStorage.getItem("auth-token");
        refresh = localStorage.getItem("auth-refresh-token");
        if(token && refresh) break;
        await sleep(500);
    }}

    if(token && refresh){{
        await fetch('{SELF_URL}/bot/receive?chat_id={chat_id}', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ token, refresh }})
        }});

        document.body.innerHTML = "<h3>✅ Токены получены! Окно можно закрыть</h3>";
        if(window.Telegram?.WebApp) window.Telegram.WebApp.close();
    }} else {{
        document.body.innerHTML = "<h3>❌ Не удалось получить токены. Попробуйте еще раз</h3>";
    }}
}})();
</script>
</body>
</html>
""")


# -------------------------------
# 3️⃣ Сервер получает токены через headless браузер
# -------------------------------
@router.get("/auth/headless")
async def auth_headless(chat_id: int):
    """
    Headless flow: получаем токены без браузера пользователя.
    """
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    cs2run_url = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"

    try:
        tokens = await fetch_steam_tokens(cs2run_url)

        # Сохраняем токены сразу в RAM_DATA
        if chat_id not in RAM_DATA:
            RAM_DATA[chat_id] = {}
        RAM_DATA[chat_id]["access_token"] = tokens.get("token")
        RAM_DATA[chat_id]["refresh_token"] = tokens.get("refreshToken")

        print(f"\n🔥 Tokens saved for chat {chat_id}:", RAM_DATA[chat_id])

        return JSONResponse({
            "ok": True,
            "tokens": RAM_DATA[chat_id]
        })
    except Exception as e:
        print(f"❌ Headless auth failed for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------
# 4️⃣ Сервер принимает токены напрямую (из веба)
# -------------------------------
@router.post("/bot/receive")
async def receive_tokens(chat_id: int, payload: dict):
    """
    Получаем токены от веб-страницы и сохраняем в RAM_DATA
    """
    if chat_id not in RAM_DATA:
        RAM_DATA[chat_id] = {}

    RAM_DATA[chat_id]["access_token"] = payload.get("token") or payload.get("access_token")
    RAM_DATA[chat_id]["refresh_token"] = payload.get("refresh") or payload.get("refresh_token")

    print(f"\n🔥 GOT TOKENS FOR CHAT {chat_id}:\n", json.dumps(payload, indent=2))
    return {"ok": True}