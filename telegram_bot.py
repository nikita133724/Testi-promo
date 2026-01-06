import json
import asyncio
from decimal import Decimal
from datetime import timezone, timedelta, datetime
MSK = timezone(timedelta(hours=3))
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from redis_client import r
from config import TELEGRAM_BOT_TOKEN, ACTIVE_NOMINALS
import base64
from access_control import prompt_for_key, process_key_input, subscription_watcher, load_keys_from_redis
from yourun_module import (
    init_yourun,
    open_yourun_menu,
    yourun_callback_handler,
    handle_yourun_input,
    handle_yourun_file
)

load_keys_from_redis()
CHATID_KEY = "promo"
ADMIN_CHAT_ID = 8455743587
ARTICLE_URL = "https://t.me/promo_runs/6"

# -----------------------
# RAM-память для всех данных
# -----------------------
RAM_DATA = {}
from subscription_config import get_price        
async def send_message_to_user(bot, chat_id, text, **kwargs):
    msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    await update_user_names_in_ram(msg.chat, persist=True)
    return msg
    
async def update_user_names_in_ram(chat, *, persist=False):
    chat_id = chat.id
    display_name = chat.first_name or ""
    if getattr(chat, "last_name", None):
        display_name += f" {chat.last_name}"

    username = f"@{chat.username}" if getattr(chat, "username", None) else None

    entry = RAM_DATA.setdefault(chat_id, {})
    changed = False
    if entry.get("display_name") != display_name:
        entry["display_name"] = display_name
        changed = True
    if entry.get("username") != username:
        entry["username"] = username
        changed = True
    if persist and changed:
        _save_to_redis_partial(chat_id, {
            "display_name": display_name,
            "username": username
        })
    return entry 
# -----------------------
# Открытые меню с таймерами
# -----------------------
OPEN_SETTINGS_MESSAGES = {}
MENU_TIMEOUT_SECONDS = 180
# -----------------------
# Callback для уведомлений
# -----------------------
NOTIFY_CALLBACK = None

def set_notify_callback(callback):
    global NOTIFY_CALLBACK
    NOTIFY_CALLBACK = callback

async def telegram_notify(chat_id, text):
    try:
        # НЕ обрабатываем это сообщение через handle_message
        await send_message_to_user(bot, chat_id=int(chat_id), text=text)
    except Exception as e:
        print(f"[BOT] send message error: {e}")

# -----------------------
# Redis helpers
# -----------------------
def _save_to_redis_partial(chat_id: str, fields: dict):
    key = str(chat_id)
    raw = r.hget(CHATID_KEY, key)
    if raw:
        data = json.loads(raw)
    else:
        data = {}

    # Создаём копию, чтобы преобразовать Decimal в str
    fields_copy = fields.copy()
    if "active_nominals" in fields_copy:
        fields_copy["active_nominals"] = {str(k): v for k, v in fields_copy["active_nominals"].items()}

    data.update(fields_copy)
    r.hset(CHATID_KEY, key, json.dumps(data))
# -----------------------
# Настройки пользователя
# -----------------------
def get_user_settings(chat_id):
    if chat_id not in RAM_DATA:
        RAM_DATA[chat_id] = {
            "access_token": None,
            "refresh_token": None,
            "next_refresh_time": None,
            "display_name": None,
            "username": None,
            "active_nominals": {Decimal(str(n)): True for n in ACTIVE_NOMINALS},
            "waiting_for_refresh": False,
            "waiting_for_refresh_message_id": None,
            "currency": "USD",
            "waiting_for_currency": False,
            "suspended": True,  # по умолчанию доступ закрыт
            "summary_silent": False  # 🔔 сводка со звуком по умолчанию
        }
    return RAM_DATA[chat_id]

