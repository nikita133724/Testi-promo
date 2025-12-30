from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
from redis_client import r
import json
from datetime import datetime, timedelta, timezone
from telegram_bot import RAM_DATA, _save_to_redis_partial, bot
import hashlib
import urllib.parse

YOOMONEY_WALLET = "4100117872411525"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"

NEXT_ORDER_ID = 1
ORDERS = {}
ORDERS_REDIS_KEY = "yoomoney_orders"

MSK = timezone(timedelta(hours=3))
SECRET_LABEL_KEY = "supersecret123"  # Секрет для хеширования label

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

# -----------------------
def make_label(chat_id: int, order_id: int, amount: float) -> str:
    amount_str = str(int(amount))  # если всегда целые рубли
    plain = f"{chat_id}|{order_id}|{amount_str}"
    hash_digest = hashlib.sha256((plain + SECRET_LABEL_KEY).encode()).hexdigest()
    return f"{plain}|{hash_digest}"
# -----------------------
async def pending_order_timeout(order_id: int, timeout: int = 300):
    """Таймер 5 минут на ожидание оплаты"""
    await asyncio.sleep(timeout)
    order = ORDERS.get(order_id)
    if order and order["status"] == "pending":
        order["status"] = "failed"
        save_order_to_redis(order_id, order)
        chat_id = order["chat_id"]
        try:
            await bot.send_message(chat_id, "⏳ Время на оплату истекло. Платеж не был завершён.")
        except:
            pass

# -----------------------
def create_payment_link(chat_id: int, amount: int):
    """Создать ссылку на оплату YooMoney"""
    order_id = get_next_order_id()
    label = make_label(chat_id, order_id, amount)

    # targets с URL-энкодом, чтобы # не ломал ссылку
    targets_text = f"Подписка на сервис, заказ №{order_id}"
    targets = urllib.parse.quote_plus(targets_text)

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

    # запуск таймера на 5 минут
    asyncio.create_task(pending_order_timeout(order_id))

    return url, order_id

# -----------------------
async def send_payment_link(bot, chat_id: int, amount: int):
    url, order_id = create_payment_link(chat_id, amount)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить подписку", url=url)]])
    await bot.send_message(
        chat_id,
        f"💳 Сумма: {amount}₽\nНомер заказа: #{order_id}\n\nНажмите кнопку для оплаты:",
        reply_markup=keyboard
    )

# -----------------------
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
    """Обработка уведомления IPN от YooMoney с проверкой хеша"""
    try:
        parts = label.split("|")
        if len(parts) != 4:
            return {"status": "error", "reason": "invalid_label"}
        chat_id_str, order_id_str, expected_amount_str, provided_hash = parts
        chat_id = int(chat_id_str)
        order_id = int(order_id_str)
        expected_amount = float(expected_amount_str)

        # Проверка хеша
        expected_hash = hashlib.sha256(f"{chat_id}|{order_id}|{expected_amount_str}{SECRET_LABEL_KEY}".encode()).hexdigest()
        if provided_hash != expected_hash:
            return {"status": "error", "reason": "invalid_label_hash"}

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

    # Продление подписки
    RAM_DATA.setdefault(chat_id, {})
    now = datetime.now()
    duration = timedelta(days=30)
    RAM_DATA[chat_id]["subscription_until"] = (now + duration).timestamp()
    RAM_DATA[chat_id]["suspended"] = False

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
        print(f"[YOOMONEY] Ошибка уведомления пользователя {chat_id}: {e}")

    return {"status": "ok"}