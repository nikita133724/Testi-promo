let cpuData = [];
let ramData = [];
let labels = [];

const maxPoints = 60;

const cpuChart = new Chart(document.getElementById('cpuChart'), {
    type: 'line',
    data: { labels, datasets: [{ label: 'CPU %', data: cpuData }] },
    options: { animation: false, scales: { y: { min: 0, max: 100 } } }
});

const ramChart = new Chart(document.getElementById('ramChart'), {
    type: 'line',
    data: { labels, datasets: [{ label: 'RAM %', data: ramData }] },
    options: { animation: false, scales: { y: { min: 0, max: 100 } } }
});

async function updateMetrics() {
    const res = await fetch('/admin/monitor/data');
    const d = await res.json();

    document.getElementById('cpu').innerText = d.cpu.toFixed(1) + " %";
    document.getElementById('ram').innerText = d.ram_mb.toFixed(0) + " MB (" + d.ram_percent.toFixed(1) + "%)";
    document.getElementById('load').innerText = d.load_avg.toFixed(2);
    document.getElementById('threads').innerText = d.threads;

    const h = Math.floor(d.uptime_sec / 3600);
    const m = Math.floor((d.uptime_sec % 3600) / 60);
    const s = d.uptime_sec % 60;
    document.getElementById('uptime').innerText = `${h}h ${m}m ${s}s`;

    const time = new Date().toLocaleTimeString();

    if (labels.length >= maxPoints) {
        labels.shift();
        cpuData.shift();
        ramData.shift();
    }

    labels.push(time);
    cpuData.push(d.cpu);
    ramData.push(d.ram_percent);

    cpuChart.update();
    ramChart.update();
}

setInterval(updateMetrics, 2000);
updateMetrics();