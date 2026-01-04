from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlencode, urlparse, parse_qs

async def fetch_steam_tokens(openid_params: dict, timeout: int = 60000):
    """
    Headless flow для получения реальных токенов через CS2RUN + Steam.
    Входные параметры - query params от Steam (OpenID).
    """
    try:
        # Формируем URL для финальной CS2RUN проверки
        base_url = "https://cs2run.app/auth/1/start-sign-in/"
        query = urlencode({"openid_params": json.dumps(openid_params)})
        final_url = f"{base_url}?{query}"

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()

            # Переходим на финальный URL для получения токенов
            await page.goto(final_url)

            # Ждём ответа, который CS2RUN отдаёт с токенами (обычно JSON на странице)
            try:
                # Ждём, пока на странице появится <pre> с JSON токенов
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