# -----------------------
# Загрузка пользователей из Redis
# -----------------------
def load_chatids():
    chat_ids = set()
    for key_bytes, raw in r.hgetall(CHATID_KEY).items():
        chat_id = int(key_bytes)
        chat_ids.add(chat_id)
        obj = json.loads(raw)

        # Обработка next_refresh_time
        nxt = obj.get("next_refresh_time")
        if isinstance(nxt, str):
            try:
                # пытаемся распарсить ISO строку
                dt = datetime.fromisoformat(nxt)
                nxt_timestamp = int(dt.replace(tzinfo=timezone.utc).timestamp())
                # сохраняем обратно в Redis в виде int
                _save_to_redis_partial(chat_id, {"next_refresh_time": nxt_timestamp})
            except Exception:
                nxt_timestamp = None
        elif isinstance(nxt, (int, float)):
            nxt_timestamp = int(nxt)
        else:
            nxt_timestamp = None

        RAM_DATA[chat_id] = {
            "access_token": obj.get("access_token"),
            "refresh_token": obj.get("refresh_token"),
            "next_refresh_time": nxt_timestamp,
            "display_name": obj.get("display_name"),
            "username": obj.get("username"),
            "active_nominals": {Decimal(k): v for k, v in obj.get("active_nominals", {}).items()} 
                               if obj.get("active_nominals") else {Decimal(str(n)): True for n in ACTIVE_NOMINALS},
            "waiting_for_refresh": False,
            "waiting_for_refresh_message_id": None,
            "currency": obj.get("currency", "USD"),
            "waiting_for_currency": False,
            "suspended": obj.get("suspended", False),
            "subscription_until": obj.get("subscription_until"),
            "notified_24h": obj.get("notified_24h", False),
            "summary_silent": obj.get("summary_silent", False)
        }
    return chat_ids

chat_ids = load_chatids()

# -----------------------
# Инициализация бота
# -----------------------
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
bot = app.bot
set_notify_callback(telegram_notify)

from refresh_tokens import init_token_module
from admin_users import AdminUsers
admin_users_module = AdminUsers(RAM_DATA, bot)

init_token_module(
    RAM_DATA,
    _save_to_redis_partial,
    telegram_notify
)

init_yourun(
    bot=bot,
    admin_chat_id=ADMIN_CHAT_ID,
    get_access_token=lambda cid: RAM_DATA.get(cid, {}).get("access_token")
)
# -----------------------
# Добавляем команду для покупки подписки
from yoomoney_module import send_payment_link
from nowpayments_module import send_payment_link as send_crypto_payment_link
async def buy_subscription(update, context):
    chat_id = update.effective_chat.id
    from subscription_config import get_price
    amount = get_price("basic")  # сумма подписки
    await send_payment_link(bot, chat_id, amount)

