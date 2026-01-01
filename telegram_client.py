from telethon import TelegramClient, events
from telethon.tl.types import MessageEntitySpoiler, MessageEntityCode, MessageEntityPre, MessageEntityCustomEmoji
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post
import asyncio
import time

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY]
SPECIAL_USERNAME = CHANNEL_SPECIAL.lstrip("@").lower()
POST_CACHE = {}
LAST_SEEN_POLL_ID = 0

ME = "me"   # Избранное
DETECTION_LOG = {}  # msg_id -> {"event": t, "poll": t}
# -----------------------------
import re

def extract_special_promos(msg):
    """
    Извлечение промо-кодов:
    - Берём только entity типа Code, Pre, Spoiler
    - Игнорируем все CustomEmoji или пробелы перед entity
    - Берём только буквенно-цифровой код длиной 4-32 символа
    """
    if not msg.entities:
        return []

    full_text = msg.raw_text or msg.message or ""
    results = []

    for ent in msg.entities:
        if isinstance(ent, (MessageEntityCode, MessageEntitySpoiler, MessageEntityPre)):
            start = ent.offset
            end = ent.offset + ent.length

            # смещаем start на все предшествующие символы, которые могут быть частью кода
            while start > 0:
                prev_char = full_text[start-1]
                # если это буква/цифра — включаем в entity
                if re.match(r'[A-Za-zА-Яа-я0-9]', prev_char):
                    start -= 1
                # если это CustomEmoji — игнорируем
                elif any(isinstance(ce, MessageEntityCustomEmoji) and ce.offset <= start-1 < ce.offset+ce.length for ce in msg.entities):
                    start -= 1
                else:
                    break

            entity_text = full_text[start:end].strip()

            # Берём только буквенно-цифровой код внутри entity
            match = re.search(r'([A-Za-zА-Яа-я0-9]{4,32})', entity_text)
            if match:
                results.append(match.group(1))

    return results

# -----------------------------
# Обычные каналы через events
@client.on(events.NewMessage(chats=channels))
async def ordinary_handler(event):
    msg = event.message
    
    t = time.perf_counter()
    DETECTION_LOG.setdefault(msg.id, {})["event"] = t
    print(f"[EVENT] msg.id={msg.id} at {t}")
    
    text = msg.message or ""
    media = msg.media

    if text:
        await handle_new_post(text, media)

    POST_CACHE.setdefault(event.chat_id, {})[msg.id] = {
        "text": text,
        "timestamp": time.time()
    }
    asyncio.create_task(track_post_changes(event.chat_id, msg.id, media, is_special_channel=False))

# -----------------------------
async def track_post_changes(chat_id, message_id, media=None, is_special_channel=False):
    CHECK_INTERVAL = 4
    TIMEOUT = 5 * 60
    start_time = time.time()

    while time.time() - start_time < TIMEOUT:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            msg = await client.get_messages(chat_id, ids=message_id)
            if not msg:
                continue
            new_text = msg.message or ""
        except Exception as e:
            print(f"[track_post_changes] Ошибка: {e}")
            continue

        old_text = POST_CACHE.get(chat_id, {}).get(message_id, {}).get("text")
        if old_text is None or new_text == old_text:
            continue

        POST_CACHE[chat_id][message_id]["text"] = new_text
        print(f"[UPDATE] Пост {message_id} изменён!")

        # Обработка промо
        codes = extract_special_promos(msg)
        if codes:
            for code in codes:
                fake_line = f"0.25$ — {code}"
                await handle_new_post(fake_line, media)
        elif not is_special_channel:
            await handle_new_post(new_text, media)


# -----------------------------
async def poll_special_channel():
    global LAST_SEEN_POLL_ID

    print("[POLL] realtime polling started")

    while not client.is_connected():
        await asyncio.sleep(0.2)

    while True:
        try:
            msgs = await client.get_messages(CHANNEL_SPECIAL, limit=1)
            if not msgs:
                await asyncio.sleep(0.15)
                continue

            msg = msgs[0]

            if msg.id <= LAST_SEEN_POLL_ID:
                await asyncio.sleep(0.15)
                continue

            LAST_SEEN_POLL_ID = msg.id

            # 🧪 фиксация времени POLL
            t = time.perf_counter()
            DETECTION_LOG.setdefault(msg.id, {})["poll"] = t
            print(f"[POLL ] msg.id={msg.id} at {t}")

            # 🧮 считаем Δ
            data = DETECTION_LOG[msg.id]
            if "event" in data:
                delta = data["poll"] - data["event"]
                text = f"Δ = POLL - EVENT = {delta:.6f} сек"
                await client.send_message(ME, text)

            # 🔽 твоя логика обработки промо — НИЧЕГО не теряем
            codes = extract_special_promos(msg)
            if codes:
                for code in codes:
                    fake_line = f"0.25$ — {code}"
                    await handle_new_post(fake_line, msg.media)

            POST_CACHE.setdefault(msg.chat_id, {})[msg.id] = {
                "text": msg.message or "",
                "timestamp": time.time()
            }

            asyncio.create_task(
                track_post_changes(msg.chat_id, msg.id, msg.media, is_special_channel=True)
            )

        except Exception as e:
            print("[POLL error]", e)

        await asyncio.sleep(0.15)