from collections import deque
from time import time

BUFFER_SECONDS = 300  # 5 минут
buffer = deque()

def push(metrics):
    now = time()
    buffer.append((now, metrics))

    while buffer and now - buffer[0][0] > BUFFER_SECONDS:
        buffer.popleft()

def get_last():
    return [item[1] for item in buffer]