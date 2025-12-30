from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio

YOOMONEY_WALLET = "4100117872411525"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"

# внутренний счётчик заказов
NEXT_ORDER_ID = 1

# Хранение всех заказов: {order_id: {"chat_id": int, "amount": int, "status": str}}
ORDERS = {}

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