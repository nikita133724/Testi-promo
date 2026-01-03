# steam_auth.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
import aiohttp
from main import RAM_DATA, SELF_URL, bot, send_message_to_user

router = APIRouter()


@router.get("/auth/login")
async def auth_login(chat_id: int = Query(...)):
    """Генерируем ссылку на Steam/OpenID авторизацию"""
    return_url = f"{SELF_URL}/auth/callback?chat_id={chat_id}"
    api_url = "https://cs2run.app/auth/1/get-url/"
    params = {"return_url": return_url}

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, params=params) as resp:
            data = await resp.json()
            steam_url = data.get("data", {}).get("url")
            if not steam_url:
                return JSONResponse({"error": "Не удалось получить ссылку на Steam"}, status_code=500)
            return RedirectResponse(steam_url)


@router.get("/auth/callback")
async def auth_callback(request: Request, chat_id: int = Query(...)):
    """Callback после авторизации Steam"""
    params = dict(request.query_params)

    async with aiohttp.ClientSession() as session:
        start_sign_in_url = "https://cs2run.app/auth/1/start-sign-in/"
        async with session.get(start_sign_in_url, params=params, allow_redirects=False) as resp:
            cookies = resp.cookies
            access_token = cookies.get("access_token").value if cookies.get("access_token") else None
            refresh_token = cookies.get("refresh_token").value if cookies.get("refresh_token") else None

            if not access_token or not refresh_token:
                try:
                    data = await resp.json()
                    access_token = data.get("access_token", access_token)
                    refresh_token = data.get("refresh_token", refresh_token)
                except Exception:
                    pass

            if not access_token or not refresh_token:
                return JSONResponse({"error": "Не удалось получить токены"}, status_code=500)

            RAM_DATA[chat_id] = {
                "access_token": access_token,
                "refresh_token": refresh_token
            }

            try:
                await send_message_to_user(
                    bot,
                    chat_id,
                    "✅ Авторизация через Steam успешна! Теперь бот может использовать ваш аккаунт cs2run."
                )
            except Exception as e:
                print(f"Ошибка при уведомлении пользователя {chat_id}: {e}")

            return RedirectResponse(f"{SELF_URL}/auth/success?chat_id={chat_id}")


@router.get("/auth/success", response_class=HTMLResponse)
async def auth_success(chat_id: int = Query(...)):
    return HTMLResponse(f"<h2>Авторизация завершена для Telegram ID {chat_id}</h2><p>Теперь можно вернуться к боту.</p>")