app.add_handler(CommandHandler("buy", buy_subscription))
# -----------------------
# Постоянная клавиатура
# -----------------------
def build_reply_keyboard(chat_id):
    settings = get_user_settings(chat_id)

    # ⛔ если доступ закрыт — только кнопка активации
    if settings.get("suspended", True):
        return ReplyKeyboardMarkup([["Активировать доступ"]], resize_keyboard=True)

    rows, row = [], []
    for n in ACTIVE_NOMINALS:
        key = Decimal(str(n))
        color = "🟢" if settings["active_nominals"].get(key, True) else "🔴"
        row.append(f"{color} {n}$")
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append(["👤 Профиль"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)
# -----------------------
# Профиль пользователя
# -----------------------
async def open_user_profile(chat_id):
    # если профиль уже открыт — удаляем старый
    if chat_id in OPEN_SETTINGS_MESSAGES:
        old = OPEN_SETTINGS_MESSAGES[chat_id]
        try:
            await bot.delete_message(chat_id, old["message_id"])
        except:
            pass

        task = old.get("task")
        if task:
            task.cancel()

        OPEN_SETTINGS_MESSAGES.pop(chat_id, None)

    from admin_users import extract_user_id_from_refresh

    settings = get_user_settings(chat_id)
    currency = settings.get("currency", "USD")

    # Проверка подписки
    if settings.get("suspended", True):
        keyboard = ReplyKeyboardMarkup([["Активировать доступ"]], resize_keyboard=True)
        await send_message_to_user(
            bot,
            chat_id,
            "⏰ Ваша подписка закончилась.\nЧтобы снова получить доступ, нажмите кнопку ниже 👇",
            reply_markup=keyboard
        )
        return

    # Никнейм пользователя
    try:
        user = await bot.get_chat(chat_id)
        nickname = user.username if user.username else (user.full_name if user.full_name else "Неизвестно")
    except:
        nickname = "Неизвестно"

    # ID профиля из refresh_token
    user_id = extract_user_id_from_refresh(settings["refresh_token"]) if settings.get("refresh_token") else None

    # Подписка
    subscription_until_ts = settings.get("subscription_until")
    from datetime import timezone, timedelta
    MSK = timezone(timedelta(hours=3))
    if isinstance(subscription_until_ts, (int, float)):
        local_dt = datetime.fromtimestamp(subscription_until_ts, tz=timezone.utc).astimezone(MSK)
        subscription_text = local_dt.strftime("%d.%m.%Y %H:%M") + " МСК"
    else:
        subscription_text = "Неизвестно"

    # Следующий refresh
    refresh_ts = settings.get("next_refresh_time")
    if isinstance(refresh_ts, (int, float)):
        refresh_text = datetime.fromtimestamp(refresh_ts).strftime("%d.%m.%Y %H:%M")
    else:
        refresh_text = "не задано"

    # Формируем текст профиля
    text = (
        f"👤 Профиль пользователя\n\n"
        f"Никнейм TG: {nickname}\n"
        f"ID профиля run'a: {user_id}\n\n"
        f"Валюта: {currency}\n\n"
        f"Подписка активна до:\n🕒 {subscription_text}\n\n"
        f"Следующее обновление токенов:\n🔄 {refresh_text}"
    )

    # Кнопки
    keyboard = [
        [InlineKeyboardButton("💳 Купить подписку", callback_data="profile_buy_confirm")],
        [InlineKeyboardButton("📄 Транзакции", callback_data="profile_transactions")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="profile_settings")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="profile_exit")]
    ]

    msg = await send_message_to_user(bot, chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

    OPEN_SETTINGS_MESSAGES[chat_id] = {
        "message_id": msg.message_id,
        "menu_type": "profile"
    }

    # таймер авто-закрытия
    reset_menu_timer(chat_id, 120)
    
# -----------------------
# Таймер для удаления меню
# -----------------------
async def remove_open_menu(chat_id):
    if chat_id not in OPEN_SETTINGS_MESSAGES:
        return
    menu_data = OPEN_SETTINGS_MESSAGES[chat_id]
    try:
        await bot.delete_message(chat_id=chat_id, message_id=menu_data["message_id"])
    except:
        pass
    del OPEN_SETTINGS_MESSAGES[chat_id]

def reset_menu_timer(chat_id, delay=None):
    if chat_id in OPEN_SETTINGS_MESSAGES:
        task = OPEN_SETTINGS_MESSAGES[chat_id].get("task")
        if task:
            task.cancel()
    delay = MENU_TIMEOUT_SECONDS if delay is None else delay
    task = asyncio.create_task(menu_timer_task(chat_id, delay))
    if chat_id in OPEN_SETTINGS_MESSAGES:
        OPEN_SETTINGS_MESSAGES[chat_id]["task"] = task
        
async def menu_timer_task(chat_id, delay):
    try:
        await asyncio.sleep(delay)
        await remove_open_menu(chat_id)
    except asyncio.CancelledError:
        return

# -----------------------
# /start
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_user_settings(chat_id)
    await update_user_names_in_ram(update.effective_chat, persist=True)
    # если новый пользователь — добавляем его в chat_ids и выставляем suspended=True
    if chat_id not in chat_ids:
        chat_ids.add(chat_id)
        settings["suspended"] = True
        _save_to_redis_partial(chat_id, {
            "suspended": True,
            "display_name": settings["display_name"],
            "username": settings["username"]
        })
    # 🔍 Проверка истечения подписки при /start (для старых пользователей)
    if settings.get("suspended") is False:
        until = settings.get("subscription_until")
    
        if isinstance(until, (int, float)):
            if datetime.now().timestamp() >= until:
                settings["suspended"] = True
                settings.pop("subscription_until", None)
    
                _save_to_redis_partial(chat_id, {
                    "suspended": True,
                    "subscription_until": None
                })


    # проверяем статус suspended
    if settings.get("suspended", True):
        # Inline-кнопка на статью
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Подробнее", url=ARTICLE_URL)]
        ])
        # Reply-кнопка «Активировать доступ»
        reply_keyboard = ReplyKeyboardMarkup(
            [["Активировать доступ"]],
            resize_keyboard=True
        )
    
        # Сначала отправляем текст с inline-кнопкой
        await update.message.reply_text(
            "Добро пожаловать в небольшое комьюнити лудоманов CSGORUN’а!\n\n"
            "Чтобы узнать больше о боте и его преимуществах, нажмите кнопку Подробнее ",
            reply_markup=inline_keyboard
        )
    
        # Потом отправляем Reply-кнопку «Активировать доступ»
        await update.message.reply_text(
            "Нажмите кнопку ниже, чтобы активировать доступ.\n\n при нажатие активировать доступ создается ссылка на оплату подписки(30дней)",
            reply_markup=reply_keyboard
        )
    else:
        # пользователь с активной подпиской — показываем основное меню
        await update.message.reply_text(
            "Добро пожаловать обратно!",
            reply_markup=build_reply_keyboard(chat_id)
        )
