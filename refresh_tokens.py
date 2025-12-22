import json
import requests
import asyncio
from datetime import datetime, timedelta
from config import API_URL_REFRESH
# --------------------------------------------------
# Внешние зависимости (инициализируются извне)
# --------------------------------------------------

RAM_DATA = None
_save_to_redis_partial = None
NOTIFY_CALLBACK = None

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
# Получение валидного access_token
# --------------------------------------------------
def get_valid_access_token(chat_id: str):
    settings = get_user_settings(int(chat_id))

    access_token = settings.get("access_token")
    refresh_token = settings.get("refresh_token")
    next_refresh = settings.get("next_refresh_time")

    if not access_token:
        return None

    if next_refresh and refresh_token and datetime.utcnow() >= next_refresh:
        ok = refresh_by_refresh_token(chat_id)
        if not ok:
            return None

    return settings["access_token"]


# --------------------------------------------------
# ОБНОВЛЕНИЕ ТОКЕНОВ (ручное И таймер)
# --------------------------------------------------
def refresh_by_refresh_token(chat_id: str, refresh_token: str | None = None):
    settings = get_user_settings(int(chat_id))

    # 1️⃣ источник refresh token
    token_source = refresh_token if refresh_token is not None else settings.get("refresh_token")
    refresh_token_clean = (token_source or "").strip()
    print("RAW TOKEN REPR:", repr(token_source))
    print("CLEAN TOKEN REPR:", repr(refresh_token_clean))
    print("LEN RAW:", len(token_source))
    print("LEN CLEAN:", len(refresh_token_clean))
    
    if not refresh_token_clean:
        notify_chat(chat_id, "❌ Refresh token отсутствует")
        return False

    print(f"[TOKENS] refresh start | chat_id={chat_id}")
    print(f"[TOKENS] refresh_token(last 8)={refresh_token_clean[-8:]}")

    # 2️⃣ запрос к API
    try:
        r_api = requests.post(
            API_URL_REFRESH,
            headers={"Content-Type": "application/json"},
            json={"refreshToken": refresh_token_clean},
            timeout=10
        )
        resp = r_api.json()
        print(f"[TOKENS] API response: {resp}")
    except Exception as e:
        notify_chat(chat_id, f"Ошибка обновления токенов:\n{e}")
        return False

    # 3️⃣ разбор ответа
    data = resp.get("data") or {}
    access_token_new = (data.get("token") or "").strip()
    refresh_token_new = (data.get("refreshToken") or "").strip()

    if not access_token_new or not refresh_token_new:
        notify_chat(
            chat_id,
            f"❌ Не удалось обновить токены:\n{json.dumps(resp, ensure_ascii=False)}"
        )
        return False

    # 4️⃣ новое время обновления
    next_time = (datetime.utcnow() + timedelta(days=7)).replace(microsecond=0)

    # 5️⃣ ОБНОВЛЕНИЕ RAM (старые токены уничтожаются)
    settings.update({
        "access_token": access_token_new,
        "refresh_token": refresh_token_new,
        "next_refresh_time": next_time
    })

    # 6️⃣ Redis = копия RAM
    _save_to_redis_partial(chat_id, {
        "access_token": access_token_new,
        "refresh_token": refresh_token_new,
        "next_refresh_time": next_time.isoformat()
    })

    notify_chat(
        chat_id,
        f"✅ Токены обновлены\nСледующее обновление: {next_time}"
    )

    return True


# --------------------------------------------------
# ТАЙМЕР
# --------------------------------------------------
async def token_refresher_loop():
    print("[TOKENS] запуск таймера для токенов")

    while True:
        now = datetime.utcnow()

        for chat_id, obj in list(RAM_DATA.items()):
            next_refresh = obj.get("next_refresh_time")
            refresh_token = obj.get("refresh_token")

            if next_refresh and refresh_token and now >= next_refresh:
                print(f"[TOKENS] timer refresh chat_id={chat_id}")
                refresh_by_refresh_token(str(chat_id))

        await asyncio.sleep(60)