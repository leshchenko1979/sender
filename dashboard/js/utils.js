// Shared dashboard helpers.

// HTML-escape user-supplied strings before interpolating into innerHTML.
export function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// Format a number with Russian locale separators.
export function fmt(n) {
    if (n == null) return '—';
    return n.toLocaleString('ru-RU');
}

// Build a tg:// link from a chat_id (channel/group id or @username).
export function tgLink(chatId) {
    if (!chatId) return null;
    if (chatId.startsWith('@')) return `tg://resolve?domain=${chatId.slice(1)}`;
    const id = chatId.replace(/^-100/, '');
    if (/^\d+$/.test(id)) return `tg://private?id=${id}`;
    return null;
}

// Convert an https://t.me/... URL to its tg:// equivalent.
// Pass-through for non-t.me URLs and invite links (no tg:// form).
export function toTgLink(url) {
    if (!url) return url;
    const m = url.match(/^https?:\/\/t\.me\/(.+)$/);
    if (!m) return url;
    const rest = m[1];

    // /c/<id>/<post> — private supergroup
    const c = rest.match(/^c\/(-?\d+)(?:\/(\d+))?$/);
    if (c) {
        const id = c[1].replace(/^-100/, '');
        return c[2]
            ? `tg://private?id=${id}&post=${c[2]}`
            : `tg://private?id=${id}`;
    }

    // /+<hash> — invite link, no tg:// equivalent
    if (rest.startsWith('+')) return url;

    // /<username>[/<post>]
    const u = rest.match(/^([^/]+)(?:\/(\d+))?$/);
    if (u) {
        return u[2]
            ? `tg://resolve?domain=${u[1]}&post=${u[2]}`
            : `tg://resolve?domain=${u[1]}`;
    }

    return url;
}
