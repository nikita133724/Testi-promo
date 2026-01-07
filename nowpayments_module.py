import asyncio
import json
from datetime import datetime, timezone, timedelta
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_bot import bot, RAM_DATA, _save_to_redis_partial, send_message_to_user, ADMIN_CHAT_ID
from fastapi import APIRouter, Request
from orders_store import next_order_id, save_order, get_order, ORDERS

router = APIRouter()

NOWPAYMENTS_API_KEY = "8HFD9KZ-ST94FV1-J32B132-WBJ0S9N"
NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1/invoice"
MSK = timezone(timedelta(hours=3))


# ----------------------- СОЗДАНИЕ ИНВОЙСА
async def create_invoice(chat_id, amount, currency="USDT", network=None):

    order_id = next_order_id()  # Локальный номер заказа
    callback_url = "https://tg-bot-test-gkbp.onrender.com/payment/nowpayments/ipn"
    description = f"Подписка 30 дней, заказ #{order_id}"

    currency = currency.upper()

    if currency == "USDT":
        if not network:
            raise Exception("Для USDT необходимо выбрать сеть")
        price_currency = f"usdt{network.lower()}"
        pay_currency = price_currency
    elif currency == "TRX":
        price_currency = "trx"
        pay_currency = "trx"
    elif currency == "TON":
        price_currency = "ton"
        pay_currency = "ton"
    else:
        raise Exception("Недоступная валюта")

    payload = {
        "price_amount": float(amount),
        "price_currency": price_currency,
        "pay_currency": pay_currency,
        "order_id": str(order_id),           # <-- ВАЖНО: свой локальный order_id
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
        raise Exception(f"NOWPayments error: {data}")

    order = {
        "chat_id": chat_id,
        "amount": float(amount),
        "currency": currency,
        "network": network,
        "status": "pending",
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "invoice_id": data["id"],           # <-- теперь это их internal ID, на всякий случай
        "invoice_url": data["invoice_url"],
        "provider": "crypto",
        "processing": False,
        "paid_at": None
    }

    save_order(order_id, order)
    asyncio.create_task(pending_order_timeout(order_id))

    return data["invoice_url"], order_id

# ----------------------- ОТПРАВКА ССЫЛКИ
async def send_payment_link(bot, chat_id, amount, currency, network=None):

    url, order_id = await create_invoice(chat_id, amount, currency, network)

    network_text = f" {network.upper()}" if network else ""

    text = (
        f"💳 Оплата: {amount} {currency}{network_text}\n"
        f"🧾 Заказ: #{order_id}\n"
        f"⏳ Время на оплату: 5 минут"
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить", url=url)]])
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    order = get_order(order_id)
    order["message_id"] = msg.message_id
    save_order(order_id, order)


# ----------------------- ТАЙМЕР
async def pending_order_timeout(order_id, timeout=300):
    await asyncio.sleep(timeout)

    order = get_order(order_id)
    if not order or order["status"] != "pending":
        return

    try:
        if "message_id" in order:
            await bot.delete_message(order["chat_id"], order["message_id"])
    except:
        pass

    order["status"] = "expired"
    save_order(order_id, order)

    await bot.send_message(order["chat_id"], f"⏳ Время оплаты истекло. Заказ #{order_id}")


# ----------------------- IPN
@router.post("/payment/nowpayments/ipn")
async def nowpayments_ipn_endpoint(request: Request):
    data = await request.json()
    return await nowpayments_ipn(data)


async def nowpayments_ipn(ipn_data: dict):

    order_id = int(ipn_data.get("order_id"))
    status = ipn_data.get("payment_status")

    order = get_order(order_id)
    if not order or order.get("processing"):
        return {"status": "ok"}

    order["processing"] = True
    save_order(order_id, order)

    try:
        if status in ["finished", "confirmed"]:

            order["status"] = "paid"
            order["paid_at"] = int(datetime.now(timezone.utc).timestamp())
            save_order(order_id, order)

            try:
                await bot.delete_message(order["chat_id"], order.get("message_id"))
            except:
                pass

            chat_id = order["chat_id"]
            now_ts = datetime.now(timezone.utc).timestamp()
            current_until = float(RAM_DATA.get(chat_id, {}).get("subscription_until", 0))
            base = max(current_until, now_ts)

            new_until = base + 30 * 24 * 60 * 60

            RAM_DATA.setdefault(chat_id, {})
            RAM_DATA[chat_id]["subscription_until"] = new_until
            RAM_DATA[chat_id]["suspended"] = False
            _save_to_redis_partial(chat_id, {"subscription_until": new_until, "suspended": False})

            until_text = datetime.fromtimestamp(new_until, tz=MSK).strftime("%d.%m.%Y %H:%M")

            await bot.send_message(chat_id, f"✅ Подписка активна до {until_text}. Заказ #{order_id}")

            await bot.send_message(
                ADMIN_CHAT_ID,
                f"💰 Оплата получена\nЗаказ #{order_id}\nПользователь {chat_id}"
            )

    finally:
        order["processing"] = False
        save_order(order_id, order)

    return {"status": "ok"}


# ----------------------- ИСТОРИЯ ПЛАТЕЖЕЙ
def get_last_orders(chat_id, count=5):
    orders = [(oid, o) for oid, o in ORDERS.items() if o["chat_id"] == chat_id]
    orders.sort(key=lambda x: x[1]["created_at"], reverse=True)
    return orders[:count]