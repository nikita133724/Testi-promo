from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import json

async def fetch_steam_tokens_headless(cs2run_url: str, timeout: int = 60000):
    """
    Headless flow: полностью серверный способ получения токенов через CS2RUN.
    Вход: cs2run_url от /auth/1/get-url/
    """
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Переходим на CS2RUN URL
            await page.goto(cs2run_url)

            # Ждем JSON с токенами
            try:
                # Обычно CS2RUN отдаёт <pre> с JSON
                await page.wait_for_selector("pre", timeout=timeout)
                content = await page.text_content("pre")
                tokens = json.loads(content)
            except PlaywrightTimeoutError:
                await browser.close()
                raise Exception("❌ Timeout: не дождались токенов от CS2RUN")

            await browser.close()

            if not tokens.get("token") or not tokens.get("refreshToken"):
                raise Exception("❌ Токены не получены от CS2RUN")

            return tokens

    except Exception as e:
        raise Exception(f"Headless Steam auth failed: {e}")