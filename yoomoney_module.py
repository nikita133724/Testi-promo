# yoomoney_module.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

YOOMONEY_WALLET = "4100117872411525"  
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"

def create_payment_link(chat_id: int, amount: int) -> str:
    comment = f"user_{chat_id}"
    url = (
        f"https://yoomoney.ru/quickpay/confirm.xml"
        f"?receiver={YOOMONEY_WALLET}"
        f"&quickpay-form=shop"
        f"&targets={comment}"
        f"&sum={amount}"
        f"&currency=643"
        f"&successURL={SUCCESS_REDIRECT_URI}"
    )
    return url

async def send_payment_link(bot, chat_id: int, amount: int):
    payment_url = create_payment_link(chat_id, amount)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить подписку", url=payment_url)]])
    await bot.send_message(chat_id, "Нажмите для оплаты:", reply_markup=keyboard)