# -----------------------
# Асинхронная обёртка для refresh_by_refresh_token
# -----------------------
async def async_refresh_token(chat_id, token):
    from refresh_tokens import refresh_by_refresh_token_async
    await refresh_by_refresh_token_async(chat_id, refresh_token=token, bot=bot)
# -----------------------
# Обработчик сообщений
# -----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    settings = get_user_settings(chat_id)

    # -------------------
    # Блокировка /users для всех кроме админа
    if text.lower() == "/users" and chat_id != ADMIN_CHAT_ID:
        return
    
    # Кнопка "Активировать доступ"
    if text == "Активировать доступ":
        from yoomoney_module import ORDERS, send_payment_link
        from subscription_config import get_price
    
        # Проверяем, есть ли уже заказ в статусе pending
        pending_orders = [o for o in ORDERS.values() if o["chat_id"] == chat_id and o["status"] == "pending"]
        if pending_orders:
            await update.message.reply_text(
                "⏳ У вас уже есть активный заказ. Подождите 5 минут или завершите текущую оплату."
            )
            return
    
        # Создаём новый заказ
        amount = get_price("basic")
        await send_payment_link(bot, chat_id, amount)
        return
        
    # Ввод ключа активации
    if settings.get("waiting_for_key"):
        from access_control import process_key_input
        await process_key_input(update, context)
        return

    # -------------------
    # Если ждём выбор валюты — ничего не принимаем
    if settings.get("waiting_for_currency"):
        return

    # -------------------
    # Ожидание refresh token
    if settings.get("waiting_for_refresh"):
        parts = text.split(".")
        invalid = False

        if len(parts) != 3:
            invalid = True
        else:
            try:
                payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
                payload_json = base64.urlsafe_b64decode(payload_b64.encode())
                payload = json.loads(payload_json)
                if not all(k in payload for k in ["id", "iat", "exp"]):
                    invalid = True
            except Exception:
                invalid = True

        if invalid:
            settings["waiting_for_refresh"] = False
            if settings.get("waiting_for_refresh_message_id"):
                try:
                    await bot.delete_message(
                        chat_id,
                        settings["waiting_for_refresh_message_id"]
                    )
                except:
                    pass
                settings["waiting_for_refresh_message_id"] = None

            await update.message.reply_text(
                "❌ Это не refresh token",
                reply_markup=build_reply_keyboard(chat_id)
            )
            return

        # токен валидный
        settings["waiting_for_refresh"] = False
        if settings.get("waiting_for_refresh_message_id"):
            try:
                await bot.delete_message(
                    chat_id,
                    settings["waiting_for_refresh_message_id"]
                )
            except:
                pass
            settings["waiting_for_refresh_message_id"] = None

        asyncio.create_task(async_refresh_token(chat_id, text))
        return

    # ------------------- ✅ УВЕДОМЛЕНИЯ ОТ АДМИНА
    if chat_id == ADMIN_CHAT_ID:
        handled = await admin_users_module.handle_admin_message(update.message)
        if handled:
            return
        handled = await handle_yourun_input(update, context)
        if handled:
            return
 
    # -------------------
    # Переключение номиналов
    if text.endswith("$"):
        try:
            amount = Decimal(
                text.replace("🟢", "")
                    .replace("🔴", "")
                    .replace("$", "")
                    .strip()
            )
        except Exception:
            return

        settings["active_nominals"][amount] = not settings["active_nominals"].get(amount, True)

        _save_to_redis_partial(chat_id, {
            "active_nominals": {
                str(k): v for k, v in settings["active_nominals"].items()
            }
        })

        await update.message.reply_text(
            f"Номинал {amount}$ теперь "
            f"{'активен' if settings['active_nominals'][amount] else 'неактивен'}",
            reply_markup=build_reply_keyboard(chat_id)
        )

        reset_menu_timer(chat_id, 150)
        return

    # -------------------
    # Открытие настроек
    if text == "Настройки":
        try:
            await update.message.delete()
        except:
            pass
        await open_settings_menu(chat_id, bot)
        return
   
    # Открытие профиля
    if text == "👤 Профиль":
        try:
            await update.message.delete()
        except:
            pass
        await open_user_profile(chat_id)
        return
    
