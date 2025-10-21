// Временный модуль для работы с торрент-клиентом.
// Если серверные эндпоинты недоступны, функции возвращают понятные заглушки.

const TORRENT_API_BASE = '/api/torrents';
const DEFAULT_HEADERS = { 'Content-Type': 'application/json' };

function isApiEnabled() {
    if (typeof window !== 'undefined' && typeof window.__TORRENT_API_ENABLED__ === 'boolean') {
        return window.__TORRENT_API_ENABLED__;
    }
    return false;
}

async function safeRequest(url, options, fallbackMessage, extra = {}) {
    if (!isApiEnabled()) {
        return { success: false, message: fallbackMessage, ...extra };
    }

    try {
        const response = await fetch(url, options);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const message = data.message || fallbackMessage;
            return { success: false, message, ...extra, ...data };
        }
        return data;
    } catch (error) {
        console.warn('Torrent API request failed:', error);
        return { success: false, message: fallbackMessage, ...extra };
    }
}

/**
 * Пытается загрузить торрент на клиент по magnet-ссылке.
 * @param {object} params
 * @param {string} params.magnetLink - Magnet-ссылка, которую нужно отправить в торрент-клиент.
 * @param {string} [params.title] - Имя фильма (используется для логов на сервере).
 * @returns {Promise<object>} Результат выполнения операции.
 */
export async function downloadTorrentToClient({ magnetLink, title } = {}) {
    if (!magnetLink) {
        return { success: false, message: 'Magnet-ссылка отсутствует. Добавьте её вручную в ваш торрент-клиент.' };
    }

    const fallbackMessage = 'Автоматическая загрузка торрентов временно недоступна. Скопируйте magnet-ссылку вручную.';
    return safeRequest(`${TORRENT_API_BASE}/download`, {
        method: 'POST',
        headers: DEFAULT_HEADERS,
        body: JSON.stringify({ magnet_link: magnetLink, title }),
    }, fallbackMessage, { magnet_link: magnetLink });
}

/**
 * Удаляет торрент с клиента по хешу.
 * @param {string} torrentHash - Хеш торрента.
 * @returns {Promise<object>} Результат удаления.
 */
export async function deleteTorrentFromClient(torrentHash) {
    if (!torrentHash) {
        return { success: false, message: 'Не удалось определить торрент для удаления.' };
    }

    const fallbackMessage = 'Удаление торрентов через веб-интерфейс временно отключено.';
    return safeRequest(`${TORRENT_API_BASE}/${encodeURIComponent(torrentHash)}`, {
        method: 'DELETE',
        headers: DEFAULT_HEADERS,
    }, fallbackMessage, { torrent_hash: torrentHash });
}

/**
 * Возвращает информацию о состоянии подключенного торрент-клиента.
 * @returns {Promise<object>} Объект с информацией о состоянии.
 */
export async function fetchClientStatus() {
    const fallbackMessage = 'Статус торрент-клиента недоступен.';
    return safeRequest(`${TORRENT_API_BASE}/status`, {
        method: 'GET',
        headers: DEFAULT_HEADERS,
    }, fallbackMessage, { status: 'unknown' });
}

/**
 * Получает перечень активных торрентов на клиенте.
 * @returns {Promise<object>} Объект с массивом торрентов.
 */
export async function fetchClientTorrents() {
    const fallbackMessage = 'Список торрентов недоступен.';
    return safeRequest(`${TORRENT_API_BASE}/list`, {
        method: 'GET',
        headers: DEFAULT_HEADERS,
    }, fallbackMessage, { torrents: [] });
}
