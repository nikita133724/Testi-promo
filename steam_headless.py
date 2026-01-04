# steam_headless.py
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import json

async def fetch_steam_tokens(cs2run_url: str, timeout: int = 15) -> dict:
    """
    Headless flow: открывает ссылку CS2RUN → Steam и ждёт выдачи токенов в localStorage.
    Возвращает словарь с токенами {"token": ..., "refreshToken": ...}
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # без GUI
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # 1. Открываем страницу CS2RUN
            await page.goto(cs2run_url, timeout=timeout*1000)

            # 2. Ждём редиректа на Steam и авторизации
            # Подразумевается, что пользователь уже вошёл в Steam
            # Ждём появления localStorage ключей
            token = None
            refresh = None
            for _ in range(timeout*2):  # каждые 0.5 сек, до timeout секунд
                token = await page.evaluate("localStorage.getItem('auth-token')")
                refresh = await page.evaluate("localStorage.getItem('auth-refresh-token')")
                if token and refresh:
                    break
                await asyncio.sleep(0.5)

            if not token or not refresh:
                raise RuntimeError("Не удалось получить токены из localStorage")

            return {"token": token, "refreshToken": refresh}

        except PlaywrightTimeoutError as e:
            raise RuntimeError(f"Playwright timeout: {e}") from e
        finally:
            await context.close()
            await browser.close()


# -------------------------------
# Для синхронного использования из main.py
def get_steam_tokens_sync(cs2run_url: str) -> dict:
    import nest_asyncio
    nest_asyncio.apply()  # чтобы можно было вызывать внутри уже работающего loop
    return asyncio.get_event_loop().run_until_complete(fetch_steam_tokens(cs2run_url))