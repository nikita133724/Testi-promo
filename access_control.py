import asyncio
from datetime import datetime, timedelta, timezone
import random
import string
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from redis_client import r  # твой клиент Redis

KEYS_REDIS = "active_keys"  # отдельный хеш для всех ключей
MSK = timezone(timedelta(hours=3))
# -------------------------
# Настройки
# -------------------------
SUBSCRIPTION_WATCHER_STARTED = False
KEY_LENGTH = 32
RATE_LIMIT_ATTEMPTS = 10
RATE_LIMIT_WINDOW = timedelta(minutes=30)
CHECK_INTERVAL = 45  # секунд, интервал фонового таймера

# -------------------------
# Хранение активных ключей
# -------------------------
ACCESS_KEYS = {}  # {ключ: {"duration": timedelta, "created_at": datetime}}

# Для rate-limit по chat_id
RATE_LIMIT = {}  # {chat_id: [{"time": datetime}, ...]}

KEYS_REDIS = "active_keys"  # ключ хеша в Redis для хранения ключей

def load_keys_from_redis():
    """Подгружает все активные ключи из Redis в RAM"""
    global ACCESS_KEYS
    from redis_client import r  # импортируем здесь, чтобы не было циклических зависимостей
    # Получаем все записи из хеша Redis
    keys_data = r.hgetall(KEYS_REDIS)
    
    for key_bytes, duration_bytes in keys_data.items():
        key = key_bytes.decode()  # ключ хранится как bytes, декодируем в str
        duration_seconds = float(duration_bytes)  # значение duration хранится как float
        ACCESS_KEYS[key] = {
            "duration": timedelta(seconds=duration_seconds),
            "created_at": datetime.now()
        }

    print(f"[ACCESS_CONTROL] Загружено {len(ACCESS_KEYS)} ключей из Redis")

# -------------------------
# Генерация ключа (32 символа)
# -------------------------
def generate_key(duration: timedelta) -> str:
    key = ''.join(random.choices(
        string.ascii_letters + string.digits + string.punctuation.replace(' ', ''), k=KEY_LENGTH
    ))
    ACCESS_KEYS[key] = {"duration": duration, "created_at": datetime.now()}
    r.hset(KEYS_REDIS, key, duration.total_seconds())
    return key
# -------------------------
# Проверка и запись попыток
# -------------------------
def can_attempt(chat_id: int) -> bool:
    now = datetime.now()
    attempts = RATE_LIMIT.get(chat_id, [])
    attempts = [a for a in attempts if now - a["time"] < RATE_LIMIT_WINDOW]  # удаляем старые
    RATE_LIMIT[chat_id] = attempts
    return len(attempts) < RATE_LIMIT_ATTEMPTS

def record_attempt(chat_id: int):
    now = datetime.now()
    RATE_LIMIT.setdefault(chat_id, []).append({"time": now})

# -------------------------
# Функции для работы с ключами
# -------------------------
async def prompt_for_key(update, context):
    # локальные импорты, чтобы убрать циклический импорт
    from telegram_bot import RAM_DATA, build_reply_keyboard

    chat_id = update.effective_chat.id
    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["waiting_for_key"] = True

    keyboard = ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Введите ключ активации или нажмите ❌ для отмены.",
        reply_markup=keyboard
    )

async def process_key_input(update, context):
    from telegram_bot import RAM_DATA, build_reply_keyboard, _save_to_redis_partial

    chat_id = update.effective_chat.id
    key = update.message.text.strip()
    settings = RAM_DATA.get(chat_id, {})

    # отмена ввода
    # отмена ввода
    if key == "❌ Отмена":
        settings["waiting_for_key"] = False
        await update.message.reply_text(
            "Ввод ключа отменён.",
            reply_markup=ReplyKeyboardMarkup([["Активировать доступ"]], resize_keyboard=True)
        )
        return

    result = await activate_key(chat_id, key, context.bot)
    settings["waiting_for_key"] = False

    if result["success"]:
        until_ts = result["subscription_until"]
        until_dt = datetime.fromtimestamp(until_ts, tz=timezone.utc).astimezone(MSK)
        until_text = until_dt.strftime("%d.%m.%Y %H:%M") + " МСК"
        await update.message.reply_text(
            f"✅ Доступ активирован! Подписка до {until_text}",
            reply_markup=build_reply_keyboard(chat_id)
        )

    else:
        if result["error"] == "invalid_length":
            msg = "❌ Неверный ключ."
        elif result["error"] == "key_not_found":
            msg = "❌ Не верный ключ."
        elif result["error"] == "rate_limited":
            msg = "❌ Превышено количество попыток. Попробуйте через 30 минут."
        else:
            msg = "❌ Ошибка при активации ключа."
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["Активировать доступ"]], resize_keyboard=True))

