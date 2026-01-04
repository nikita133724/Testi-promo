from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlencode
import json

async def fetch_steam_tokens(openid_params: dict, timeout: int = 60000):
    """
    Headless flow: получаем реальные токены через CS2RUN + Steam.
    openid_params - словарь query-параметров от Steam OpenID
    """
    try:
        # Формируем URL для финального CS2RUN start-sign-in
        base_url = "https://cs2run.app/auth/1/start-sign-in/"
        query = urlencode(openid_params)  # <--- ключи Steam как GET-параметры
        final_url = f"{base_url}?{query}"

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()

            # Переходим на финальный URL для получения токенов
            await page.goto(final_url)

            # Ждём JSON на странице (обычно в <pre>)
            try:
                await page.wait_for_selector("pre", timeout=timeout)
                content = await page.text_content("pre")
                tokens = json.loads(content)
            except PlaywrightTimeoutError:
                await browser.close()
                raise Exception("❌ Timeout: не удалось получить токены с CS2RUN")

            await browser.close()

            if not tokens.get("token") or not tokens.get("refreshToken"):
                raise Exception("❌ Токены не получены")

            return tokens

    except Exception as e:
        raise Exception(f"Headless Steam auth failed: {e}")