# -----------------------
# Функция открытия меню настроек
# -----------------------
async def open_settings_menu(chat_id, bot):
    # Удаляем старое меню, если есть
    old = OPEN_SETTINGS_MESSAGES.get(chat_id)
    if old:
        try:
            await bot.delete_message(chat_id, old["message_id"])
        except:
            pass
        task = old.get("task")
        if task:
            task.cancel()
        OPEN_SETTINGS_MESSAGES.pop(chat_id, None)

    settings = get_user_settings(chat_id)
    summary_button_text = "Тихий режим ✅" if settings["summary_silent"] else "Тихий режим ❌"

    keyboard = [
        [InlineKeyboardButton("🔐 Авторизация CSGORUN", callback_data="settings_csgorun_auth")],
        [InlineKeyboardButton("💱 Валюта", callback_data="settings_currency")],
        [InlineKeyboardButton(summary_button_text, callback_data="settings_summary_silent")]
    ]
    if chat_id == ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("👥 Юзеры", callback_data="settings_users")])
        keyboard.append([InlineKeyboardButton("🔑 Генерация ключей", callback_data="settings_keygen")])
        keyboard.append([InlineKeyboardButton("YouRun", callback_data="menu_yourun")])
    keyboard.append([InlineKeyboardButton("❌ Выход", callback_data="settings_exit")])

    try:
        msg = await send_message_to_user(bot, chat_id, text="Настройки бота:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Ошибка при открытии меню настроек: {e}")
        return

    OPEN_SETTINGS_MESSAGES[chat_id] = {"message_id": msg.message_id, "menu_type": "settings_main"}
    reset_menu_timer(chat_id, 150)