# -------------------------
# Активация ключа
# -------------------------
async def activate_key(chat_id: int, key: str, bot) -> dict:
    from telegram_bot import RAM_DATA, _save_to_redis_partial

    now = datetime.now()

    if len(key) != KEY_LENGTH:
        return {"success": False, "error": "invalid_length"}

    if not can_attempt(chat_id):
        return {"success": False, "error": "rate_limited"}

    record_attempt(chat_id)

    key_data = ACCESS_KEYS.get(key)
    if not key_data:
        return {"success": False, "error": "key_not_found"}

    duration = key_data["duration"]

    RAM_DATA.setdefault(chat_id, {})
    RAM_DATA[chat_id]["suspended"] = False
    subscription_until_ts = (now + duration).timestamp()

    RAM_DATA[chat_id]["subscription_until"] = subscription_until_ts
    
    _save_to_redis_partial(chat_id, {
        "suspended": False,
        "subscription_until": subscription_until_ts
    })

    # Удаляем ключ
    del ACCESS_KEYS[key]
    r.hdel(KEYS_REDIS, key)
    
    return {"success": True, "subscription_until": RAM_DATA[chat_id]["subscription_until"]}


# -------------------------
# Фоновый таймер проверки подписок с уведомлением за 24 часа
# -------------------------
# В access_control.py
async def subscription_watcher(bot, send_message_fn):
    from telegram_bot import RAM_DATA, _save_to_redis_partial
    global SUBSCRIPTION_WATCHER_STARTED

    if SUBSCRIPTION_WATCHER_STARTED:
        return

    SUBSCRIPTION_WATCHER_STARTED = True

    while True:
        now = datetime.now(timezone.utc)
        for chat_id, data in list(RAM_DATA.items()):
            if not data.get("suspended", True):
                until = data.get("subscription_until")
                if not until:
                    continue

                until_dt = datetime.fromtimestamp(until, tz=timezone.utc)

                # уведомление за 24 часа
                if not data.get("notified_24h", False) and now + timedelta(hours=24) >= until_dt:
                    try:
                        await send_message_fn(
                            bot,
                            chat_id,
                            "⏳ Ваша подписка истекает через 24 часа. Не забудьте продлить доступ!"
                        )
                        RAM_DATA[chat_id]["notified_24h"] = True
                        _save_to_redis_partial(chat_id, {"notified_24h": True})
                    except Exception as e:
                        print(f"[SUBSCRIPTIONS] notify 24h error {chat_id}: {e}")

                # окончание подписки
                if now >= until_dt:
                    RAM_DATA[chat_id]["suspended"] = True
                    RAM_DATA[chat_id].pop("subscription_until", None)
                    RAM_DATA[chat_id].pop("notified_24h", None)

                    _save_to_redis_partial(chat_id, {
                        "suspended": True,
                        "subscription_until": None,
                        "notified_24h": None
                    })

                    try:
                        # 1️⃣ временное сообщение для удаления клавиатуры
                        tmp_msg = await bot.send_message(
                            chat_id=chat_id,
                            text=".",  # можно любой символ, точку или пустую строку
                            reply_markup=ReplyKeyboardRemove()
                        )
                        
                        # 2️⃣ удаляем его через секунду (или сразу, не важно)
                        await bot.delete_message(chat_id=chat_id, message_id=tmp_msg.message_id)
                        await asyncio.sleep(0.2)
                        # 3️⃣ основное сообщение с новой клавиатурой
                        await bot.send_message(
                            chat_id=chat_id,
                            text="⏰ Ваша подписка закончилась.\nЧтобы снова получить доступ, нажмите кнопку ниже 👇",
                            reply_markup=ReplyKeyboardMarkup([["Активировать доступ"]], resize_keyboard=True)
                        )
                    except Exception as e:
                        print(f"[SUBSCRIPTIONS] notify expired error {chat_id}: {e}")

        await asyncio.sleep(CHECK_INTERVAL)