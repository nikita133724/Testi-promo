import asyncio
import random
from datetime import datetime, time
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# =========================================================
# ИНИЦИАЛИЗАЦИЯ
# =========================================================
BOT = None
ADMIN_CHAT_ID = None
GET_TOKEN = None

def init_yourun(bot, admin_chat_id, get_access_token):
    global BOT, ADMIN_CHAT_ID, GET_TOKEN
    BOT = bot
    ADMIN_CHAT_ID = admin_chat_id
    GET_TOKEN = get_access_token

# =========================================================
# СОСТОЯНИЕ
# =========================================================
STATE = {
    "enabled": False,
    "spam_active": False,
    "watcher_task": None,
    "spam_task": None,
    "phase1_msgs": [],
    "phase2_msgs": [],
    "last_seen_uran": None,
    "balance_snapshot": None,
}
STATE["last_yourun_notify"] = None  # время последнего уведомления
# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================
LAST_MENU_MSG_ID = None

UTC_START = time(16, 0)
UTC_END = time(2, 0)

def in_utc_window():
    now = datetime.utcnow().time()
    return UTC_START <= now or now <= UTC_END

def build_yourun_menu():
    start_stop = InlineKeyboardButton(
        "🛑 STOP" if STATE["enabled"] else "😈 START",
        callback_data="yourun_stop" if STATE["enabled"] else "yourun_start"
    )
    input_button = InlineKeyboardButton("✍️ Ввести сообщение", callback_data="yourun_input")
    cancel_button = InlineKeyboardButton("❌ Отмена", callback_data="yourun_cancel")
    return InlineKeyboardMarkup([[start_stop], [input_button], [cancel_button]])

def build_yourun_input_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="yourun_cancel_input")]])

async def open_yourun_menu(chat_id):
    global LAST_MENU_MSG_ID
    if chat_id != ADMIN_CHAT_ID:
        return None
    try:
        if LAST_MENU_MSG_ID:
            try:
                await BOT.edit_message_text(
                    chat_id=chat_id,
                    message_id=LAST_MENU_MSG_ID,
                    text="⚙️ YouRun control panel",
                    reply_markup=build_yourun_menu()
                )
                print("[LOG] Редактируем существующее меню YouRun")
                return LAST_MENU_MSG_ID
            except Exception as e:
                print(f"[WARN] Не удалось редактировать старое меню: {e}")
                LAST_MENU_MSG_ID = None
        msg = await BOT.send_message(
            chat_id,
            "⚙️ YouRun control panel",
            reply_markup=build_yourun_menu()
        )
        LAST_MENU_MSG_ID = msg.message_id
        print("[LOG] Открываем новое меню YouRun")
        return LAST_MENU_MSG_ID
    except Exception as e:
        print(f"[ERROR] open_yourun_menu: {e}")
        return None

# =========================================================
# WATCHER
# =========================================================
async def chat_watcher():
    print("[LOG] watcher стартовал")
    while STATE["enabled"]:
        await asyncio.sleep(4)
        token = GET_TOKEN(ADMIN_CHAT_ID)
        if not token:
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://cs2run.app/chat/ru/all",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"JWT {token}",
                    },
                ) as r:
                    data = await r.json()
        except Exception as e:
            print(f"[ERROR] watcher fetch: {e}")
            continue

        for msg in data.get("data", {}).get("messages", []):
            user = msg.get("user", {})
            if user.get("name") == "YouRun":
                msg_id = msg.get("id")
                STATE["last_seen_uran"] = msg_id  # просто фиксируем что он был
                
                now_ts = asyncio.get_event_loop().time()
                last_notify = STATE.get("last_yourun_notify")
                
                if not last_notify or (now_ts - last_notify) > 300:
                    try:
                        await BOT.send_message(802085966, "Юран в чате!")
                        print("[LOG] Отправлено уведомление о Юране")
                        STATE["last_yourun_notify"] = now_ts
                    except Exception as e:
                        print(f"[ERROR] Не удалось отправить уведомление: {e}")
                
                    
                    if not STATE["spam_active"] and in_utc_window():
                        STATE["spam_task"] = asyncio.create_task(spam_session())
                break

