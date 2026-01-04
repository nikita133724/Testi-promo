# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
import json

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"


# -------------------------------
# 1️⃣ Login → CS2RUN → Steam
# -------------------------------
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Пользователь нажимает "Войти через Steam" в боте.
    Сначала редиректим на cs2run.app/get-url для генерации ссылки на Steam.
    """
    cs2run_url = f"https://cs2run.app/auth/1/get-url/?return_url={SELF_URL}/auth/callback?chat_id={chat_id}"
    return RedirectResponse(cs2run_url)


# -------------------------------
# 2️⃣ Callback после Steam / CS2RUN
# -------------------------------
@router.get("/auth/callback")
async def auth_callback(chat_id: int):
    """
    Пользователь вернулся с Steam → CS2RUN.
    Отдаем страницу, которая ждёт токены в localStorage.
    """
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
        console.log("🔥 Tokens found:", token, refresh);

        await fetch('{SELF_URL}/bot/receive?chat_id={chat_id}', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ token, refresh }})
        }});

        document.body.innerHTML = "<h3>✅ Токены получены! Окно можно закрыть</h3>";

        // Если открыто в Telegram WebApp
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
# 3️⃣ Сервер принимает токены
# -------------------------------
@router.post("/bot/receive")
async def receive_tokens(chat_id: int, payload: dict):
    """
    Получаем токены, чтобы бот мог действовать от имени пользователя.
    """
    print(f"\n🔥 GOT TOKENS FOR CHAT {chat_id}:\n", json.dumps(payload, indent=2))
    # Здесь можно положить токены в RAM или в базу
    return {"ok": True}