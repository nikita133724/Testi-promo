from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
from redis_client import r
import json
from datetime import datetime, timedelta, timezone
from telegram_bot import RAM_DATA, _save_to_redis_partial, bot, send_message_to_user, app as tg_app, build_reply_keyboard
import hashlib
import urllib.parse

def safe_telegram_call(coro):
    tg_app.create_task(coro)

YOOMONEY_WALLET = "4100117872411525"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"

NEXT_ORDER_ID = 1
ORDERS = {}
ORDERS_REDIS_KEY = "yoomoney_orders"

MSK = timezone(timedelta(hours=3))
SECRET_LABEL_KEY = "supersecret123"

# ----------------------- Redis
def save_order_to_redis(order_id, data):
    r.hset(ORDERS_REDIS_KEY, order_id, json.dumps(data))

def load_orders_from_redis():
    global ORDERS, NEXT_ORDER_ID
    ORDERS.clear()
    all_orders = r.hgetall(ORDERS_REDIS_KEY)
    max_order_id = 0
    for k, v in all_orders.items():
        oid = int(k.decode())
        data = json.loads(v.decode())
        ORDERS[oid] = data
        max_order_id = max(max_order_id, oid)
    NEXT_ORDER_ID = max_order_id + 1

# ----------------------- Helpers
def get_next_order_id():
    global NEXT_ORDER_ID
    oid = NEXT_ORDER_ID
    NEXT_ORDER_ID += 1
    return oid

def make_label(chat_id, order_id, amount):
    plain = f"{chat_id}|{order_id}|{int(amount)}"
    h = hashlib.sha256((plain + SECRET_LABEL_KEY).encode()).hexdigest()
    return f"{plain}|{h}"
    
# ----------------------- Timer
async def pending_order_timeout(order_id, timeout=300):
    await asyncio.sleep(timeout)

    order = ORDERS.get(order_id)
    if not order:
        return

    # Удаляем сообщение с кнопкой в любом случае
    if "message_id" in order:
        try:
            safe_telegram_call(bot.delete_message(order["chat_id"], order["message_id"]))
        except Exception as e:
            # Можно логировать, но игнорировать ошибку
            print(f"[YOOMONEY] Не удалось удалить сообщение: {e}")

    if order["status"] == "pending":
        order["status"] = "expired"
        save_order_to_redis(order_id, order)
        safe_telegram_call(bot.send_message(order["chat_id"], "⏳ Время на оплату истекло."))

# ----------------------- Create link
def create_payment_link(chat_id, amount):
    order_id = get_next_order_id()
    label = make_label(chat_id, order_id, amount)

    store_name = "promo_run_bot"
    targets = urllib.parse.quote_plus(f"{store_name}, заказ №{order_id}")  # название магазина + номер заказа

    url = (
        f"https://yoomoney.ru/quickpay/confirm.xml"
        f"?receiver={YOOMONEY_WALLET}"
        f"&quickpay-form=shop"
        f"&targets={targets}"
        f"&sum={amount}"
        f"&currency=643"
        f"&successURL={SUCCESS_REDIRECT_URI}"
        f"&label={label}"
    )

    ORDERS[order_id] = {
        "chat_id": chat_id,
        "amount": amount,
        "status": "pending",
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "paid_at": None,
        "operation_id": None
    }

    save_order_to_redis(order_id, ORDERS[order_id])
    asyncio.create_task(pending_order_timeout(order_id))

    return url, order_id
# ----------------------- Send link
async def send_payment_link(bot, chat_id, amount):
    url, order_id = create_payment_link(chat_id, amount)

    now_ts = datetime.now(timezone.utc).timestamp()
    current_until = float(RAM_DATA.get(chat_id, {}).get("subscription_until", 0))
    suspended = RAM_DATA.get(chat_id, {}).get("suspended", False)
    was_active = current_until > now_ts and not suspended

    text = f"💳 Сумма: {amount}₽\nЗаказ: #{order_id}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить", url=url)]])
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    ORDERS[order_id]["message_id"] = msg.message_id
    save_order_to_redis(order_id, ORDERS[order_id])

# ----------------------- IPN
async def yoomoney_ipn(operation_id, amount, currency,
                       datetime_str, label, sha1_hash):

    try:
        chat_id, order_id, expected_amount, provided_hash = label.split("|")
        order_id = int(order_id)

        plain = f"{chat_id}|{order_id}|{expected_amount}"
        expected_hash = hashlib.sha256((plain + SECRET_LABEL_KEY).encode()).hexdigest()
        if provided_hash != expected_hash:
            return {"status": "error", "reason": "invalid_label_hash"}
    except:
        return {"status": "error", "reason": "invalid_label"}

    # 🧾 проверка валюты
    if currency != "643":
        return {"status": "error", "reason": "wrong_currency"}
        
    order = ORDERS.get(order_id)
    if not order:
        return {"status": "error", "reason": "order_not_found"}

    # 🛡 защита от двойного IPN
    if order["status"] in ("paid", "expired"):
        if "message_id" in order:
            try:
                safe_telegram_call(bot.delete_message(order["chat_id"], order["message_id"]))
            except:
                pass
        # Если заказ истёк — платёж принимаем, но подписку не выдаём
        return {"status": "ok"}
    

    if round(float(amount), 2) != round(float(expected_amount), 2):
        order["status"] = "failed"
        save_order_to_redis(order_id, order)
        return {"status": "error", "reason": "wrong_amount"}

    order["status"] = "paid"
    order["paid_at"] = int(datetime.fromisoformat(datetime_str.replace("Z", "+00:00")).timestamp())      # время платежа от YooMoney
    order["operation_id"] = operation_id
    save_order_to_redis(order_id, order)

    # удаляем сообщение с кнопкой
    if "message_id" in order:
        try:
            safe_telegram_call(bot.delete_message(order["chat_id"], order["message_id"]))
        except:
            pass

    # продление подписки
    now = datetime.now(timezone.utc).timestamp()
    current = float(RAM_DATA.get(int(chat_id), {}).get("subscription_until", 0))
    suspended = RAM_DATA.get(int(chat_id), {}).get("suspended", False)
    
    # Если подписка активна и не приостановлена, от текущей даты +30 дней
    base = current if current > now and not suspended else now
    new_until = base + 30 * 24 * 60 * 60

    was_suspended = RAM_DATA[int(chat_id)].get("suspended", True)
    RAM_DATA[int(chat_id)]["subscription_until"] = new_until
    RAM_DATA[int(chat_id)]["suspended"] = False
    _save_to_redis_partial(int(chat_id), {"subscription_until": new_until, "suspended": False})
    
    # формируем строку с МСК
    until_text = datetime.fromtimestamp(new_until, tz=MSK).strftime("%d.%m.%Y %H:%M") + " МСК"
    
    # если подписка была неактивна — отправляем клавиатуру с номиналами
    if was_suspended:
        await send_message_to_user(
            bot,
            int(chat_id),
            f"✅ Подписка активна до {until_text}",
            reply_markup=build_reply_keyboard(int(chat_id))
        )
    else:
        await bot.send_message(int(chat_id), f"✅ Подписка активна до {until_text}")
        
def get_last_orders(chat_id, count=4):
    """Возвращает список последних заказов пользователя вместе с их ID."""
    orders = [(oid, o) for oid, o in ORDERS.items() if o["chat_id"] == chat_id]
    orders.sort(key=lambda x: x[1]["created_at"], reverse=True)
    return orders[:count]