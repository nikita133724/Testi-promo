const cpuCtx = document.getElementById('cpuChart').getContext('2d');
const ramCtx = document.getElementById('ramChart').getContext('2d');

const cpuData = [];
const ramData = [];
const labels = [];

const cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'CPU %', data: cpuData }] },
    options: { animation: false }
});

const ramChart = new Chart(ramCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'RAM %', data: ramData }] },
    options: { animation: false }
});

async function updateMetrics() {
    try {
        const res = await fetch('/admin/monitor/data');
        const data = await res.json();

        if (!data || data.cpu === undefined) return;

        document.getElementById("cpu").innerText = data.cpu + " %";
        document.getElementById("ram").innerText = data.ram_mb + " MB (" + data.ram_percent + "%)";
        document.getElementById("load").innerText = data.load_avg;
        document.getElementById("threads").innerText = data.threads;

        const h = Math.floor(data.uptime_sec / 3600);
        const m = Math.floor((data.uptime_sec % 3600) / 60);
        const s = data.uptime_sec % 60;
        document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;

        if (labels.length > 60) {
            labels.shift();
            cpuData.shift();
            ramData.shift();
        }

        labels.push('');
        cpuData.push(data.cpu);
        ramData.push(data.ram_percent);

        cpuChart.update();
        ramChart.update();

    } catch (e) {
        console.error(e);
    }
}

setInterval(updateMetrics, 800);
updateMetrics();