# -----------------------
# Обработчик нажатий inline-кнопок
# -----------------------
async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await update_user_names_in_ram(query.message.chat, persist=True)
    chat_id = query.message.chat.id
    if OPEN_SETTINGS_MESSAGES.get(chat_id, {}).get("menu_type") == "profile":
    
        # Нажатие "Купить подписку"
        if query.data == "profile_buy_confirm":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Да", callback_data="profile_buy_yes"),
                    InlineKeyboardButton("❌ Нет", callback_data="profile_buy_no")
                ]
            ])
            await query.message.edit_text(
                "Вы уверены, что хотите приобрести подписку на 30 дней?",
                reply_markup=keyboard
            )
            return
    
        # Нажатие "Нет" — возвращаем профиль
        elif query.data == "profile_buy_no":
            await query.message.delete()
            await open_user_profile(chat_id)
            return
    
        # Нажатие "Да" — показываем выбор способа оплаты
        elif query.data == "profile_buy_yes":
            # Выбор способа оплаты
            keyboard = [
                [InlineKeyboardButton("💳 Карта РФ", callback_data="pay_yoomoney")],
                [InlineKeyboardButton("₿ Крипта", callback_data="pay_crypto")],
                [InlineKeyboardButton("❌ Отмена", callback_data="profile_buy_no")]
            ]
            await query.message.edit_text(
                "Выберите способ оплаты подписки на 30 дней:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # -----------------------
        # Оплата картой РФ
        elif query.data == "pay_yoomoney":
            from subscription_config import get_price
            from yoomoney_module import send_payment_link
        
            amount = get_price("basic")
            await send_payment_link(bot, query.message.chat.id, amount)
        
            await query.message.delete()
            await open_user_profile(query.message.chat.id)
            return
        
        # -----------------------
        # Выбор крипты
        elif query.data == "pay_crypto":
            # показываем выбор валюты
            keyboard = [
                [InlineKeyboardButton("💵 USD", callback_data="crypto_usd")],
                [InlineKeyboardButton("🌐 TRX", callback_data="crypto_trx")],
                [InlineKeyboardButton("🪙 TON", callback_data="crypto_ton")],
                [InlineKeyboardButton("❌ Отмена", callback_data="profile_buy_no")]
            ]
            await query.message.edit_text(
                "Выберите криптовалюту для оплаты подписки:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # -----------------------
        # Обработка выбора криптовалюты
        elif query.data in ["crypto_usd", "crypto_trx", "crypto_ton"]:
            crypto_map = {
                "crypto_usd": "USD",
                "crypto_trx": "TRX",
                "crypto_ton": "TON"
            }
            currency = crypto_map[query.data]
        
            from subscription_config import get_price
            from nowpayments_module import send_payment_link as send_crypto_payment_link
        
            amount = get_price("basic")
        
            # отправляем ссылку на оплату криптой
            await send_crypto_payment_link(bot, query.message.chat.id, amount, currency=currency)
        
            # уведомляем админа
            try:
                await bot.send_message(
                    ADMIN_CHAT_ID,
                    f"💰 Пользователь {query.message.chat.id} выбрал оплату криптой.\n"
                    f"Сумма: {amount} {currency}"
                )
            except Exception as e:
                print(f"[ADMIN NOTIFY ERROR] {e}")
        
            # закрываем меню выбора
            await query.message.delete()
            await open_user_profile(query.message.chat.id)
            return
        
        if query.data == "profile_transactions":
            from yoomoney_module import get_last_orders
            
            last_orders = get_last_orders(chat_id, 4)
            if not last_orders:
                text = "У вас ещё нет покупок."
            else:
                lines = []
                for order_id, o in last_orders:
                    amount = o["amount"]
                    ts = datetime.fromtimestamp(o["created_at"], tz=MSK).strftime("%d.%m.%Y %H:%M") + " МСК"
                    
                    status_map = {
                        "paid": "Оплачено",
                        "pending": "Ожидание",
                        "canceled": "Отмена",
                        "expired": "Отмена",
                        "failed": "Ошибка"
                    }
                    status = status_map.get(o["status"].lower(), o["status"].capitalize())
                
                    lines.append(f"Заказ: #{order_id} | Сумма: {amount}₽ | Статус: {status} | Дата: {ts}")
                text = "\n".join(lines)
        
            # Кнопка назад
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="profile_back")]
            ]
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            reset_menu_timer(chat_id, 120)
            
        elif query.data == "profile_back":
            # Возвращаем профиль
            await query.message.delete()
            await open_user_profile(chat_id)
            
        # ⚙️ Переход в настройки из профиля
        if query.data == "profile_settings":
            # сбрасываем таймер профиля
            reset_menu_timer(chat_id, 120)
    
            # удаляем сообщение профиля
            try:
                await query.message.delete()
            except:
                pass
    
            # открываем меню настроек
            await open_settings_menu(chat_id, bot)
            return
    
        # ❌ Выход из профиля
        elif query.data == "profile_exit":
            # останавливаем таймер
            task = OPEN_SETTINGS_MESSAGES.get(chat_id, {}).get("task")
            if task:
                task.cancel()
    
            await query.message.delete()
            OPEN_SETTINGS_MESSAGES.pop(chat_id, None)
    
            await send_message_to_user(
                bot,
                chat_id,
                "Возврат в меню",
                reply_markup=build_reply_keyboard(chat_id)
            )
            return
    settings = get_user_settings(chat_id)
    
    # Обновляем таймер меню
    menu = OPEN_SETTINGS_MESSAGES.get(chat_id)
    if menu and menu.get("menu_type") == "settings_main":
        reset_menu_timer(chat_id, 150)
        
    # -----------------------
    # Авторизация CSGORUN
    if query.data == "settings_csgorun_auth":
        chat_id = query.message.chat.id
    
        url = f"https://tg-bot-test-gkbp.onrender.com/auth/start?chat_id={chat_id}"
    
        text = (
            "🔐 Авторизация CSGORUN\n\n"
            "Нажмите на ссылку ниже для авторизации:\n\n"
            f"{url}\n\n"
            "После авторизации вернитесь в бота."
        )
    
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="settings_back")]
            ])
        )
    
        reset_menu_timer(chat_id, 180)
        return
    
    elif query.data == "settings_back":
        await open_settings_menu(chat_id, bot)
        return
    # -----------------------
    # Настройки Refresh Token
    elif query.data == "settings_refresh":
        await query.message.delete()
        settings["waiting_for_refresh"] = True
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="refresh_cancel")]]
        msg = await send_message_to_user(bot, chat_id, "Отправьте Refresh Token", reply_markup=InlineKeyboardMarkup(keyboard))
        settings["waiting_for_refresh_message_id"] = msg.message_id
        OPEN_SETTINGS_MESSAGES[chat_id] = {"message_id": msg.message_id, "menu_type": "refresh"}
        reset_menu_timer(chat_id, 180)

    # -----------------------
    # Настройки Валюты
    elif query.data == "settings_currency":
        keyboard = [
            [InlineKeyboardButton("Рубли", callback_data="currency_rub")],
            [InlineKeyboardButton("Доллары", callback_data="currency_usd")],
            [InlineKeyboardButton("❌ Выход", callback_data="currency_exit")]
        ]
        msg = await query.message.edit_text("Выберите валюту:", reply_markup=InlineKeyboardMarkup(keyboard))
        OPEN_SETTINGS_MESSAGES[chat_id] = {"message_id": msg.message_id, "menu_type": "currency"}
        reset_menu_timer(chat_id, 120)

    # -----------------------
    # Список пользователей (админ)
    elif query.data == "settings_users":
        if chat_id != ADMIN_CHAT_ID:
        
            return
    
        # ⛔ останавливаем таймер
        if chat_id in OPEN_SETTINGS_MESSAGES:
            task = OPEN_SETTINGS_MESSAGES[chat_id].get("task")
            if task:
                task.cancel()
                OPEN_SETTINGS_MESSAGES[chat_id]["task"] = None
    
        await admin_users_module.show_users(chat_id, query=query)
    
        # 🧭 помечаем режим меню
        OPEN_SETTINGS_MESSAGES[chat_id] = {
            "message_id": query.message.message_id,
            "menu_type": "users",
            "task": None
        }
    # Генерация ключей (админ)
    elif query.data == "settings_keygen":
        if chat_id != ADMIN_CHAT_ID:
        
            return
    
        # отключаем таймер для keygen
        if chat_id in OPEN_SETTINGS_MESSAGES:
            task = OPEN_SETTINGS_MESSAGES[chat_id].get("task")
            if task:
                task.cancel()
    
        # помечаем меню keygen, таймер не нужен
        OPEN_SETTINGS_MESSAGES[chat_id] = {
            "message_id": query.message.message_id,
            "menu_type": "keygen",
            "task": None
        }
    
    
        await admin_users_module.open_key_generation_menu(chat_id, query=query)
        return
    
    # Обработка callback внутри keygen
    elif query.data.startswith("keygen_") or query.data == "keygen_cancel":
        if chat_id != ADMIN_CHAT_ID:
        
            return
        # передаем в модуль админа обработку
        await admin_users_module.handle_keygen_callback(chat_id, query.data, query=query)
        return
    
    
    elif query.data == "menu_yourun":
    
        if chat_id != ADMIN_CHAT_ID:
            await query.message.edit_text("Доступ запрещен")
            return
    
        # Удаляем старое меню, если есть
        old_menu = OPEN_SETTINGS_MESSAGES.get(chat_id)
        if old_menu and old_menu.get("menu_type") != "yourun":
            try:
                await bot.delete_message(chat_id, old_menu["message_id"])
            except:
                pass
        
        # Открываем меню YouRun
        try:
            msg_id = await open_yourun_menu(chat_id)  # <- возвращает int
        except Exception as e:
            print(f"Error opening YouRun menu: {e}")
            await query.message.edit_text("Ошибка открытия YouRun")
            return
        
        if msg_id is None:
            await query.message.edit_text("Ошибка открытия YouRun")
            return
        
        # Сохраняем меню
        OPEN_SETTINGS_MESSAGES[chat_id] = {
            "message_id": msg_id,
            "menu_type": "yourun"
        }
        
        reset_menu_timer(chat_id)
        
    # Пагинация пользователей
    elif query.data.startswith("users_next"):
        await admin_users_module.paginate(chat_id, "next", query=query)
    elif query.data.startswith("users_back"):
        await admin_users_module.paginate(chat_id, "back", query=query)

    
    # Работа с токенами пользователя
    elif query.data.startswith("user_tokens_"):
        uid = int(query.data.split("_")[2])
        await admin_users_module.show_tokens(chat_id, uid, query=query)

    # Пауза пользователя
    elif query.data.startswith("user_pause_"):
        uid = int(query.data.split("_")[2])
        await admin_users_module.pause_user(chat_id, uid, query=query)
        
    elif query.data.startswith("user_"):
        uid = int(query.data.split("_")[1])
        await admin_users_module.show_user_info(chat_id, uid, query=query)

    # Выход из меню пользователей
    elif query.data == "users_exit":
        await query.message.delete()
        await open_settings_menu(chat_id, bot)

    # -----------------------
    # Выход из настроек
    elif query.data == "settings_exit":
        await query.message.delete()
        if chat_id in OPEN_SETTINGS_MESSAGES:
            del OPEN_SETTINGS_MESSAGES[chat_id]
        await send_message_to_user(bot, chat_id=chat_id, text="выход из меню настроек", reply_markup=build_reply_keyboard(chat_id))

    # -----------------------
    # Выбор валюты
    elif query.data == "currency_rub":
        settings["currency"] = "RUB"
        settings["waiting_for_currency"] = False
        await query.message.delete()
        if chat_id in OPEN_SETTINGS_MESSAGES:
            del OPEN_SETTINGS_MESSAGES[chat_id]
        _save_to_redis_partial(chat_id, {"currency": settings["currency"]})
        await send_message_to_user(bot, chat_id, f"✅ Выбрана валюта: {settings['currency']}", reply_markup=build_reply_keyboard(chat_id))

    elif query.data == "currency_usd":
        settings["currency"] = "USD"
        settings["waiting_for_currency"] = False
        await query.message.delete()
        if chat_id in OPEN_SETTINGS_MESSAGES:
            del OPEN_SETTINGS_MESSAGES[chat_id]
        _save_to_redis_partial(chat_id, {"currency": settings["currency"]})
        await send_message_to_user(bot, chat_id, f"✅ Выбрана валюта: {settings['currency']}", reply_markup=build_reply_keyboard(chat_id))
    
    elif query.data == "settings_summary_silent":
        settings["summary_silent"] = not settings["summary_silent"]
    
        _save_to_redis_partial(chat_id, {
            "summary_silent": settings["summary_silent"]
        })
    
        summary_button_text = (
            "Тихий режим ✅"
            if settings["summary_silent"]
            else "Тихий режим ❌"
        )
    
        keyboard = [
            [InlineKeyboardButton("🔐 Авторизация CSGORUN", callback_data="settings_csgorun_auth")],
            [InlineKeyboardButton("💱 Валюта", callback_data="settings_currency")],
            [InlineKeyboardButton(summary_button_text, callback_data="settings_summary_silent")]
        ]
    
        if chat_id == ADMIN_CHAT_ID:
            keyboard.append([InlineKeyboardButton("👥 Юзеры", callback_data="settings_users")])
            keyboard.append([InlineKeyboardButton("🔑 Генерация ключей", callback_data="settings_keygen")])
            keyboard.append([InlineKeyboardButton("YouRun", callback_data="menu_yourun")])
        keyboard.append([InlineKeyboardButton("❌ Выход", callback_data="settings_exit")])
    
        await query.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
        await query.answer(
            "🔕 Сводка без звука"
            if settings["summary_silent"]
            else "🔔 Сводка со звуком"
        )
        reset_menu_timer(chat_id)

    # -----------------------
    # Отмена операций
    elif query.data in ["currency_exit", "refresh_cancel"]:
        if query.data == "refresh_cancel":
            settings["waiting_for_refresh"] = False
        settings["waiting_for_currency"] = False
        await query.message.delete()
        if chat_id in OPEN_SETTINGS_MESSAGES:
            del OPEN_SETTINGS_MESSAGES[chat_id]
        await send_message_to_user(bot, chat_id, text="Меню", reply_markup=build_reply_keyboard(chat_id))
        
        
