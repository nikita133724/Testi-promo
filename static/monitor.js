const ably = new Ably.Realtime(ABLY_PUBLIC_KEY);
const channel = ably.channels.get('system-metrics');

const cpuCtx = document.getElementById('cpuChart').getContext('2d');
const ramCtx = document.getElementById('ramChart').getContext('2d');

let cpuData = [], ramData = [], labels = [];

const cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'CPU %', data: cpuData, borderColor: 'red', fill: false }] },
    options: { animation: { duration: 300 }, responsive: true, scales: { x: { display: false } } }
});

const ramChart = new Chart(ramCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'RAM %', data: ramData, borderColor: 'blue', fill: false }] },
    options: { animation: { duration: 300 }, responsive: true, scales: { x: { display: false } } }
});

// ----------------------------
// Входим в Presence при открытии страницы
channel.presence.enter({ viewing: true }).catch(console.error);

// Выходим из Presence при уходе
window.addEventListener("beforeunload", () => {
    channel.presence.leave().catch(console.error);
});

// ----------------------------
// Обновление графиков и таблицы
function updateCharts(d) {
    labels.push(new Date().toLocaleTimeString());
    cpuData.push(d.cpu);
    ramData.push(d.ram_percent);

    if (labels.length > 300) {
        labels.shift();
        cpuData.shift();
        ramData.shift();
    }

    cpuChart.update();
    ramChart.update();

    document.getElementById("cpu").innerText = d.cpu + " %";
    document.getElementById("ram").innerText = `${d.ram_mb} MB (${d.ram_percent}%)`;
    document.getElementById("load").innerText = d.load_avg;
    document.getElementById("threads").innerText = d.threads;

    const h = Math.floor(d.uptime_sec / 3600);
    const m = Math.floor((d.uptime_sec % 3600) / 60);
    const s = d.uptime_sec % 60;
    document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;
}

// ----------------------------
// Подписка на метрики
channel.subscribe('metrics', msg => {
    let d = msg.data;
    if (typeof d === 'string') d = JSON.parse(d);
    updateCharts(d);
});

// ----------------------------
// Загрузка истории метрик
async function initMonitor() {
    const history = await fetch('/admin/monitor/history').then(r => r.json());
    history.forEach(p => updateCharts(p));
}

initMonitor();