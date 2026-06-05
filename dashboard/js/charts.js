let chart = null;

export function renderVolumeChart(entries) {
    const canvas = document.getElementById('volume-chart');
    if (!canvas) return;

    // Group by day and chat_id
    const byDay = {};
    const groups = new Set();
    for (const e of entries) {
        if (!e.datetime) continue;
        const day = e.datetime.slice(0, 10);
        const g = e.chat_id;
        groups.add(g);
        if (!byDay[day]) byDay[day] = {};
        byDay[day][g] = (byDay[day][g] || 0) + 1;
    }

    const labels = Object.keys(byDay).sort();
    const colors = [
        '#1a73e8', '#ea4335', '#34a853', '#fbbc04', '#9c27b0',
        '#00bcd4', '#ff5722', '#607d8b', '#e91e63', '#3f51b5',
    ];
    const datasets = Array.from(groups).map((g, i) => ({
        label: g,
        data: labels.map(d => byDay[d][g] || 0),
        backgroundColor: colors[i % colors.length],
    }));

    if (chart) chart.destroy();
    chart = new Chart(canvas, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
                x: { stacked: true },
                y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1 } },
            },
        },
    });
}

export function destroyVolumeChart() {
    if (chart) { chart.destroy(); chart = null; }
}
