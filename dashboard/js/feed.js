import { esc, tgLink, toTgLink } from './utils.js';

export function renderFeed(container, entries) {
    if (!container) return;
    if (entries.length === 0) {
        container.innerHTML = '<div class="empty">Нет отправок</div>';
        return;
    }

    container.innerHTML = entries.map(e => {
        const time = new Date(e.datetime).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        const ok = e.result && e.result.includes('successfully');
        const statusClass = ok ? 'ok' : 'err';
        const statusIcon = ok ? '✅' : '⚠️';
        const title = e.message_title || e.text || '[—]';
        const link = e.message_link
            ? `<a href="${esc(toTgLink(e.message_link))}" target="_blank">→</a>`
            : '';
        const gLink = tgLink(e.chat_id);

        return `<div class="feed-item">
            <span class="time">${time}</span>
            <span class="group">${gLink ? `<a href="${gLink}" target="_blank">${esc(e.chat_id)}</a>` : esc(e.chat_id)}</span>
            <span class="title">${esc(title)}</span>
            <span class="status ${statusClass}">${statusIcon}</span>
            ${link}
        </div>`;
    }).join('');
}
