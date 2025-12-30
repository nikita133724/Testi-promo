from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
from redis_client import r
import json
from datetime import datetime, timedelta

YOOMONEY_WALLET = "4100117872411525"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"

# внутренний счётчик заказов
NEXT_ORDER_ID = 1

# Хранение всех заказов: {order_id: {"chat_id": int, "amount": int, "status": str}}
ORDERS = {}

ORDERS_REDIS_KEY = "yoomoney_orders"

# -----------------------
# Redis helpers
def save_order_to_redis(order_id, data):
    r.hset(ORDERS_REDIS_KEY, order_id, json.dumps(data))

def load_orders_from_redis():
    global ORDERS, NEXT_ORDER_ID
    ORDERS.clear()
    all_orders = r.hgetall(ORDERS_REDIS_KEY)
    max_order_id = 0
    for oid_bytes, data_bytes in all_orders.items():
        oid = int(oid_bytes.decode())
        data = json.loads(data_bytes.decode())
        ORDERS[oid] = data
        max_order_id = max(max_order_id, oid)
    NEXT_ORDER_ID = max_order_id + 1
    print(f"[YOOMONEY] Загружено {len(ORDERS)} заказов из Redis")

# -----------------------
def get_next_order_id():
    global NEXT_ORDER_ID
    oid = NEXT_ORDER_ID
    NEXT_ORDER_ID += 1
    return oid

def create_payment_link(chat_id: int, amount: int):
    order_id = get_next_order_id()
    label = f"{chat_id}|{order_id}|{amount}"
    targets = f"Подписка на сервис, заказ #{order_id}"

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

    # сохраняем заказ как pending
    ORDERS[order_id] = {
        "chat_id": chat_id,
        "amount": amount,
        "status": "pending"
    }
    save_order_to_redis(order_id, ORDERS[order_id])
    return url, order_id

async def send_payment_link(bot, chat_id: int, amount: int):
    url, order_id = create_payment_link(chat_id, amount)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Оплатить подписку", url=url)]
    ])

    await bot.send_message(
        chat_id,
        f"💳 Сумма: {amount}₽\nНомер заказа: #{order_id}\n\nНажмите кнопку для оплаты:",
        reply_markup=keyboard
    )

# -----------------------
# IPN обработка
from telegram_bot import RAM_DATA, _save_to_redis_partial, bot
from datetime import timezone

MSK = timezone(timedelta(hours=3))

async def yoomoney_ipn(
    notification_type: str,
    operation_id: str,
    amount: float,
    currency: str,
    datetime_str: str,
    sender: str,
    codepro: str,
    label: str,
    sha1_hash: str
):
    """
    Обработка уведомления IPN от YooMoney.
    label = "chat_id|order_id|amount"
    """
    try:
        chat_id_str, order_id_str, expected_amount_str = label.split("|")
        chat_id = int(chat_id_str)
        order_id = int(order_id_str)
        expected_amount = float(expected_amount_str)
    except Exception:
        return {"status": "error", "reason": "invalid_label"}

    order = ORDERS.get(order_id)
    if not order:
        return {"status": "error", "reason": "order_not_found"}

    if order["status"] != "pending":
        return {"status": "ok"}  # уже обработан

    if float(amount) != expected_amount:
        order["status"] = "failed"
        save_order_to_redis(order_id, order)
        return {"status": "error", "reason": "wrong_amount"}

    # Оплата успешна
    order["status"] = "paid"
    save_order_to_redis(order_id, order)

    # Продление подписки в RAM_DATA
    RAM_DATA.setdefault(chat_id, {})
    now = datetime.now()
    duration = timedelta(days=30)  # например, 30 дней подписки
    RAM_DATA[chat_id]["subscription_until"] = (now + duration).timestamp()
    RAM_DATA[chat_id]["suspended"] = False

    # сохраняем в Redis
    _save_to_redis_partial(chat_id, {
        "subscription_until": RAM_DATA[chat_id]["subscription_until"],
        "suspended": False
    })

    # уведомление пользователя
    until_dt = datetime.fromtimestamp(RAM_DATA[chat_id]["subscription_until"], tz=MSK)
    until_text = until_dt.strftime("%d.%m.%Y %H:%M")
    try:
        await bot.send_message(
            chat_id,
            f"✅ Оплата подтверждена!\nВаша подписка активна до {until_text}"
        )
    except Exception as e:
        print(f"Ошибка уведомления пользователя: {e}")

    return {"status": "ok"}