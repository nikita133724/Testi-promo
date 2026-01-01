from telethon import TelegramClient, events
from telethon.tl.types import MessageEntitySpoiler, MessageEntityCode, MessageEntityPre, MessageEntityCustomEmoji
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post
import asyncio
import time
import re

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]
SPECIAL_USERNAME = CHANNEL_SPECIAL.lstrip("@").lower()
POST_CACHE = {}

def extract_special_promos(msg):
    if not msg.entities:
        return []

    full_text = msg.raw_text or msg.message or ""
    results = []

    for ent in msg.entities:
        if isinstance(ent, (MessageEntityCode, MessageEntitySpoiler, MessageEntityPre)):
            start = ent.offset
            end = ent.offset + ent.length

            while start > 0:
                prev_char = full_text[start - 1]
                if re.match(r"[A-Za-zА-Яа-я0-9]", prev_char):
                    start -= 1
                elif any(isinstance(ce, MessageEntityCustomEmoji) and ce.offset <= start - 1 < ce.offset + ce.length for ce in msg.entities):
                    start -= 1
                else:
                    break

            entity_text = full_text[start:end].strip()

            match = re.search(r"([A-Za-zА-Яа-я0-9]{4,32})", entity_text)
            if match:
                results.append(match.group(1))

    return results

@client.on(events.NewMessage(chats=channels))
async def all_channels_handler(event):
    msg = event.message
    chat_id = event.chat_id
    chat = await event.get_chat()
    chat_username = (getattr(chat, "username", None) or "").lower()
    is_special_channel = chat_username == SPECIAL_USERNAME
    text = msg.message or ""
    media = msg.media

    if text:
        if is_special_channel:
            # 🔔 уведомление о новом посте
            await client.send_message("@saxarok322", f"Вышел пост от @{SPECIAL_USERNAME}")

            # 🔽 обработка промо
            codes = extract_special_promos(msg)
            if codes:
                for code in codes:
                    fake_line = f"0.5$ — {code}"
                    await handle_new_post(fake_line, media)
            else:
                print("[SPECIAL] В посте нет промокодов")
        else:
            await handle_new_post(text, media)

    POST_CACHE.setdefault(chat_id, {})[msg.id] = {
        "text": text,
        "timestamp": time.time()
    }

    asyncio.create_task(track_post_changes(chat_id, msg.id, media, is_special_channel=is_special_channel))

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

        if is_special_channel:
            codes = extract_special_promos(msg)
            if codes:
                for code in codes:
                    fake_line = f"0.5$ — {code}"
                    await handle_new_post(fake_line, media)
        else:
            await handle_new_post(new_text, media)