# =========================================================
# SPAM
# =========================================================
async def spam_session():
    if STATE["spam_active"]:
        print("[LOG] spam_session уже активна — выходим")
        return
    print("[LOG] Запускаем spam_session")
    STATE["spam_active"] = True
    STATE["balance_snapshot"] = await get_balance_snapshot()

    try:
        for phase_msgs, duration in [(STATE["phase1_msgs"], 3*60), (STATE["phase2_msgs"], 3*60)]:
            if not phase_msgs:
                continue
            pool = phase_msgs.copy()
            random.shuffle(pool)
            end = asyncio.get_event_loop().time() + duration
            while asyncio.get_event_loop().time() < end and STATE["enabled"]:
                if not pool:
                    pool = phase_msgs.copy()
                    random.shuffle(pool)
                msg_text = pool.pop()
                print(f"[LOG] Отправляем сообщение: {msg_text}")
                await send_chat(msg_text)
                await asyncio.sleep(random.randint(12, 15) if duration==3*60 else 30)
                stop_spam = await check_balance_change()
                if stop_spam:
                    print("[LOG] Баланс превысил порог, останавливаем спам")
                    return
    finally:
        STATE["spam_active"] = False
        # Сбрасываем snapshot при окончании спама
        STATE["balance_snapshot"] = None
        print("[LOG] Spam session завершена")

# =========================================================
# SEND MESSAGE
# =========================================================
async def send_chat(text):
    token = GET_TOKEN(ADMIN_CHAT_ID)
    if not token:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://cs2run.app/chat/ru",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"JWT {token}",
                },
                json={"text": f"@YouRun, {text}"}
            ) as r:
                if r.status != 200:
                    data = await r.text()
                    print(f"[ERROR] Ошибка отправки сообщения: {r.status} {data}")
                else:
                    print("[LOG] Сообщение отправлено успешно")
    except Exception as e:
        print(f"[ERROR] send_chat exception: {e}")

# =========================================================
# BALANCE
# =========================================================
async def get_balance_snapshot():
    token = GET_TOKEN(ADMIN_CHAT_ID)
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://cs2run.app/v1/user/wallets",
                headers={"Authorization": f"JWT {token}"}
            ) as r:
                data = await r.json()
        snap = {w["id"]: w["balance"] for w in data.get("data", [])}
        return snap
    except Exception as e:
        print(f"[ERROR] get_balance_snapshot: {e}")
        return None

async def check_balance_change():
    if not STATE["spam_active"]:
        return False
    new = await get_balance_snapshot()
    old = STATE["balance_snapshot"]
    if not new or not old:
        return False

    stop = False
    for wid, bal in new.items():
        old_bal = old.get(wid, 0)
        diff = bal - old_bal
        if wid == 3597849 and diff > 1000:  # RUB
            await BOT.send_message(
                ADMIN_CHAT_ID,
                f"💰 Баланс RUB изменился: {bal} ₽"
            )
            stop = True
        elif wid == 188865 and diff > 10:  # USD
            await BOT.send_message(
                ADMIN_CHAT_ID,
                f"💰 Баланс USD изменился: {bal} $"
            )
            stop = True
    if stop:
        # Сбрасываем snapshot, чтобы при следующем запуске старый баланс не учитывался
        STATE["balance_snapshot"] = None
    return stop

# =========================================================
# CALLBACK HANDLER
# =========================================================
async def yourun_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    cid = q.message.chat.id
    if cid != ADMIN_CHAT_ID:
        await q.answer()
        return

    # START / STOP
    if q.data == "yourun_start":
        STATE["enabled"] = True
        print("[LOG] YouRun START")

        # если вдруг остался watcher
        if STATE.get("watcher_task"):
            STATE["watcher_task"].cancel()
            STATE["watcher_task"] = None
        STATE["watcher_task"] = asyncio.create_task(chat_watcher())

        await BOT.edit_message_text(
            chat_id=cid,
            message_id=q.message.message_id,
            text="⚙️ YouRun control panel",
            reply_markup=build_yourun_menu()
        )


    elif q.data == "yourun_stop":
        print("[LOG] YouRun STOP (force reset)")
    
        STATE["enabled"] = False
    
        # 🔴 КРИТИЧНО — полный сброс
        STATE["spam_active"] = False
        STATE["balance_snapshot"] = None
        STATE["spam_task"] = None
        STATE["last_seen_uran"] = None
    
        for k in ("watcher_task", "spam_task"):
            t = STATE.get(k)
            if t:
                t.cancel()
                STATE[k] = None
                print("[LOG] Spam session завершена")

        await BOT.edit_message_text(
            chat_id=cid,
            message_id=q.message.message_id,
            text="⚙️ YouRun control panel",
            reply_markup=build_yourun_menu()
        )

    # Ввод сообщений
    elif q.data == "yourun_input":
        if context.user_data.get("yourun_input_task"):
            context.user_data["yourun_input_task"].cancel()
        context.user_data["awaiting_yourun_input"] = True

        msg = await BOT.edit_message_text(
            chat_id=cid,
            message_id=q.message.message_id,
            text="Введите сообщения для Юры (3 минуты)",
            reply_markup=build_yourun_input_menu()
        )
        context.user_data["yourun_input_msg_id"] = msg.message_id

        async def input_timeout(chat_id, message_id):
            await asyncio.sleep(180)
            if context.user_data.get("awaiting_yourun_input"):
                context.user_data["awaiting_yourun_input"] = False
                try:
                    await BOT.delete_message(chat_id, message_id)
                except:
                    pass
                await open_yourun_menu(chat_id)

        task = asyncio.create_task(input_timeout(cid, msg.message_id))
        context.user_data["yourun_input_task"] = task

    elif q.data == "yourun_cancel_input":
        print("[LOG] Нажата кнопка Отмена ввода")
        if context.user_data.get("yourun_input_task"):
            context.user_data["yourun_input_task"].cancel()
            context.user_data["yourun_input_task"] = None
        context.user_data["awaiting_yourun_input"] = False
        msg_id = context.user_data.get("yourun_input_msg_id")
        if msg_id:
            try:
                await BOT.delete_message(cid, msg_id)
            except:
                pass
            context.user_data["yourun_input_msg_id"] = None
        # Возвращаем главное меню
        await open_yourun_menu(cid)

    elif q.data == "yourun_cancel":
        print("[LOG] Нажата кнопка Отмена главного меню")
        # Просто удаляем меню и сбрасываем LAST_MENU_MSG_ID
        try:
            await BOT.delete_message(cid, q.message.message_id)
        except:
            pass
        global LAST_MENU_MSG_ID
        LAST_MENU_MSG_ID = None


    await q.answer()

