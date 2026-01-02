from redis_client import r

KEY = "subscription_prices"

def get_price(tariff="basic"):
    value = r.hget(KEY, tariff)
    if not value:
        return 2  # цена по умолчанию
    return int(value)

def save_prices(data: dict):
    for k, v in data.items():
        r.hset(KEY, k, int(v))