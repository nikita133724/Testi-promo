import json
from datetime import datetime, timezone
from redis_client import r

ORDERS_KEY = "GLOBAL_ORDERS"
COUNTER_KEY = "GLOBAL_ORDER_COUNTER"

ORDERS = {}


def load_orders():
    global ORDERS
    raw = r.hgetall(ORDERS_KEY)
    for k, v in raw.items():
        ORDERS[int(k)] = json.loads(v)


def save_order(order_id, data):
    ORDERS[order_id] = data
    r.hset(ORDERS_KEY, order_id, json.dumps(data))


def next_order_id():
    new_id = r.incr(COUNTER_KEY)
    return int(new_id)


def get_user_orders(chat_id):
    return [(oid, o) for oid, o in ORDERS.items() if o["chat_id"] == chat_id]


def get_order(order_id):
    return ORDERS.get(order_id)
    
def get_last_orders(chat_id, count=4):
    orders = [(oid, o) for oid, o in ORDERS.items() if o["chat_id"] == chat_id]
    orders.sort(key=lambda x: x[1]["created_at"], reverse=True)
    return orders[:count]