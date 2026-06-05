export function renderErrors(container, errors) {
    if (!container) return;
    if (errors.length === 0) {
        container.innerHTML = '<div class="empty">Нет ошибок</div>';
        return;
    }

    container.innerHTML = errors.map(e => {
        const title = e.text && e.text.startsWith('http')
            ? `<a href="${esc(e.text)}" target="_blank">${esc(e.text)}</a>`
            : esc(e.text || '[текст]');
        const gLink = tgLink(e.chat_id);
        return `<div class="error-card">
            <div class="group">${gLink ? `<a href="${gLink}" target="_blank">${esc(e.chat_id)}</a>` : esc(e.chat_id)}</div>
            <div class="source">${title}</div>
            <div class="error-msg">${esc(e.error)}</div>
            <div class="meta">Расп: ${esc(e.schedule)} | Акк: ${esc(e.account || '—')}</div>
        </div>`;
    }).join('');
}

function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function tgLink(chatId) {
    if (!chatId) return null;
    if (chatId.startsWith('@')) return `tg://resolve?domain=${chatId.slice(1)}`;
    const id = chatId.replace(/^-100/, '');
    if (/^\d+$/.test(id)) return `tg://private?id=${id}`;
    return null;
}
