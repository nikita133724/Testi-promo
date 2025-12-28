import psutil
import time
from collections import deque

psutil.cpu_percent(None)   # инициализация

START_TIME = time.time()
CPU_WINDOW = deque(maxlen=5)

_last_heavy = 0
_cached_load = 0
_cached_threads = 0

def read_value(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except:
        return None

def get_container_memory():
    limit = read_value("/sys/fs/cgroup/memory.max")
    usage = read_value("/sys/fs/cgroup/memory.current")

    if limit and usage and limit > 0 and limit < 10**15:
        return usage, limit

    vm = psutil.virtual_memory()
    return vm.used, vm.total

def get_metrics():
    global _last_heavy, _cached_load, _cached_threads

    cpu = psutil.cpu_percent(None)
    CPU_WINDOW.append(cpu)
    cpu_smooth = round(sum(CPU_WINDOW) / len(CPU_WINDOW), 1)

    used, total = get_container_memory()
    ram_mb = round(used / 1024 / 1024, 1)
    ram_percent = round((used / total) * 100, 1)

    now = time.time()
    if now - _last_heavy > 5:
        try:
            _cached_load = round(psutil.getloadavg()[0], 2)
        except:
            _cached_load = 0

        _cached_threads = psutil.Process().num_threads()
        _last_heavy = now

    uptime = int(time.time() - START_TIME)

    return {
        "cpu": cpu_smooth,
        "ram_mb": ram_mb,
        "ram_percent": ram_percent,
        "load_avg": _cached_load,
        "threads": _cached_threads,
        "uptime_sec": uptime
    }