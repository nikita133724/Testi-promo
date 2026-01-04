from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import urllib.parse
import httpx
import json

from main import RAM_DATA

router = APIRouter()
SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# -------------------------------
# 1️⃣ Login → CS2RUN → Steam
# -------------------------------
@router.get("/auth/login")
async def auth_login(chat_id: int):
    """
    Пользователь нажимает "Войти через Steam".
    Получаем ссылку через CS2RUN и редиректим.
    """
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    cs2run_api = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"

    async with httpx.AsyncClient() as client:
        r = await client.get(cs2run_api)
        data = r.json()

    steam_url = data.get("data", {}).get("url")
    if not steam_url:
        raise HTTPException(status_code=500, detail="❌ Не удалось получить ссылку на Steam")

    return RedirectResponse(steam_url)


# -------------------------------
# 2️⃣ Callback после Steam → CS2RUN → csgoyz.run
# -------------------------------
@router.get("/auth/callback")
async def auth_callback(chat_id: int):
    """
    После редиректа с csgoyz.run. Ждём появления токенов в localStorage
    и отправляем их на сервер.
    """
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>Авторизация Steam</title></head>
<body>
<h3>🔐 Пожалуйста, дождитесь окончания авторизации...</h3>
<p>После получения токенов окно закроется автоматически.</p>

<script>
(async function() {{
    function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}

    let token, refresh;
    for(let i = 0; i < 40; i++){{  // ждём до 20 секунд
        token = localStorage.getItem("auth-token");
        refresh = localStorage.getItem("auth-refresh-token");
        if(token && refresh) break;
        await sleep(500);
    }}

    if(token && refresh){{
        await fetch('{SELF_URL}/auth/save?chat_id={chat_id}', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ token, refresh }})
        }});

        document.body.innerHTML = "<h3>✅ Токены получены! Можете закрыть окно.</h3>";
    }} else {{
        document.body.innerHTML = "<h3>❌ Не удалось получить токены. Попробуйте ещё раз</h3>";
    }}
}})();
</script>
</body>
</html>
""")


# -------------------------------
# 3️⃣ Приём токенов от браузера
# -------------------------------
@router.post("/auth/save")
async def save_tokens(request: Request, chat_id: int):
    data = await request.json()

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access_token"] = data["token"]
    RAM_DATA[chat_id]["refresh_token"] = data["refresh"]

    print(f"\n🔥 Tokens saved for chat {chat_id}:", RAM_DATA[chat_id])
    return JSONResponse({"ok": True})