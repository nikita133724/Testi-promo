const cpuCtx = document.getElementById('cpuChart').getContext('2d');
const ramCtx = document.getElementById('ramChart').getContext('2d');

const cpuData = [];
const ramData = [];
const labels = [];

const cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'CPU %', data: cpuData, borderColor: 'red', fill: false }] },
    options: { 
        animation: { duration: 300 }, // плавное смещение
        responsive: true,
        scales: { x: { display: false } } // убираем лишние метки времени
    }
});

const ramChart = new Chart(ramCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'RAM %', data: ramData, borderColor: 'blue', fill: false }] },
    options: { 
        animation: { duration: 300 },
        responsive: true,
        scales: { x: { display: false } }
    }
});

const ably = new Ably.Realtime(ABLY_PUBLIC_KEY);
const channel = ably.channels.get('system-metrics');
const client_id = Math.random().toString(36).substring(2);

// ----------------------------
// Пинг серверу
function sendPing() {
    channel.publish('ping', { viewing: true, client_id }).catch(console.error);
}

// ----------------------------
// Буфер метрик
let pendingMetrics = [];

// ----------------------------
// Обновление графиков и таблицы
function updateCharts() {
    if (!pendingMetrics.length) return;

    const last = pendingMetrics[pendingMetrics.length - 1];

    // Добавляем новую точку
    labels.push(new Date().toLocaleTimeString());
    cpuData.push(last.cpu);
    ramData.push(last.ram_percent);

    // Удаляем старые, если больше 300
    if (labels.length > 300) {
        labels.shift();
        cpuData.shift();
        ramData.shift();
    }

    // Обновляем графики с анимацией
    cpuChart.update();
    ramChart.update();

    // Таблица
    document.getElementById("cpu").innerText = last.cpu + " %";
    document.getElementById("ram").innerText = `${last.ram_mb} MB (${last.ram_percent}%)`;
    document.getElementById("load").innerText = last.load_avg;
    document.getElementById("threads").innerText = last.threads;

    const h = Math.floor(last.uptime_sec / 3600);
    const m = Math.floor((last.uptime_sec % 3600) / 60);
    const s = last.uptime_sec % 60;
    document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;

    pendingMetrics = [];
}

// ----------------------------
// Подписка на метрики
channel.subscribe('metrics', msg => {
    let d = msg.data;
    if (typeof d === 'string') d = JSON.parse(d);
    pendingMetrics.push(d);
});

// Интервал обновления графиков с плавным скроллом
setInterval(updateCharts, 500); // 0.5 секунды

// ----------------------------
// Инициализация
async function initMonitor() {
    // Загружаем историю
    const history = await fetch('/admin/monitor/history').then(r => r.json());
    history.forEach(p => {
        labels.push(new Date().toLocaleTimeString());
        cpuData.push(p.cpu);
        ramData.push(p.ram_percent);
    });
    cpuChart.update();
    ramChart.update();

    sendPing();
    setInterval(sendPing, 20000);
}

// ----------------------------
// Уходим со страницы
window.addEventListener("beforeunload", () => {
    channel.presence.leave().catch(console.error);
});

initMonitor();