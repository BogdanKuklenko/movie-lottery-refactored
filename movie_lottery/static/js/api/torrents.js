// Временный модуль для работы с торрент-клиентом.
// Если серверные эндпоинты недоступны, функции возвращают понятные заглушки.

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

    console.info('[torrent-api] Download request skipped. Title:', title || 'unknown');
    return {
        success: false,
        message: 'Автоматическая загрузка торрентов отключена. Скопируйте magnet-ссылку и добавьте её вручную.',
        magnet_link: magnetLink,
    };
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

    console.info('[torrent-api] Delete request skipped. Hash:', torrentHash);
    return {
        success: false,
        message: 'Удаление торрентов через веб-интерфейс отключено. Управляйте загрузками в клиенте вручную.',
        torrent_hash: torrentHash,
    };
}

/**
 * Возвращает информацию о состоянии подключенного торрент-клиента.
 * @returns {Promise<object>} Объект с информацией о состоянии.
 */
export async function fetchClientStatus() {
    console.info('[torrent-api] Client status request skipped.');
    return {
        success: false,
        message: 'Статус торрент-клиента недоступен. Интеграция отключена.',
        status: 'unknown',
    };
}

/**
 * Получает перечень активных торрентов на клиенте.
 * @returns {Promise<object>} Объект с массивом торрентов.
 */
export async function fetchClientTorrents() {
    console.info('[torrent-api] Torrent list request skipped.');
    return {
        success: false,
        message: 'Список торрентов недоступен. Интеграция отключена.',
        torrents: [],
    };
}
