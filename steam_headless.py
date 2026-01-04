# steam_headless.py
from playwright.async_api import async_playwright
import asyncio
import urllib.parse
import json

async def fetch_steam_tokens(cs2run_url: str) -> dict:
    """
    Headless flow: заходим на cs2run, делаем все редиректы,
    ждём JSON с токенами.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Переходим на ссылку CS2RUN
        await page.goto(cs2run_url)

        # Ждём, пока не появится JSON с токенами
        try:
            # CS2RUN редиректит на /auth/callback?...
            await page.wait_for_response(lambda resp: "auth/callback" in resp.url and resp.status == 200, timeout=15000)
            responses = [resp async for resp in page.context.responses if "auth/callback" in resp.url]
            data = None
            for resp in responses:
                try:
                    text = await resp.text()
                    if text.startswith("{"):
                        data = json.loads(text)
                        break
                except:
                    continue
            await browser.close()
            if data:
                return data
            else:
                raise Exception("Tokens not found")
        except Exception as e:
            await browser.close()
            raise e

# Example usage:
# asyncio.run(fetch_steam_tokens("https://cs2run.app/auth/1/get-url/?return_url=..."))