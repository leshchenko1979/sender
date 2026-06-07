import { query } from './supabase.js';
import { renderVolumeChart, destroyVolumeChart } from './charts.js';
import { renderGroups } from './groups.js';
import { renderErrors } from './errors.js';
import { renderFeed } from './feed.js';
import { esc, tgLink } from './utils.js';

let currentClient = 'pro_gab';

// ── Tab switching ──────────────────────────────────────────────

document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
});

// ── Client switcher ────────────────────────────────────────────

const switcher = document.getElementById('client-switcher');
switcher.addEventListener('change', () => {
    currentClient = switcher.value;
    loadAll();
});

// ── Data loading ───────────────────────────────────────────────

function daysAgo(n) {
    const d = new Date();
    d.setDate(d.getDate() - n);
    return d.toISOString();
}

async function loadAll() {
    await Promise.allSettled([
        loadOverview(),
        loadErrors(),
        loadGroups(),
        loadFeed(),
    ]);
}

async function loadOverview() {
    const since = daysAgo(7);

    const [logEntries, errors, groupStats, feed] = await Promise.all([
        query('log_entries', {
            select: 'chat_id,datetime,result',
            client_name: `eq.${currentClient}`,
            datetime: `gte.${since}`,
        }),
        query('settings_mirror', {
            select: '*',
            client_name: `eq.${currentClient}`,
            active: 'eq.false',
            error: 'neq.',
            order: 'row_index',
        }),
        query('group_stats', {
            select: '*',
            client_name: `eq.${currentClient}`,
            order: 'members.desc',
        }),
        query('log_entries', {
            select: '*',
            client_name: `eq.${currentClient}`,
            order: 'datetime.desc',
            limit: 10,
        }),
    ]);

    // Volume chart
    renderVolumeChart(logEntries);

    // Error count
    document.getElementById('error-count').textContent = errors.length;

    // Error summary
    const errDiv = document.getElementById('error-summary');
    if (errors.length === 0) {
        errDiv.innerHTML = '<div class="empty">Нет ошибок</div>';
    } else {
        errDiv.innerHTML = errors.slice(0, 3).map(e => `
            <div class="error-card">
                <div class="group">${esc(e.chat_id)}</div>
                <div class="error-msg">${esc(e.error)}</div>
            </div>
        `).join('');
    }

    // Groups summary — volume per group this week
    const gsDiv = document.getElementById('groups-summary');
    const volumeByGroup = {};
    for (const e of logEntries) {
        if (!e.chat_id || !e.result?.includes('successfully')) continue;
        volumeByGroup[e.chat_id] = (volumeByGroup[e.chat_id] || 0) + 1;
    }
    const sorted = Object.entries(volumeByGroup).sort((a, b) => b[1] - a[1]);
    if (sorted.length === 0) {
        gsDiv.innerHTML = '<div class="empty">Нет данных</div>';
    } else {
        gsDiv.innerHTML = `<div class="groups-summary-grid">${
            sorted.map(([chatId, count]) => {
                const stat = groupStats.find(g => g.chat_id === chatId);
                const name = stat?.name || chatId;
                const link = tgLink(chatId);
                return `<div class="group-mini">
                    <div class="name">${link ? `<a href="${link}" target="_blank">${esc(name)}</a>` : esc(name)}</div>
                    <div class="stats">${count} постов / 7 дней</div>
                </div>`;
            }).join('')
        }</div>`;
    }

    // Feed preview
    renderFeed(document.getElementById('feed-preview'), feed);
}

async function loadErrors() {
    const errors = await query('settings_mirror', {
        select: '*',
        client_name: `eq.${currentClient}`,
        active: 'eq.false',
        error: 'neq.',
        order: 'row_index',
    });
    renderErrors(document.getElementById('errors-list'), errors);
}

async function loadGroups() {
    const since = daysAgo(7);
    const [groups, dailyStats] = await Promise.all([
        query('group_stats', {
            select: '*',
            client_name: `eq.${currentClient}`,
        }),
        query('group_daily_stats', {
            select: '*',
            client_name: `eq.${currentClient}`,
            date: `gte.${since.slice(0, 10)}`,
        }),
    ]);
    renderGroups(document.getElementById('groups-tbody'), groups, dailyStats);
}

async function loadFeed() {
    const feed = await query('log_entries', {
        select: '*',
        client_name: `eq.${currentClient}`,
        order: 'datetime.desc',
        limit: 50,
    });
    renderFeed(document.getElementById('feed-list'), feed);
}

// ── Init ───────────────────────────────────────────────────────

loadAll();