# =========================================================
# ОБРАБОТКА ВВОДА
# =========================================================
async def handle_yourun_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    if chat_id != ADMIN_CHAT_ID:
        return False
    if not context.user_data.get("awaiting_yourun_input"):
        return False

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if "Первая фаза" not in text or "Вторая фаза" not in text:
        await BOT.send_message(chat_id, "❌ Формат неверный")
        msg_id = context.user_data.get("yourun_input_msg_id")
        if msg_id:
            try:
                await BOT.delete_message(chat_id, msg_id)
            except:
                pass
            context.user_data["yourun_input_msg_id"] = None
        context.user_data["awaiting_yourun_input"] = False
        return False

    p1, p2 = [], []
    current = None
    for line in lines:
        if line.lower().startswith("первая"):
            current = 1
            continue
        if line.lower().startswith("вторая"):
            current = 2
            continue
        if current == 1:
            p1.append(line)
        elif current == 2:
            p2.append(line)

    STATE["phase1_msgs"] = p1
    STATE["phase2_msgs"] = p2

    context.user_data["awaiting_yourun_input"] = False
    msg_id = context.user_data.get("yourun_input_msg_id")
    if msg_id:
        try:
            await BOT.delete_message(chat_id, msg_id)
        except:
            pass
        context.user_data["yourun_input_msg_id"] = None
    if context.user_data.get("yourun_input_task"):
        context.user_data["yourun_input_task"].cancel()
        context.user_data["yourun_input_task"] = None

    await BOT.send_message(chat_id, "Список сообщений сохранен")
    await open_yourun_menu(chat_id)
    return True

# -----------------------
# ОБРАБОТКА ВВОДА ФАЙЛА
# -----------------------
async def handle_yourun_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_CHAT_ID:
        return

    if not context.user_data.get("awaiting_yourun_input"):
        return

    doc = update.message.document
    if not doc:
        return

    if not doc.file_name.lower().endswith(".txt"):
        await BOT.send_message(chat_id, "❌ Поддерживаются только .txt файлы")
        return

    file = await doc.get_file()
    content = await file.download_as_bytearray()
    try:
        text = content.decode("utf-8")
    except Exception:
        await BOT.send_message(chat_id, "❌ Не удалось прочитать файл. Убедитесь, что кодировка UTF-8")
        return

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    p1, p2 = [], []
    current = None
    for line in lines:
        if line.lower().startswith("первая"):
            current = 1
            continue
        if line.lower().startswith("вторая"):
            current = 2
            continue
        if current == 1:
            p1.append(line)
        elif current == 2:
            p2.append(line)

    if not p1 and not p2:
        await BOT.send_message(chat_id, "❌ Не найдены сообщения для фаз")
        return

    STATE["phase1_msgs"] = p1
    STATE["phase2_msgs"] = p2

    context.user_data["awaiting_yourun_input"] = False
    msg_id = context.user_data.get("yourun_input_msg_id")
    if msg_id:
        try:
            await BOT.delete_message(chat_id, msg_id)
        except:
            pass
        context.user_data["yourun_input_msg_id"] = None
    if context.user_data.get("yourun_input_task"):
        context.user_data["yourun_input_task"].cancel()
        context.user_data["yourun_input_task"] = None

    await BOT.send_message(chat_id, "✅ Сообщения из файла успешно загружены")
    await open_yourun_menu(chat_id)
