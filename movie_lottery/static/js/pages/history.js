// F:\GPT\movie-lottery V2\movie_lottery\static\js\pages\history.js

import { ModalManager } from '../components/modal.js';
import * as movieApi from '../api/movies.js';
import { downloadTorrentToClient, deleteTorrentFromClient } from '../api/torrents.js';

function formatDate(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleDateString('ru-RU');
}

/**
 * Динамически переключает иконку "копировать"/"искать" на карточке.
 * @param {HTMLElement} card - Элемент карточки.
 * @param {boolean} hasMagnet - Есть ли magnet-ссылка.
 */
function toggleDownloadIcon(card, hasMagnet) {
    const actionButtons = card.querySelector('.action-buttons');
    if (!actionButtons) return;

    // Удаляем обе кнопки, чтобы избежать дублирования
    const copyButton = actionButtons.querySelector('.copy-magnet-button');
    const searchButton = actionButtons.querySelector('.search-rutracker-button');
    if (copyButton) copyButton.remove();
    if (searchButton) searchButton.remove();

    // Создаем нужную кнопку и вставляем ее на первое место
    const newButton = document.createElement('button');
    newButton.type = 'button';
    
    if (hasMagnet) {
        newButton.className = 'icon-button copy-magnet-button';
        newButton.title = 'Скопировать magnet-ссылку';
        newButton.setAttribute('aria-label', 'Скопировать magnet-ссылку');
        newButton.innerHTML = `<svg class="icon-svg icon-copy" viewBox="0 0 24 24"><use href="#icon-copy"></use></svg>`;
    } else {
        newButton.className = 'icon-button search-rutracker-button';
        newButton.title = 'Найти на RuTracker';
        newButton.setAttribute('aria-label', 'Найти на RuTracker');
        newButton.innerHTML = `<svg class="icon-svg icon-search" viewBox="0 0 24 24"><use href="#icon-search"></use></svg>`;
    }
    
    actionButtons.prepend(newButton);
}


document.addEventListener('DOMContentLoaded', () => {
    const gallery = document.querySelector('.history-gallery');
    const modalElement = document.getElementById('history-modal');

    if (!gallery || !modalElement) return;

    const modal = new ModalManager(modalElement);

    const notify = (message, type = 'info') => {
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            const logger = type === 'error' ? console.error : console.log;
            logger(message);
        }
    };

    const handleOpenModal = async (lotteryId) => {
        const card = document.querySelector(`.gallery-item[data-lottery-id="${lotteryId}"]`);
        modalElement.dataset.activeLotteryId = lotteryId;
        modal.open();
        try {
            const lotteryData = await movieApi.fetchLotteryDetails(lotteryId);
            if (lotteryData.result) {
                if (card) {
                    lotteryData.result.is_on_client = card.classList.contains('has-torrent-on-client');
                    lotteryData.result.torrent_hash = card.dataset.torrentHash || '';
                }

                const actions = {
                    onSaveMagnet: async (kinopoiskId, magnetLink) => {
                        const result = await movieApi.saveMagnetLink(kinopoiskId, magnetLink);
                        notify(result.message, result.success ? 'success' : 'error');
                        // Обновляем данные и иконку на карточке
                        if (card) {
                            card.dataset.hasMagnet = result.has_magnet.toString();
                            card.dataset.magnetLink = result.magnet_link;
                            toggleDownloadIcon(card, result.has_magnet);
                        }
                        handleOpenModal(lotteryId);
                    },
                    onAddToLibrary: (movieData) => movieApi.addOrUpdateLibraryMovie(movieData).then(data => notify(data.message, data.success ? 'success' : 'error')),
                    onDownload: async () => {
                        try {
                            const result = await downloadTorrentToClient({
                                magnetLink: lotteryData.result.magnet_link,
                                title: lotteryData.result.name,
                            });
                            const status = result.success ? 'success' : 'info';
                            notify(result.message || 'Операция выполнена.', status);
                            if (result.success && card) {
                                card.classList.add('has-torrent-on-client');
                                card.dataset.torrentHash = result.torrent_hash || card.dataset.torrentHash || '';
                                lotteryData.result.is_on_client = true;
                                lotteryData.result.torrent_hash = card.dataset.torrentHash;
                                handleOpenModal(lotteryId);
                            }
                        } catch (error) {
                            notify(error.message || 'Не удалось отправить торрент в клиент.', 'error');
                        }
                    },
                    onDeleteTorrent: async (torrentHash) => {
                        try {
                            const result = await deleteTorrentFromClient(torrentHash);
                            const status = result.success ? 'success' : 'info';
                            notify(result.message || 'Операция выполнена.', status);
                            if (result.success && card) {
                                card.classList.remove('has-torrent-on-client');
                                card.dataset.torrentHash = '';
                                lotteryData.result.is_on_client = false;
                                lotteryData.result.torrent_hash = '';
                                handleOpenModal(lotteryId);
                            }
                        } catch (error) {
                            notify(error.message || 'Не удалось удалить торрент с клиента.', 'error');
                        }
                    }
                };

                modal.renderHistoryModal(lotteryData, actions);
            } else {
                modal.renderWaitingModal(lotteryData);
            }
        } catch (error) {
            modal.renderError(error.message);
        }
    };

    // АВТОПОИСК МАГНЕТ-ССЫЛОК ОТКЛЮЧЕН
    // Пользователь вручную вводит магнет-ссылки через модальное окно
    // Кнопка RuTracker для поиска на сайте сохранена

    gallery.addEventListener('click', (event) => {
        const card = event.target.closest('.gallery-item');
        if (!card) return;

        const { lotteryId, kinopoiskId, movieName, movieSearchName, movieYear, hasMagnet, magnetLink } = card.dataset;
        const button = event.target.closest('.icon-button');

        if (button) {
            event.stopPropagation();
            if (button.classList.contains('delete-button')) {
                movieApi.deleteLottery(lotteryId).then(data => {
                    if (data.success) card.remove();
                    showToast(data.message, data.success ? 'success' : 'error');
                });
            } else if (button.classList.contains('search-rutracker-button')) {
                // Открываем поиск на RuTracker
                const searchQuery = `${movieSearchName || movieName}${movieYear ? ' ' + movieYear : ''}`;
                const encodedQuery = encodeURIComponent(searchQuery);
                const rutrackerUrl = `https://rutracker.org/forum/tracker.php?nm=${encodedQuery}`;
                window.open(rutrackerUrl, '_blank');
                showToast(`Открыт поиск на RuTracker: "${searchQuery}"`, 'info');
            } else if (button.classList.contains('copy-magnet-button')) {
                // Копируем magnet-ссылку в буфер обмена
                if (hasMagnet === 'true' && magnetLink) {
                    navigator.clipboard.writeText(magnetLink).then(() => {
                        showToast('Magnet-ссылка скопирована в буфер обмена', 'success');
                    }).catch(() => {
                        showToast('Не удалось скопировать ссылку', 'error');
                    });
                }
            }
        } else if (lotteryId) {
            handleOpenModal(lotteryId);
        }
    });

    document.querySelectorAll('.date-badge').forEach(badge => {
        badge.textContent = formatDate(badge.dataset.date);
    });
});