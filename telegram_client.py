from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL, ADMIN_USER_ID
from promo_processor import handle_new_post

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]

@client.on(events.NewMessage(chats=channels))
async def new_message_handler(event):
    message_text = event.message.message or ""
    media = event.message.media

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

    # Логирование
    print("=== Новый пост ===")
    print(f"Канал/Чат: {event.chat_id}")
    if message_text and media_info:
        print(f"Текст с медиа ({media_info}): {message_text}")
    elif message_text:
        print(f"Только текст: {message_text}")
    elif media_info:
        print(f"Только медиа: {media_info}")
    else:
        print("Пустое сообщение")
    print("----")

    if message_text:
        # ChatID больше не передается
        await handle_new_post(message_text, media)
        



# ------------------ Сессии "секретных чатов" ------------------
# user_id -> {"admin_id": int, "messages": list of (from_user, text, media)}
active_chats = {}
MAX_ACTIVE_CHATS = 10
MAX_MESSAGES_PER_CHAT = 50  # ограничение на количество сообщений в памяти

async def create_admin_session(user_id: int, admin_id: int):
    if len(active_chats) >= MAX_ACTIVE_CHATS:
        return False
    if user_id in active_chats:
        return True
    active_chats[user_id] = {"admin_id": admin_id, "messages": []}
    return True

async def close_admin_session(user_id: int):
    if user_id in active_chats:
        del active_chats[user_id]

# ------------------ Универсальный обработчик сообщений ------------------
@client.on(events.NewMessage)
async def global_message_handler(event):
    sender = await event.get_sender()
    user_id = sender.id
    message_text = event.message.message or ""
    media = event.message.media

    # -------------------- Медиа инфо --------------------
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

    # -------------------- Админ-сессия --------------------
    if user_id in active_chats:
        chat = active_chats[user_id]
        # Сохраняем сообщение с лимитом по MAX_MESSAGES_PER_CHAT
        chat["messages"].append((user_id, message_text, media))
        chat["messages"] = chat["messages"][-MAX_MESSAGES_PER_CHAT:]

        admin_id = chat["admin_id"]
        # Пересылаем только текст и медиа
        await client.send_message(admin_id, f"Сообщение от {user_id}: {message_text}", file=media if media else None)
        return  # не продолжаем обработку как обычный пост

    # -------------------- Сообщения из каналов --------------------
    if event.chat_id in channels:
        if message_text or media:
            await handle_new_post(message_text, media)

# ------------------ Команды пользователя ------------------
@client.on(events.NewMessage(pattern='/admin_chat'))
async def admin_chat_command(event):
    user_id = event.sender_id
    success = await create_admin_session(user_id, ADMIN_USER_ID)
    if success:
        await event.respond(
            "✅ Административная сессия открыта! "
            "Теперь вы можете писать сообщения, и администратор их увидит."
        )
    else:
        await event.respond("⚠️ Не могу открыть сессию. Достигнуто максимальное количество активных чатов.")

# ------------------ Команды администратора ------------------
@client.on(events.NewMessage(from_users=ADMIN_USER_ID, pattern='/reply (\d+) (.+)'))
async def admin_reply(event):
    """Команда: /reply <user_id> <текст>"""
    user_id = int(event.pattern_match.group(1))
    text = event.pattern_match.group(2)

    if user_id not in active_chats:
        await event.respond("⚠️ Сессия с этим пользователем не найдена.")
        return

    chat = active_chats[user_id]
    chat["messages"].append((ADMIN_USER_ID, text, None))
    chat["messages"] = chat["messages"][-MAX_MESSAGES_PER_CHAT:]

    await client.send_message(user_id, f"Администратор: {text}")
    await event.respond(f"✅ Ответ отправлен пользователю {user_id}")

@client.on(events.NewMessage(from_users=ADMIN_USER_ID, pattern='/close_chat (\d+)'))
async def admin_close_chat(event):
    user_id = int(event.pattern_match.group(1))
    if user_id not in active_chats:
        await event.respond("⚠️ Сессия с этим пользователем не найдена.")
        return
    await close_admin_session(user_id)
    await event.respond(f"✅ Сессия с пользователем {user_id} закрыта.")

@client.on(events.NewMessage(from_users=ADMIN_USER_ID, pattern='/history (\d+)'))
async def admin_history(event):
    user_id = int(event.pattern_match.group(1))
    if user_id not in active_chats:
        await event.respond("⚠️ Сессия с этим пользователем не найдена.")
        return

    chat = active_chats[user_id]
    history_texts = []
    for msg_user, text, media in chat["messages"][-MAX_MESSAGES_PER_CHAT:]:
        sender = "Администратор" if msg_user == ADMIN_USER_ID else f"Пользователь {msg_user}"
        if text:
            history_texts.append(f"{sender}: {text}")
        if media:
            history_texts.append(f"{sender} отправил медиа: {type(media).__name__}")

    if history_texts:
        await event.respond("\n".join(history_texts))
    else:
        await event.respond("История сообщений пуста.")