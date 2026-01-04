import json
import asyncio
from datetime import datetime, timedelta, timezone
from config import API_URL_REFRESH, API_URL_PROMO_ACTIVATE
import aiohttp
import random

# --------------------------------------------------
# Внешние зависимости (инициализируются извне)
# --------------------------------------------------
RAM_DATA = None
_save_to_redis_partial = None
NOTIFY_CALLBACK = None
MSK = timezone(timedelta(hours=3))

def init_token_module(ram_data, save_to_redis_partial, notify_callback):
    global RAM_DATA, _save_to_redis_partial, NOTIFY_CALLBACK
    RAM_DATA = ram_data
    _save_to_redis_partial = save_to_redis_partial
    NOTIFY_CALLBACK = notify_callback

# --------------------------------------------------
# Уведомления
# --------------------------------------------------
def notify_chat(chat_id: str, text: str):
    if NOTIFY_CALLBACK:
        try:
            asyncio.create_task(NOTIFY_CALLBACK(chat_id, text))
        except Exception as e:
            print(f"[TOKENS] notify error: {e}")

# --------------------------------------------------
# RAM-память пользователя
# --------------------------------------------------
def get_user_settings(chat_id: int):
    if chat_id not in RAM_DATA:
        RAM_DATA[chat_id] = {
            "access_token": None,
            "refresh_token": None,
            "next_refresh_time": None,
            "active_nominals": {},
            "waiting_for_refresh": False
        }
    return RAM_DATA[chat_id]

# --------------------------------------------------
# ПРОГРЕВ АККАУНТА (promo)
# --------------------------------------------------
PROMO_CODES = ["A7Q9M", "F4L8C", "T6H2K", "W3PZB", "елка2026", "дуб221", "замок880"]

async def warmup_promo(access_token, chat_id=None):
    async with aiohttp.ClientSession() as session:
        for i in range(3):
            code = random.choice(PROMO_CODES)
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Authorization": f"JWT {access_token}",
                "Accept-Language": "ru"
            }
            data = {"code": code, "token": "1a"}

            try:
                async with session.post(API_URL_PROMO_ACTIVATE, headers=headers, json=data) as resp:
                    await resp.text()
                    print(f"[WARMUP] chat_id={chat_id} | request {i+1}/3 | code={code} | status={resp.status}")
            except Exception as e:
                print(f"[WARMUP] chat_id={chat_id} | request {i+1}/3 | code={code} | failed: {e}")

            await asyncio.sleep(random.randint(10, 15))

# --------------------------------------------------
# ОБНОВЛЕНИЕ ТОКЕНОВ
# --------------------------------------------------
async def refresh_by_refresh_token_async(chat_id, refresh_token=None, bot=None, from_steam=False):
    """
    from_steam=True → уведомление всегда (успех/неуспех)
    from_steam=False → уведомление только при ошибке (таймер)
    """
    settings = get_user_settings(chat_id)
    token_source = refresh_token or settings.get("refresh_token")
    if not token_source:
        if from_steam:
            notify_chat(chat_id, "❌ Refresh token отсутствует")
        return False

    refresh_token_clean = token_source.strip()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL_REFRESH, json={"refreshToken": refresh_token_clean}) as r:
                resp = await r.json()
    except Exception as e:
        if from_steam:
            notify_chat(chat_id, f"Ошибка обновления токенов:\n{e}")
        else:
            notify_chat(chat_id, f"❌ Ошибка при таймере обновления токенов:\n{e}")
        return False

    data = resp.get("data") or {}
    access_token_new = data.get("token")
    refresh_token_new = data.get("refreshToken")

    if not access_token_new or not refresh_token_new:
        if from_steam:
            notify_chat(chat_id, f"❌ Не удалось привязать аккаунт:\n{resp}")
        else:
            notify_chat(chat_id, f"❌ Не удалось обновить токены:\n{resp}")
        return False

    # Сохраняем новые токены
    next_time = int((datetime.utcnow() + timedelta(days=7)).timestamp())
    settings.update({
        "access_token": access_token_new,
        "refresh_token": refresh_token_new,
        "next_refresh_time": next_time
    })
    _save_to_redis_partial(chat_id, settings)

    # Прогрев промо
    asyncio.create_task(warmup_promo(access_token_new, chat_id))

    # Уведомление пользователю, если from_steam=True (успех привязки)
    if from_steam:
        notify_chat(chat_id, "✅ Аккаунт CSGORUN успешно привязан!")

    return True

# --------------------------------------------------
# Получение валидного access_token
# --------------------------------------------------
async def get_valid_access_token(chat_id: str, bot):
    settings = get_user_settings(int(chat_id))
    access_token = settings.get("access_token")
    refresh_token = settings.get("refresh_token")
    next_refresh = settings.get("next_refresh_time")
    now = int(datetime.utcnow().timestamp())

    if not access_token:
        return None

    if next_refresh and refresh_token and now >= next_refresh:
        ok = await refresh_by_refresh_token_async(chat_id, refresh_token, bot)
        if not ok:
            return None

    return settings["access_token"]

# --------------------------------------------------
# ТАЙМЕР
# --------------------------------------------------
async def token_refresher_loop(bot):
    print("[TOKENS] запуск таймера для токенов")

    while True:
        now = int(datetime.utcnow().timestamp())

        for chat_id, obj in list(RAM_DATA.items()):
            next_refresh = obj.get("next_refresh_time")
            refresh_token = obj.get("refresh_token")

            if next_refresh and now >= next_refresh:
                print(f"[TOKENS] timer refresh chat_id={chat_id}")
                # запускаем обновление в отдельной таске, from_steam=False
                asyncio.create_task(refresh_by_refresh_token_async(chat_id, refresh_token, bot, from_steam=False))

        await asyncio.sleep(60)