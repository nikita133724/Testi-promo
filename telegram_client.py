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

            # Игнорируем все CustomEmoji сразу перед entity
            while start > 0:
                for ce in msg.entities:
                    if isinstance(ce, MessageEntityCustomEmoji) and ce.offset + ce.length == start:
                        start -= ce.length
                        break
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
# Polling для спец-канала (без отправки в Избранное)
# -----------------------------
# -----------------------------
def debug_message(msg):
    """Печатаем, как Telethon видит сообщение полностью"""
    print("=== DEBUG MESSAGE START ===")
    print("msg.id:", msg.id)
    print("msg.chat_id:", msg.chat_id)
    print("msg.date:", msg.date)
    print("msg.message (repr):", repr(msg.message))
    print("msg.raw_text (repr):", repr(msg.raw_text))

    print("\n--- Entities ---")
    if msg.entities:
        for ent in msg.entities:
            # Текст, который entity покрывает (без ошибок, если текст None)
            full_text = msg.message or msg.raw_text or ""
            text = full_text[ent.offset:ent.offset+ent.length] if full_text else ""
            print(f"{type(ent).__name__}: offset={ent.offset}, length={ent.length}, text={repr(text)}")
    else:
        print("No entities found")

    print("\n--- Full msg object ---")
    # Полностью словарь для всех атрибутов
    try:
        import json
        print(json.dumps(msg.to_dict(), indent=2, default=str))
    except Exception as e:
        print("msg.to_dict() error:", e)

    print("=== DEBUG MESSAGE END ===\n")

async def poll_special_channel():
    print("[POLL] Запущен polling спец-канала")
    TARGET_POST_ID = 9472  # пример ID

    while not client.is_connected():
        await asyncio.sleep(0.5)

    await asyncio.sleep(60)  # задержка 1 минута для теста

    try:
        msg = await client.get_messages(CHANNEL_SPECIAL, ids=TARGET_POST_ID)
        if not msg:
            print(f"[POLL] Пост с ID={TARGET_POST_ID} не найден")
            return

        # --- DEBUG ---
        debug_message(msg)

        # Обработка промо
        codes = extract_special_promos(msg)
        if codes:
            for code in codes:
                fake_line = f"0.25$ — {code}"
                await handle_new_post(fake_line, msg.media)
        else:
            print("[POLL] В посте нет промокодов")

        POST_CACHE.setdefault(msg.chat_id, {})[msg.id] = {
            "text": msg.message or "",
            "timestamp": time.time()
        }
        asyncio.create_task(track_post_changes(msg.chat_id, msg.id, msg.media, is_special_channel=True))

    except Exception as e:
        print(f"[POLL] Ошибка при получении поста ID={TARGET_POST_ID}: {e}")