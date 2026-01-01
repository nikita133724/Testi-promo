from telethon import TelegramClient, events
from telethon.tl.types import MessageEntitySpoiler, MessageEntityCode, MessageEntityPre
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post
import asyncio
import time

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY]
SPECIAL_USERNAME = CHANNEL_SPECIAL.lstrip("@").lower()
POST_CACHE = {}

# -----------------------------
def extract_special_promos(message):
    """Достаем промо-коды из сообщения"""
    if not message.entities:
        return []
    results = []
    full_text = message.raw_text or message.message or ""
    for ent in message.entities:
        if isinstance(ent, (MessageEntitySpoiler, MessageEntityCode, MessageEntityPre)):
            code = full_text[ent.offset:ent.offset + ent.length].strip()
            if 4 <= len(code) <= 32:
                results.append(code)
    return results

# -----------------------------
# Обычные каналы через events
@client.on(events.NewMessage(chats=channels))
async def ordinary_handler(event):
    msg = event.message
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

        if is_special_channel and new_text:
            try:
                await client.send_message("me", f"[POLLING UPDATE] {new_text}")
            except Exception as e:
                print(f"Ошибка отправки обновленного поста в избранное: {e}")

        # Обработка промо
        codes = extract_special_promos(msg)
        if codes:
            for code in codes:
                fake_line = f"0.25$ — {code}"
                await handle_new_post(fake_line, media)
        elif not is_special_channel:
            await handle_new_post(new_text, media)

# -----------------------------
# Polling для спец-канала
async def poll_special_channel():
    print("[POLL] Запущен polling спец-канала")
    last_id = 0

    while not client.is_connected():
        await asyncio.sleep(0.5)

    while True:
        try:
            messages = await client.get_messages(CHANNEL_SPECIAL, limit=1)
            if messages:
                msg = messages[0]
                if msg.id != last_id:
                    last_id = msg.id
                    print("[POLL] Новый пост в спец-канале")

                    # Тест: пишем в Избранное
                    if msg.message:
                        try:
                            await client.send_message("me", f"[POLLING] {msg.message}")
                        except Exception as e:
                            print(f"Ошибка отправки в избранное: {e}")

                    # Обработка промо
                    codes = extract_special_promos(msg)
                    if codes:
                        for code in codes:
                            fake_line = f"0.25$ — {code}"
                            await handle_new_post(fake_line, msg.media)

                    # Кэширование и отслеживание изменений
                    POST_CACHE.setdefault(msg.chat_id, {})[msg.id] = {
                        "text": msg.message or "",
                        "timestamp": time.time()
                    }
                    asyncio.create_task(track_post_changes(msg.chat_id, msg.id, msg.media, is_special_channel=True))
        except Exception as e:
            print(f"[POLL] Ошибка: {e}")

        await asyncio.sleep(0.3)

#