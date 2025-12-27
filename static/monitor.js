const cpuData = [];
const ramData = [];
const labels = [];

const ctx = document.getElementById('chart').getContext('2d');

const chart = new Chart(ctx, {
    type: 'line',
    data: {
        labels,
        datasets: [
            { label: 'CPU %', data: cpuData },
            { label: 'RAM %', data: ramData }
        ]
    }
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

        let h = Math.floor(data.uptime_sec / 3600);
        let m = Math.floor((data.uptime_sec % 3600) / 60);
        let s = data.uptime_sec % 60;
        document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;

        if (labels.length > 60) {
            labels.shift();
            cpuData.shift();
            ramData.shift();
        }

        labels.push("");
        cpuData.push(data.cpu);
        ramData.push(data.ram_percent);

        chart.update();

    } catch (e) {}
}

setInterval(updateMetrics, 2000);
updateMetrics();