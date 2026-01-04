import httpx
import urllib.parse
from main import RAM_DATA

async def fetch_csgoyz_tokens(chat_id: int):
    async with httpx.AsyncClient(follow_redirects=True) as client:

        # 1. Получаем ссылку на Steam
        return_url = f"https://tg-bot-test-gkbp.onrender.com/auth/finish?chat_id={chat_id}"
        get_url = f"https://cs2run.app/auth/1/get-url/?return_url={urllib.parse.quote(return_url)}"

        r = await client.get(get_url)
        steam_url = r.json()["data"]["url"]

        # 2. Отдаём эту ссылку пользователю
        return steam_url, client