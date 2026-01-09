from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import json
from datetime import datetime, timedelta, timezone
import hashlib
import urllib.parse

from telegram_bot import RAM_DATA, _save_to_redis_partial, bot, send_message_to_user, ADMIN_CHAT_ID, app as tg_app
from orders_store import next_order_id, save_order, get_order, ORDERS


INSTRUCTION_URL = "https://telegra.ph/Instrukciya-po-ispolzovaniyu-tg-bota-01-06"
YOOMONEY_WALLET = "4100117872411525"
SUCCESS_REDIRECT_URI = "https://t.me/promo_run_bot"

MSK = timezone(timedelta(hours=3))
SECRET_LABEL_KEY = "superqownsnms18191wnwnw181991wnsnsm199192nwnnsjs292992snnejsjs"

MAX_DIFF_PERCENT = 0.1
MIN_HASH_LEN = 25


def safe_telegram_call(coro):
    tg_app.create_task(coro)


# ----------------------- LABEL
def make_label(chat_id, order_id, amount):
    plain = f"{chat_id}|{order_id}|{int(amount)}"
    h = hashlib.sha256((plain + SECRET_LABEL_KEY).encode()).hexdigest()
    return f"{plain}|{h}"


# ----------------------- TIMER
async def pending_order_timeout(order_id, timeout=300):
    await asyncio.sleep(timeout)

    order = get_order(order_id)
    if not order:
        return

    if "message_id" in order:
        try:
            safe_telegram_call(bot.delete_message(order["chat_id"], order["message_id"]))
        except:
            pass

    if order["status"] == "pending":
        order["status"] = "expired"
        order["processing"] = False
        save_order(order_id, order)
        safe_telegram_call(bot.send_message(order["chat_id"], f"⏳ Время оплаты истекло. Заказ #{order_id}"))


# ----------------------- CREATE PAYMENT
def create_payment_link(chat_id, amount):

    order_id = next_order_id()
    label = make_label(chat_id, order_id, amount)

    targets = urllib.parse.quote_plus(f"promo_run_bot, заказ №{order_id}")

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

    order = {
        "chat_id": chat_id,
        "amount": amount,
        "currency": "RUB",
        "provider": "yoomoney",
        "status": "pending",
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "payment_id": None,
        "processing": False
    }

    save_order(order_id, order)
    asyncio.create_task(pending_order_timeout(order_id))

    return url, order_id


# ----------------------- SEND LINK
async def send_payment_link(bot, chat_id, amount):

    url, order_id = create_payment_link(chat_id, amount)

    text = (
        f"💳 Сумма: {amount}₽\n"
        f"🧾 Заказ: #{order_id}\n"
        f"⏳ Время на оплату: 5 минут"
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить", url=url)]])
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    order = get_order(order_id)
    order["message_id"] = msg.message_id
    save_order(order_id, order)


# ----------------------- IPN
async def yoomoney_ipn(operation_id, amount, currency, datetime_str, label, sha1_hash):
    try:
        chat_id, order_id, expected_amount_str, provided_hash = label.split("|")
        order_id = int(order_id)
        expected_amount = float(expected_amount_str)

        # Проверка хэша
        plain = f"{chat_id}|{order_id}|{expected_amount_str}"
        expected_hash = hashlib.sha256((plain + SECRET_LABEL_KEY).encode()).hexdigest()
        if len(provided_hash) < MIN_HASH_LEN or not expected_hash.startswith(provided_hash):
            return {"status": "error", "reason": "invalid_label_hash"}

        # Проверка суммы
        if amount < expected_amount * (1 - MAX_DIFF_PERCENT):
            return {"status": "error", "reason": "wrong_amount"}

    except:
        return {"status": "error", "reason": "invalid_label"}

    # Проверка валюты
    if currency != "643":
        return {"status": "error", "reason": "wrong_currency"}

    # Получаем заказ
    order = get_order(order_id)
    if not order:
        return {"status": "error", "reason": "order_not_found"}

    # Если уже оплачено — ничего не делаем
    if order["status"] == "paid":
        return {"status": "ok"}

    # Ставим флаг, что обрабатываем платеж
    order["processing"] = True
    save_order(order_id, order)

    try:
        # Меняем статус на оплачено
        order["status"] = "paid"
        order["payment_id"] = operation_id
        save_order(order_id, order)

        # Удаляем сообщение с кнопкой оплаты
        try:
            await bot.delete_message(order["chat_id"], order.get("message_id"))
        except:
            pass

        # Продлеваем подписку
        chat_id = int(chat_id)
        now = datetime.now(timezone.utc).timestamp()
        current = float(RAM_DATA.get(chat_id, {}).get("subscription_until", 0))
        base = max(current, now)
        new_until = base + 30 * 24 * 60 * 60  # +30 дней

        RAM_DATA.setdefault(chat_id, {})
        RAM_DATA[chat_id]["subscription_until"] = new_until
        RAM_DATA[chat_id]["suspended"] = False
        _save_to_redis_partial(chat_id, {"subscription_until": new_until, "suspended": False})

        until_text = datetime.fromtimestamp(new_until, tz=MSK).strftime("%d.%m.%Y %H:%M")
        await send_message_to_user(bot, chat_id, f"✅ Подписка активна до {until_text}. Заказ #{order_id}")

        # Уведомление админу
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"💰 Новая покупка\nПользователь: {chat_id}\nЗаказ: #{order_id}\nСумма: {amount}₽\nДо: {until_text}"
        )

    finally:
        # Снимаем флаг обработки
        order["processing"] = False
        save_order(order_id, order)

    return {"status": "ok"}

# ----------------------- HISTORY
def get_last_orders(chat_id, count=4):
    orders = [(oid, o) for oid, o in ORDERS.items() if o["chat_id"] == chat_id]
    orders.sort(key=lambda x: x[1]["created_at"], reverse=True)
    return orders[:count]