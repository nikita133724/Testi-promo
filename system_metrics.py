import psutil
import time
from collections import deque

START_TIME = time.time()
CPU_WINDOW = deque(maxlen=5)

def read_value(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except:
        return None

def get_container_memory():
    # cgroup v2 (используется на Render)
    limit = read_value("/sys/fs/cgroup/memory.max")
    usage = read_value("/sys/fs/cgroup/memory.current")

    if limit and usage and limit > 0 and limit < 10**15:
        return usage, limit

    # fallback — если вдруг не контейнер
    vm = psutil.virtual_memory()
    return vm.used, vm.total

def get_metrics():
    cpu = psutil.cpu_percent(interval=0.2)
    CPU_WINDOW.append(cpu)
    cpu_smooth = round(sum(CPU_WINDOW) / len(CPU_WINDOW), 1)
    
    used, total = get_container_memory()
    ram_mb = round(used / 1024 / 1024, 1)
    ram_percent = round((used / total) * 100, 1)

    try:
        load = round(psutil.getloadavg()[0], 2)
    except:
        load = 0

    threads = psutil.Process().num_threads()
    uptime = int(time.time() - START_TIME)

    return {
        "cpu": cpu_smooth,
        "ram_mb": ram_mb,
        "ram_percent": ram_percent,
        "load_avg": load,
        "threads": threads,
        "uptime_sec": uptime
    }