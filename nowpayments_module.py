import asyncio
from datetime import datetime, timezone, timedelta
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_bot import bot, RAM_DATA, _save_to_redis_partial, send_message_to_user, ADMIN_CHAT_ID
from orders_store import next_order_id, save_order, get_order, find_order_by_invoice
from fastapi import APIRouter, Request

router = APIRouter()

NOWPAYMENTS_API_KEY = "8HFD9KZ-ST94FV1-J32B132-WBJ0S9N"
NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1/invoice"
MSK = timezone(timedelta(hours=3))


# ----------------------- CREATE INVOICE
async def create_invoice(chat_id, amount, currency="USDT", network=None):

    local_order_id = next_order_id()

    callback_url = "https://tg-bot-test-gkbp.onrender.com/payment/nowpayments/ipn"
    description = f"Подписка 30 дней, заказ #{local_order_id}"

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

    # --- формируем инвойс
    payload = {
        "price_amount": float(amount),
        "price_currency": price_currency,
        "pay_currency": pay_currency,
        "order_description": description,
        "ipn_callback_url": callback_url,
        "pay_amount_additional": "network_fee"  # комиссия сети добавляется на покупателя
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

    # --- сохраняем заказ в нашей системе
    order = {
        "chat_id": chat_id,
        "amount": float(amount),  # сумма, которую мы хотим получить
        "currency": currency,
        "network": network,
        "status": "pending",
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "invoice_id": str(data["id"]),
        "invoice_url": data["invoice_url"],
        "provider": "crypto",
        "processing": False,
        "paid_at": None
    }

    save_order(local_order_id, order)
    asyncio.create_task(pending_order_timeout(local_order_id))

    return data["invoice_url"], local_order_id


# ----------------------- SEND PAYMENT LINK
async def send_payment_link(bot, chat_id, amount, currency="USDT", network=None):

    url, order_id = await create_invoice(chat_id, amount, currency, network)

    network_text = f" {network.upper()}" if network else ""

    text = (
        f"💳 Оплата: {amount} {currency}{network_text}\n"
        f"🧾 Заказ: #{order_id}\n"
        f"⏳ Время на оплату: 20 минут"
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить", url=url)]])
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    order = get_order(order_id)
    order["message_id"] = msg.message_id
    save_order(order_id, order)


# ----------------------- PENDING TIMEOUT
async def pending_order_timeout(order_id, timeout=1200):

    await asyncio.sleep(timeout)

    order = get_order(order_id)
    if not order or order["status"] != "pending":
        return

    try:
        await bot.delete_message(order["chat_id"], order["message_id"])
    except:
        pass

    order["status"] = "expired"
    save_order(order_id, order)

    await bot.send_message(order["chat_id"], f"⏳ Время оплаты истекло. Заказ #{order_id}")


# ----------------------- IPN ENDPOINT
@router.post("/payment/nowpayments/ipn")
async def nowpayments_ipn_endpoint(request: Request):
    data = await request.json()
    return await nowpayments_ipn(data)


# ----------------------- ОБРАБОТКА IPN
async def nowpayments_ipn(ipn_data: dict):

    print("NOWPayments IPN:", ipn_data)

    invoice_id = str(ipn_data.get("invoice_id"))
    status = ipn_data.get("payment_status")
    actually_paid = float(ipn_data.get("actually_paid", 0))  # реально получено

    if not invoice_id:
        return {"status": "error", "reason": "missing_invoice_id"}

    if status != "finished":
        return {"status": "ok"}  # ждём оплаты

    local_order_id, order = find_order_by_invoice(invoice_id)

    if not order:
        print("Order not found for invoice:", invoice_id)
        return {"status": "ok"}

    if order.get("status") == "paid" or order.get("processing"):
        return {"status": "ok"}

    # --- проверка суммы
    if actually_paid < order["amount"]:
        print(f"Не хватает суммы: поступило {actually_paid}, ожидаем {order['amount']}")
        return {"status": "ok"}

    # --- отмечаем обработку
    order["processing"] = True
    save_order(local_order_id, order)

    try:
        order["status"] = "paid"
        order["paid_at"] = int(datetime.now(timezone.utc).timestamp())
        save_order(local_order_id, order)

        try:
            await bot.delete_message(order["chat_id"], order.get("message_id"))
        except:
            pass

        chat_id = order["chat_id"]

        # --- НАЧИСЛЕНИЕ ПОДПИСКИ ---
        now_ts = datetime.now(timezone.utc).timestamp()
        current_until = float(RAM_DATA.get(chat_id, {}).get("subscription_until", 0))
        base = max(current_until, now_ts)
        new_until = base + 30 * 24 * 60 * 60

        RAM_DATA.setdefault(chat_id, {})
        RAM_DATA[chat_id]["subscription_until"] = new_until
        RAM_DATA[chat_id]["suspended"] = False

        _save_to_redis_partial(chat_id, {
            "subscription_until": new_until,
            "suspended": False
        })

        until_text = datetime.fromtimestamp(new_until, tz=MSK).strftime("%d.%m.%Y %H:%M")

        await send_message_to_user(
            bot, chat_id,
            f"✅ Подписка активна до {until_text}. Заказ #{local_order_id}"
        )

        # --- сообщение админам только после факта оплаты ---
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"💰 Оплата получена\nПользователь: {chat_id}\nЗаказ: #{local_order_id}"
        )

    finally:
        order["processing"] = False
        save_order(local_order_id, order)

    return {"status": "ok"}