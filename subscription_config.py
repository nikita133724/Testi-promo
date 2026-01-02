import json
from redis_client import r

KEY = "subscription_prices"

DEFAULT = {
    "basic": 2
}

def load_prices():
    raw = r.get(KEY)
    if not raw:
        r.set(KEY, json.dumps(DEFAULT))
        return DEFAULT
    return json.loads(raw)

def save_prices(prices: dict):
    r.set(KEY, json.dumps(prices))

def get_price(plan="basic"):
    prices = load_prices()
    return int(prices.get(plan, DEFAULT["basic"]))