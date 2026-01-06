# nowpayments_module.py
import asyncio
import json
from datetime import datetime, timezone, timedelta
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_bot import bot, RAM_DATA, _save_to_redis_partial, send_message_to_user, ADMIN_CHAT_ID
from redis_client import r
from fastapi import APIRouter, Request

router = APIRouter()

# -----------------------
NOWPAYMENTS_API_KEY = "8HFD9KZ-ST94FV1-J32B132-WBJ0S9N"  # <-- Вставь свой ключ
NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1/invoice"
NOWPAYMENTS_ORDERS_KEY = "nowpayments_orders"
MSK = timezone(timedelta(hours=3))

ORDERS = {}
NEXT_ORDER_ID = 1

# ----------------------- Redis
def save_order_to_redis(order_id, data):
    r.hset(NOWPAYMENTS_ORDERS_KEY, order_id, json.dumps(data))

def load_orders_from_redis():
    global ORDERS, NEXT_ORDER_ID
    ORDERS.clear()
    all_orders = r.hgetall(NOWPAYMENTS_ORDERS_KEY)
    max_order_id = 0
    for k, v in all_orders.items():
        oid = int(k.decode())
        data = json.loads(v.decode())
        ORDERS[oid] = data
        max_order_id = max(max_order_id, oid)
    NEXT_ORDER_ID = max_order_id + 1

# -----------------------
def get_next_order_id():
    global NEXT_ORDER_ID
    oid = NEXT_ORDER_ID
    NEXT_ORDER_ID += 1
    return oid

# ----------------------- Создание инвойса
# ----------------------- Создание инвойса только в крипте
async def create_invoice(chat_id, amount, currency="USDT"):
    order_id = get_next_order_id()
    callback_url = f"https://tg-bot-test-gkbp.onrender.com/payment/nowpayments/ipn"  # <-- укажи свой URL
    description = f"Подписка 30 дней, заказ #{order_id}"

    currency = currency.upper()
    if currency not in ["USDT", "TRX", "TON"]:
        raise Exception("Выбранная валюта недоступна. Доступно: USDT, TRX, TON")

    payload = {
        "price_amount": float(amount),
        "price_currency": currency,     # базовая валюта = крипта
        "pay_currency": currency,       # оплата только в выбранной крипте
        "order_id": str(order_id),
        "order_description": description,
        "ipn_callback_url": callback_url
    }

    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(NOWPAYMENTS_API_URL, headers=headers, json=payload) as resp:
            data = await resp.json()

    if "invoice_url" not in data:
        raise Exception(f"Ошибка создания invoice: {data}")

    ORDERS[order_id] = {
        "chat_id": chat_id,
        "amount": float(amount),
        "currency": currency,
        "status": "pending",
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "invoice_id": data.get("id"),
        "invoice_url": data.get("invoice_url"),
        "processing": False,
        "paid_at": None
    }
    save_order_to_redis(order_id, ORDERS[order_id])
    asyncio.create_task(pending_order_timeout(order_id))
    return data.get("invoice_url"), order_id


# ----------------------- Отправка ссылки пользователю
async def send_payment_link(bot, chat_id, amount, currency):
    """
    Отправка пользователю ссылки на оплату выбранной криптой.
    Валюта должна приходить из Telegram кнопок: USDT/TRX/TON
    """
    currency = currency.upper()
    if currency not in ["USDT", "TRX", "TON"]:
        raise Exception("Выбранная валюта недоступна. Доступно: USDT, TRX, TON")

    url, order_id = await create_invoice(chat_id, amount, currency=currency)
    text = (
        f"💳 Оплата криптой: {amount} {currency}\n"
        f"Заказ: #{order_id}\n"
        f"⏳ Время на оплату: 5 минут"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить", url=url)]])
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)
    ORDERS[order_id]["message_id"] = msg.message_id
    save_order_to_redis(order_id, ORDERS[order_id])

# ----------------------- Таймер для неоплаченных заказов
async def pending_order_timeout(order_id, timeout=300):
    await asyncio.sleep(timeout)
    order = ORDERS.get(order_id)
    if not order:
        return

    if order.get("message_id"):
        try:
            await bot.delete_message(order["chat_id"], order["message_id"])
        except:
            pass

    if order["status"] == "pending":
        order["status"] = "expired"
        save_order_to_redis(order_id, order)
        await bot.send_message(order["chat_id"], f"⏳ Время на оплату истекло. Заказ #{order_id}")

# ----------------------- NOWPayments IPN (Webhook)
@router.post("/payment/nowpayments/ipn")
async def nowpayments_ipn_endpoint(request: Request):
    data = await request.json()
    return await nowpayments_ipn(data)

async def nowpayments_ipn(ipn_data: dict):
    """
    Обработка webhook от NOWPayments
    """
    order_id = int(ipn_data.get("order_id"))
    status = ipn_data.get("payment_status")
    amount = float(ipn_data.get("price_amount", 0))
    currency = ipn_data.get("pay_currency", "USD").upper()

    order = ORDERS.get(order_id)
    if not order:
        return {"status": "error", "reason": "order_not_found"}

    if order.get("processing"):
        return {"status": "ok"}

    order["processing"] = True
    save_order_to_redis(order_id, order)

    try:
        if status in ["finished", "confirmed"]:
            order["status"] = "paid"
            order["paid_at"] = int(datetime.now(timezone.utc).timestamp())
            save_order_to_redis(order_id, order)

            # Удаляем кнопку
            if "message_id" in order:
                try:
                    await bot.delete_message(order["chat_id"], order["message_id"])
                except:
                    pass

            # Продление подписки на 30 дней
            chat_id = order["chat_id"]
            now_ts = datetime.now(timezone.utc).timestamp()
            raw_until = RAM_DATA.get(chat_id, {}).get("subscription_until")
            current_until = float(raw_until) if isinstance(raw_until, (int, float)) else 0
            suspended = RAM_DATA.get(chat_id, {}).get("suspended", False)
            base = current_until if current_until > now_ts and not suspended else now_ts
            new_until = base + 30 * 24 * 60 * 60

            was_suspended = RAM_DATA[chat_id].get("suspended", True)
            RAM_DATA[chat_id]["subscription_until"] = new_until
            RAM_DATA[chat_id]["suspended"] = False
            _save_to_redis_partial(chat_id, {"subscription_until": new_until, "suspended": False})

            until_text = datetime.fromtimestamp(new_until, tz=MSK).strftime("%d.%m.%Y %H:%M") + " МСК"

            if was_suspended:
                await send_message_to_user(bot, chat_id, f"✅ Подписка активна до {until_text}. Заказ #{order_id}")
            else:
                await bot.send_message(chat_id, f"✅ Подписка продлена до {until_text}. Заказ #{order_id}")

            # Уведомление администратору
            try:
                await bot.send_message(
                    ADMIN_CHAT_ID,
                    f"💰 Новая покупка подписки\nПользователь: {chat_id}\n"
                    f"Сумма: {amount} {currency}\nЗаказ: #{order_id}\nАктивна до: {until_text}"
                )
            except Exception as e:
                print(f"[ADMIN NOTIFY ERROR] {e}")
    finally:
        order["processing"] = False
        save_order_to_redis(order_id, order)

    return {"status": "ok"}

# ----------------------- Получение последних заказов пользователя
def get_last_orders(chat_id, count=4):
    orders = [(oid, o) for oid, o in ORDERS.items() if o["chat_id"] == chat_id]
    orders.sort(key=lambda x: x[1]["created_at"], reverse=True)
    return orders[:count]