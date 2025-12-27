import psutil
import time

START_TIME = time.time()

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
        "cpu": cpu,
        "ram_mb": ram_mb,
        "ram_percent": ram_percent,
        "load_avg": load,
        "threads": threads,
        "uptime_sec": uptime
    }