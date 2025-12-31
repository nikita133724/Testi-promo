from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageEntitySpoiler, MessageEntityCode, MessageEntityPre
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post
import asyncio
import time
client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]


POST_CACHE = {}

def extract_special_promos(message):
    if not message.entities:
        print("[DEBUG] Нет entities в сообщении")
        return []

    results = []
    full_text = message.message or ""
    print(f"[DEBUG] Всего entities: {len(message.entities)}")

    for i, ent in enumerate(message.entities, start=1):
        print(f"[DEBUG] Entity {i}: {type(ent).__name__}, offset={ent.offset}, length={ent.length}")

        if isinstance(ent, (MessageEntitySpoiler, MessageEntityCode, MessageEntityPre)):
            start = ent.offset
            end = ent.offset + ent.length
            code = full_text[start:end].strip()
            print(f"[DEBUG] Извлечённый код: '{code}'")

            # фильтр мусора
            if 4 <= len(code) <= 32:
                results.append(code)
            else:
                print(f"[DEBUG] Код '{code}' отфильтрован (длина {len(code)})")

    print(f"[DEBUG] Всего найдено промо: {len(results)}")
    return results
    
@client.on(events.NewMessage(chats=channels))
async def new_message_handler(event):
    message = event.message
    message_id = message.id
    chat_id = event.chat_id
    message_text = message.message or ""
    media = message.media

    # --- логирование и обработка медиа как раньше ---
    media_info = None
    if media:
        if isinstance(media, MessageMediaPhoto):
            media_info = "Фото"
        elif isinstance(media, MessageMediaDocument):
            mime = getattr(media.document, 'mime_type', '')
            if mime.startswith("image/webp"):
                media_info = "Стикер"
            elif mime.startswith("video/"):
                media_info = "Видео"
            else:
                media_info = f"Файл ({mime})"
        else:
            media_info = "Другое медиа"

    print("=== Новый пост ===")
    print(f"Канал/Чат: {chat_id}")
    if message_text and media_info:
        print(f"Текст с медиа ({media_info}): {message_text}")
    elif message_text:
        print(f"Только текст: {message_text}")
    elif media_info:
        print(f"Только медиа: {media_info}")
    else:
        print("Пустое сообщение")
    print("----")

    # --- Отправляем в promo_processor ---
    if message_text:
        if chat_id == CHANNEL_SPECIAL:
            codes = extract_special_promos(message)
    
            if codes:
                for code in codes:
                    fake_line = f"0.25$ — {code}"
                    print(f"[SPECIAL] Найден промо: {code}")
                    await handle_new_post(fake_line, media)
            else:
                print("[SPECIAL] В посте нет промокодов")
    
        else:
            await handle_new_post(message_text, media)
    # --- Сохраняем пост в кэш для отслеживания изменений ---
    POST_CACHE.setdefault(chat_id, {})[message_id] = {
        "text": message_text,
        "timestamp": time.time()
    }

    # --- Запускаем фоновую проверку изменений ---
    asyncio.create_task(track_post_changes(chat_id, message_id, media))
    
async def track_post_changes(chat_id, message_id, media=None):
    print(f"[track_post_changes] Старт отслеживания поста {message_id} в чате {chat_id}")

    CHECK_INTERVAL = 4
    TIMEOUT = 5 * 60

    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            message = await client.get_messages(chat_id, ids=message_id)
            if not message:
                continue
            new_text = message.message or ""
        except Exception as e:
            print(f"[track_post_changes] Ошибка при получении сообщения: {e}")
            continue

        old_text = POST_CACHE.get(chat_id, {}).get(message_id, {}).get("text")
        if old_text is None:
            continue

        if new_text != old_text:
            print(f"[UPDATE] Пост {message_id} изменён! Отправляем заново.")
            POST_CACHE[chat_id][message_id]["text"] = new_text
        
            if chat_id == CHANNEL_SPECIAL:
                codes = extract_special_promos(message)
                if codes:
                    for code in codes:
                        fake_line = f"0.25$ — {code}"
                        print(f"[SPECIAL UPDATE] Найден промо: {code}")
                        await handle_new_post(fake_line, media)
            else:
                await handle_new_post(new_text, media)