import { esc, tgLink } from './utils.js';

export function renderGroups(tbody, groups, dailyStats) {
    if (!tbody) return;
    dailyStats = dailyStats || [];

    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const weekAgo = new Date(now);
    weekAgo.setDate(weekAgo.getDate() - 7);

    // Aggregate daily stats per group
    const statsMap = {};
    for (const g of groups) statsMap[g.chat_id] = g;

    const volume = {};
    for (const row of dailyStats) {
        const g = row.chat_id;
        if (!volume[g]) volume[g] = { today: 0, week: 0, days: 0 };
        volume[g].week += row.post_count || 0;
        volume[g].days++;
        if (row.date === today) volume[g].today = row.post_count || 0;
    }

    const allGroups = Object.keys(statsMap).sort(
        (a, b) => (volume[b]?.week || 0) - (volume[a]?.week || 0)
    );

    if (allGroups.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty">Нет данных о группах</td></tr>';
        return;
    }

    tbody.innerHTML = allGroups.map(chatId => {
        const v = volume[chatId] || { today: 0, week: 0, days: 0 };
        const stat = statsMap[chatId];
        const name = stat?.name || chatId;
        const online = stat?.online;
        const avg = v.days > 0 ? (v.week / v.days).toFixed(0) : '—';
        const link = tgLink(chatId);
        return `<tr>
            <td>${link ? `<a href="${link}" target="_blank">${esc(name)}</a>` : esc(name)}</td>
            <td>${online ?? '—'}</td>
            <td>${v.today}</td>
            <td>${v.week}</td>
            <td>${avg}</td>
        </tr>`;
    }).join('');
}
