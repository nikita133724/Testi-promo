# admin_chats.py
import asyncio

MAX_ACTIVE_CHATS = 10
MAX_MESSAGES_PER_CHAT = 50

# user_id -> {"admin_id": int, "messages": [(from_user, text, media)]}
_active_chats = {}
_lock = asyncio.Lock()

async def create_admin_session(user_id: int, admin_id: int):
    async with _lock:
        if len(_active_chats) >= MAX_ACTIVE_CHATS:
            return False
        if user_id in _active_chats:
            return True
        _active_chats[user_id] = {"admin_id": admin_id, "messages": []}
        return True

async def close_admin_session(user_id: int):
    async with _lock:
        if user_id in _active_chats:
            del _active_chats[user_id]

async def add_message(user_id: int, from_user: int, text: str, media=None):
    async with _lock:
        if user_id not in _active_chats:
            return None
        chat = _active_chats[user_id]
        chat["messages"].append((from_user, text, media))
        chat["messages"] = chat["messages"][-MAX_MESSAGES_PER_CHAT:]
        return chat["admin_id"]

async def get_history(user_id: int):
    async with _lock:
        return _active_chats.get(user_id, {}).get("messages", [])

async def get_active_chats():
    async with _lock:
        return list(_active_chats.keys())