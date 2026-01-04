from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import urllib.parse

from main import RAM_DATA

router = APIRouter()

SELF_URL = "https://tg-bot-test-gkbp.onrender.com"

# 1️⃣ Кнопка входа для пользователя
@router.get("/auth/login")
async def auth_login(chat_id: int):
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    steam_login = (
        "https://steamcommunity.com/openid/login"
        "?openid.ns=http://specs.openid.net/auth/2.0"
        "&openid.mode=checkid_setup"
        "&openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select"
        "&openid.identity=http://specs.openid.net/auth/2.0/identifier_select"
        f"&openid.return_to={urllib.parse.quote(return_url)}"
        "&openid.realm=https://steamcommunity.com"
    )
    return RedirectResponse(steam_login)


# 2️⃣ Страница после Steam
@router.get("/auth/callback")
async def auth_callback(chat_id: int):
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<body>
<h3>Авторизация завершена</h3>

<script>
(async () => {{
    // ждем пока csgoyz создаст токены
    await new Promise(r => setTimeout(r, 1500));

    const access = localStorage.getItem("auth-token");
    const refresh = localStorage.getItem("auth-refresh-token");

    if (!access || !refresh) {{
        document.body.innerHTML = "❌ Токены не найдены";
        return;
    }}

    await fetch("/auth/save?chat_id={chat_id}", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ access, refresh }})
    }});

    document.body.innerHTML = "✅ Готово! Можешь закрыть окно.";
}})();
</script>
</body>
</html>
""")


# 3️⃣ Прием токенов от браузера
@router.post("/auth/save")
async def save_tokens(request: Request, chat_id: int):
    data = await request.json()

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access_token"] = data["access"]
    RAM_DATA[chat_id]["refresh_token"] = data["refresh"]

    return JSONResponse({"ok": True})