# -----------------------
# Аварийная команда обновления токена
# -----------------------
async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_user_settings(chat_id)

    settings["waiting_for_refresh"] = True

    msg = await update.message.reply_text("Отправьте  Token:")

    settings["waiting_for_refresh_message_id"] = msg.message_id
        
        
# -----------------------
# Регистрация обработчиков
# -----------------------
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("token", token_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler(filters.Document.FileExtension("txt"), handle_yourun_file))
app.add_handler(CallbackQueryHandler(admin_users_module.handle_callback, pattern="^notify_(all|user|cancel)$"))
app.add_handler(CallbackQueryHandler(yourun_callback_handler,pattern="^yourun_"))
app.add_handler(CallbackQueryHandler(settings_callback, pattern="^(settings_|currency_|refresh_|users_|user_|profile_|menu_yourun)"))
app.add_handler(CallbackQueryHandler(settings_callback, pattern="^settings_keygen$"))
app.add_handler(CallbackQueryHandler(settings_callback, pattern="^keygen_|keygen_cancel$"))
app.add_handler(CallbackQueryHandler(settings_callback))
# -----------------------
# Функция для отправки сводки
# -----------------------
async def send_summary(chat_id: int, summary: list):
    settings = RAM_DATA.get(chat_id, {})
    silent = settings.get("summary_silent", False)

    if not summary:
        return
    title = "🔕 Сводка по посту:\n" if silent else "Сводка по посту:\n"
    message_text = title
    for item in summary:
        if item["promo_code"] is not None:
            message_text += f"{item['nominal']}$ | {item['promo_code']} | {item['status']}\n"
        else:
            message_text += f"\n{item['status']}\n"  # отдельная строка для времени активации

    try:
        markup = build_reply_keyboard(chat_id)
        await send_message_to_user(bot, chat_id=chat_id, text=message_text, reply_markup=markup, disable_notification=silent)
    except Exception as e:
        print(f"Ошибка отправки сводки {chat_id}: {e}")