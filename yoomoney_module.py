import aiohttp
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

YOOMONEY_WALLET = "4100117872411525"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"

# -----------------------
# RAM-хранилище для платежей (тест)
# -----------------------
PAYMENTS_RAM = {}  # payment_id -> {chat_id, amount, status, comment}

# -----------------------
# Генерация уникального номера платежа
# -----------------------
NEXT_PAYMENT_NUMBER = 1
def get_next_payment_number() -> int:
    global NEXT_PAYMENT_NUMBER
    num = NEXT_PAYMENT_NUMBER
    NEXT_PAYMENT_NUMBER += 1
    return num

# -----------------------
# Создание ссылки на оплату
# -----------------------
def create_payment_link(chat_id: int, amount: float) -> str:
    payment_number = get_next_payment_number()
    comment = f"user_{chat_id}_payment_{payment_number}"

    # Сохраняем временно в RAM для дальнейшей проверки
    PAYMENTS_RAM[comment] = {
        "chat_id": chat_id,
        "amount": amount,
        "status": "pending",
        "payment_number": payment_number
    }

    url = (
        f"https://yoomoney.ru/quickpay/confirm.xml"
        f"?receiver={YOOMONEY_WALLET}"
        f"&quickpay-form=shop"
        f"&targets={comment}"
        f"&sum={amount}"
        f"&currency=643"
        f"&successURL={SUCCESS_REDIRECT_URI}"
    )
    return url, comment

# -----------------------
# Отправка ссылки пользователю
# -----------------------
async def send_payment_link(bot, chat_id: int, amount: float):
    payment_url, comment = create_payment_link(chat_id, amount)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить подписку", url=payment_url)]])
    await bot.send_message(chat_id, f"Сумма к оплате: {amount}₽\nНажмите для оплаты:", reply_markup=keyboard)

# -----------------------
# Обработка уведомлений от YooMoney (Webhook)
# -----------------------
async def handle_payment_notification(data: dict, bot):
    """
    data - словарь, который приходит от YooMoney
    bot - объект telegram.Bot
    """
    # В QuickPay уведомления приходят с полем "operation" или "status" и "targets" (наш comment)
    comment = data.get("targets")  # это наш comment user_{chat_id}_payment_{number}
    status = data.get("status")    # succeeded / canceled / pending

    if comment not in PAYMENTS_RAM:
        return  # неизвестный платеж

    payment_info = PAYMENTS_RAM[comment]
    chat_id = payment_info["chat_id"]

    if status == "succeeded":
        payment_info["status"] = "paid"
        # здесь можно вызвать функцию выдачи подписки
        await bot.send_message(chat_id, f"✅ Оплата подтверждена! Сумма: {payment_info['amount']}₽")
        # удаляем данные из RAM (тест)
        del PAYMENTS_RAM[comment]

    elif status == "canceled":
        payment_info["status"] = "canceled"
        await bot.send_message(chat_id, f"❌ Оплата отменена. Попробуйте снова.")
        del PAYMENTS_RAM[comment]