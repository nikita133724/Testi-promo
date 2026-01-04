# steam_headless.py
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

async def fetch_steam_tokens(cs2run_url: str, timeout: int = 60000):
    """
    Headless браузер для получения токенов Steam через CS2RUN.
    Возвращает словарь {"token": ..., "refreshToken": ...}
    """
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Переходим на CS2RUN URL
            await page.goto(cs2run_url)

            # Ждём редиректа на callback, где обычно сохраняются токены
            try:
                await page.wait_for_url("**/auth/callback**", timeout=timeout)
            except PlaywrightTimeoutError:
                await browser.close()
                raise Exception("❌ Timeout: не дождались callback после CS2RUN")

            # Достаём токены из localStorage
            token = await page.evaluate("() => localStorage.getItem('auth-token')")
            refresh = await page.evaluate("() => localStorage.getItem('auth-refresh-token')")

            await browser.close()

            if not token or not refresh:
                raise Exception("❌ Токены не найдены в localStorage")

            return {"token": token, "refreshToken": refresh}

    except Exception as e:
        raise Exception(f"Headless Steam auth failed: {e}")