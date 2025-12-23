import asyncio
import random
from datetime import datetime
from refresh_tokens import warmup_promo  # твой прогрев
from access_control import generate_key

USERS_PER_PAGE = 5

# ----------------------
# Получение списка пользователей с пагинацией
# ----------------------
def get_all_users(ram_data, page=0):
    chat_ids = list(ram_data.keys())
    total_pages = (len(chat_ids) - 1) // USERS_PER_PAGE + 1

    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    page_chat_ids = chat_ids[start:end]

    users = []
    for uid in page_chat_ids:
        user_data = ram_data.get(uid, {})
        users.append({
            "chat_id": uid,
            "access_token": user_data.get("access_token"),
            "refresh_token": user_data.get("refresh_token"),
            "next_refresh": user_data.get("next_refresh_time"),
            "suspended": user_data.get("suspended", False)
        })
    return users, total_pages

# ----------------------
# Информация о пользователе
# ----------------------
def get_user_info(ram_data, uid):
    user_data = ram_data.get(uid, {})
    return {
        "chat_id": uid,
        "access_token": user_data.get("access_token", "не задан"),
        "refresh_token": user_data.get("refresh_token", "не задан"),
        "next_refresh": user_data.get("next_refresh_time", "не задано"),
        "suspended": user_data.get("suspended", False)
    }

# ----------------------
# Приостановка/восстановление пользователя
# ----------------------
def pause_user(ram_data, uid, save_to_redis):
    user_data = ram_data.get(uid)
    if not user_data:
        return False

    user_data["suspended"] = not user_data.get("suspended", False)
    save_to_redis(uid, {"suspended": user_data["suspended"]})
    return user_data["suspended"]

# ----------------------
# Обновление токенов пользователя
# ----------------------
def refresh_user_token(uid, ram_data, refresh_func):
    """refresh_func – это функция refresh_by_refresh_token(chat_id)"""
    return refresh_func(uid)

# ----------------------
# Прогрев пользователя
# ----------------------
async def warmup_user(uid, ram_data):
    user_data = ram_data.get(uid)
    if not user_data:
        return False
    access_token = user_data.get("access_token")
    if not access_token:
        return False
    await warmup_promo(access_token, chat_id=uid)
    return True

# ----------------------
# Ключи
# ----------------------
def get_all_keys():
    # Возвращаем список ключей, можно хранить в отдельном файле или БД
    from access_control import KEYS_STORAGE
    return KEYS_STORAGE

def create_key(duration):
    return generate_key(duration)
