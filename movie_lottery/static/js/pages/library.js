// F:\GPT\movie-lottery V2\movie_lottery\static\js\pages\library.js

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

    const copyButton = actionButtons.querySelector('.copy-magnet-button');
    const searchButton = actionButtons.querySelector('.search-rutracker-button');
    if (copyButton) copyButton.remove();
    if (searchButton) searchButton.remove();

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
    const gallery = document.querySelector('.library-gallery');
    const modalElement = document.getElementById('library-modal');

    if (!gallery || !modalElement) return;

    const modal = new ModalManager(modalElement);

    // --- Функционал выбора фильмов и создания опросов ---
    const toggleSelectModeBtn = document.getElementById('toggle-select-mode-btn');
    const selectionPanel = document.getElementById('selection-panel');
    const selectionCount = document.getElementById('selection-count');
    const createPollBtn = document.getElementById('create-poll-from-selection-btn');
    const cancelSelectionBtn = document.getElementById('cancel-selection-btn');
    const myPollsBtn = document.getElementById('my-polls-btn');
    const myPollsBadge = document.getElementById('my-polls-badge');

    let selectionMode = false;
    let selectedMovies = new Set();

    // Проверяем и загружаем "Мои опросы"
    loadMyPolls();

    function toggleSelectionMode() {
        selectionMode = !selectionMode;
        selectedMovies.clear();
        updateSelectionUI();

        const checkboxes = document.querySelectorAll('.movie-checkbox');
        checkboxes.forEach(cb => {
            cb.style.display = selectionMode ? 'block' : 'none';
            cb.checked = false;
        });

        if (selectionMode) {
            toggleSelectModeBtn.textContent = 'Отменить выбор';
            selectionPanel.style.display = 'flex';
            gallery.classList.add('selection-mode');
        } else {
            toggleSelectModeBtn.textContent = 'Выбрать фильмы';
            selectionPanel.style.display = 'none';
            gallery.classList.remove('selection-mode');
        }
    }

    function updateSelectionUI() {
        selectionCount.textContent = `Выбрано: ${selectedMovies.size}`;
        createPollBtn.disabled = selectedMovies.size < 2 || selectedMovies.size > 25;
    }

    toggleSelectModeBtn.addEventListener('click', toggleSelectionMode);
    cancelSelectionBtn.addEventListener('click', toggleSelectionMode);

    // Обработка выбора фильмов через чекбоксы
    gallery.addEventListener('change', (e) => {
        if (e.target.classList.contains('movie-checkbox')) {
            const movieId = e.target.dataset.movieId;
            if (e.target.checked) {
                selectedMovies.add(movieId);
            } else {
                selectedMovies.delete(movieId);
            }
            updateSelectionUI();
        }
    });

    // Создание опроса из выбранных фильмов
    createPollBtn.addEventListener('click', async () => {
        if (selectedMovies.size < 2 || selectedMovies.size > 25) return;

        createPollBtn.disabled = true;
        createPollBtn.textContent = 'Создание...';

        const moviesData = [];
        selectedMovies.forEach(movieId => {
            const card = document.querySelector(`[data-movie-id="${movieId}"]`);
            if (card) {
                moviesData.push({
                    kinopoisk_id: card.dataset.kinopoiskId || null,
                    name: card.dataset.movieName,
                    search_name: card.dataset.movieSearchName || null,
                    poster: card.dataset.moviePoster || null,
                    year: card.dataset.movieYear || null,
                    description: card.dataset.movieDescription || null,
                    rating_kp: card.dataset.movieRating ? parseFloat(card.dataset.movieRating) : null,
                    genres: card.dataset.movieGenres || null,
                    countries: card.dataset.movieCountries || null
                });
            }
        });

        try {
            const response = await fetch('/api/polls/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ movies: moviesData })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Не удалось создать опрос');
            }

            // Сохраняем токен создателя в localStorage
            const creatorTokens = JSON.parse(localStorage.getItem('pollCreatorTokens') || '{}');
            creatorTokens[data.poll_id] = data.creator_token;
            localStorage.setItem('pollCreatorTokens', JSON.stringify(creatorTokens));

            // Показываем модальное окно с результатом
            showPollCreatedModal(data.poll_url, data.poll_id);

            // Сбрасываем выбор
            toggleSelectionMode();

            // Обновляем кнопку "Мои опросы"
            loadMyPolls();

        } catch (error) {
            showToast(error.message, 'error');
            createPollBtn.disabled = false;
            createPollBtn.textContent = 'Создать опрос';
        }
    });

    function showPollCreatedModal(pollUrl, pollId) {
        const modalContent = `
            <h2>Опрос создан!</h2>
            <p>Поделитесь этой ссылкой с друзьями:</p>
            <div class="link-box">
                <input type="text" id="poll-share-link" value="${pollUrl}" readonly>
                <button class="copy-btn" onclick="copyPollLink()">Копировать</button>
            </div>
            <a href="https://t.me/share/url?url=${encodeURIComponent(pollUrl)}&text=${encodeURIComponent('Приглашаю принять участие в опросе')}" 
               class="action-button-tg" target="_blank">
                Поделиться в Telegram
            </a>
            <p class="poll-info">Результаты появятся в "Мои опросы" после первого голоса</p>
        `;
        modal.open();
        modal.renderCustomContent(modalContent);

        // Добавляем функцию копирования
        window.copyPollLink = () => {
            const input = document.getElementById('poll-share-link');
            input.select();
            document.execCommand('copy');
            showToast('Ссылка скопирована!', 'success');
        };
    }

    async function loadMyPolls() {
        const creatorTokens = JSON.parse(localStorage.getItem('pollCreatorTokens') || '{}');
        const tokens = Object.values(creatorTokens);
        
        if (tokens.length === 0) {
            myPollsBtn.style.display = 'none';
            return;
        }

        try {
            // Проверяем каждый токен и собираем все опросы
            let allPolls = [];
            for (const token of tokens) {
                const response = await fetch(`/api/polls/my-polls?creator_token=${token}`);
                if (response.ok) {
                    const data = await response.json();
                    allPolls = allPolls.concat(data.polls);
                }
            }

            if (allPolls.length > 0) {
                myPollsBtn.style.display = 'inline-block';
                
                // Подсчитываем новые результаты (опросы с голосами)
                const viewedPolls = JSON.parse(localStorage.getItem('viewedPolls') || '{}');
                const newResults = allPolls.filter(poll => !viewedPolls[poll.poll_id]);
                
                if (newResults.length > 0) {
                    myPollsBadge.textContent = newResults.length;
                    myPollsBadge.style.display = 'inline-block';
                } else {
                    myPollsBadge.style.display = 'none';
                }
            } else {
                myPollsBtn.style.display = 'none';
            }
        } catch (error) {
            console.error('Ошибка загрузки опросов:', error);
        }
    }

    myPollsBtn.addEventListener('click', () => {
        showMyPollsModal();
    });

    async function showMyPollsModal() {
        const creatorTokens = JSON.parse(localStorage.getItem('pollCreatorTokens') || '{}');
        const tokens = Object.values(creatorTokens);
        
        let allPolls = [];
        for (const token of tokens) {
            try {
                const response = await fetch(`/api/polls/my-polls?creator_token=${token}`);
                if (response.ok) {
                    const data = await response.json();
                    allPolls = allPolls.concat(data.polls);
                }
            } catch (error) {
                console.error('Ошибка загрузки опросов:', error);
            }
        }

        if (allPolls.length === 0) {
            modal.open();
            modal.renderCustomContent('<h2>Мои опросы</h2><p>У вас пока нет активных опросов с голосами.</p>');
            return;
        }

        // Сортируем по дате создания (новые первые)
        allPolls.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

        let pollsHtml = '<h2>Мои опросы</h2><div class="my-polls-list">';
        
        allPolls.forEach(poll => {
            const createdDate = new Date(poll.created_at).toLocaleString('ru-RU');
            const winnersHtml = poll.winners.map(w => `
                <div class="poll-winner">
                    <img src="${w.poster || 'https://via.placeholder.com/100x150.png?text=No+Image'}" alt="${w.name}">
                    <div class="poll-winner-info">
                        <h4>${w.name}</h4>
                        <p>${w.year || ''}</p>
                        <p class="vote-count">Голосов: ${w.votes}</p>
                    </div>
                </div>
            `).join('');

            pollsHtml += `
                <div class="poll-result-item">
                    <div class="poll-result-header">
                        <h3>Опрос от ${createdDate}</h3>
                        <p>Всего голосов: ${poll.total_votes} | Фильмов: ${poll.movies_count}</p>
                    </div>
                    <div class="poll-winners">
                        ${poll.winners.length > 1 ? '<p><strong>Победители (равное количество голосов):</strong></p>' : '<p><strong>Победитель:</strong></p>'}
                        ${winnersHtml}
                    </div>
                    ${poll.winners.length > 1 ? `
                        <button class="secondary-button create-poll-from-winners" data-winners='${JSON.stringify(poll.winners)}'>
                            Создать опрос из победителей
                        </button>
                    ` : ''}
                    <div class="poll-actions">
                        <button class="secondary-button search-winner-btn" data-movie-name="${poll.winners[0].name}" data-movie-year="${poll.winners[0].year || ''}">
                            Найти на RuTracker
                        </button>
                        <a href="${poll.poll_url}" class="secondary-button" target="_blank">Открыть опрос</a>
                    </div>
                    <a href="https://t.me/share/url?url=${encodeURIComponent(poll.poll_url)}&text=${encodeURIComponent('Приглашаю принять участие в опросе')}"
                       class="action-button-tg" target="_blank">
                        Поделиться в Telegram
                    </a>
                </div>
            `;
        });

        pollsHtml += '</div>';

        modal.open();
        modal.renderCustomContent(pollsHtml);

        // Отмечаем все опросы как просмотренные
        const viewedPolls = JSON.parse(localStorage.getItem('viewedPolls') || '{}');
        allPolls.forEach(poll => {
            viewedPolls[poll.poll_id] = true;
        });
        localStorage.setItem('viewedPolls', JSON.stringify(viewedPolls));

        // Скрываем индикатор
        myPollsBadge.style.display = 'none';

        // Добавляем обработчики для кнопок RuTracker
        document.querySelectorAll('.search-winner-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const movieName = e.target.dataset.movieName;
                const movieYear = e.target.dataset.movieYear;
                const searchQuery = `${movieName}${movieYear ? ' ' + movieYear : ''}`;
                const encodedQuery = encodeURIComponent(searchQuery);
                const rutrackerUrl = `https://rutracker.org/forum/tracker.php?nm=${encodedQuery}`;
                window.open(rutrackerUrl, '_blank');
                showToast(`Открыт поиск на RuTracker: "${searchQuery}"`, 'info');
            });
        });

        // Обработчик для создания опроса из победителей
        document.querySelectorAll('.create-poll-from-winners').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const winners = JSON.parse(e.target.dataset.winners);
                
                btn.disabled = true;
                btn.textContent = 'Создание...';

                try {
                    const response = await fetch('/api/polls/create', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ movies: winners })
                    });

                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(data.error || 'Не удалось создать опрос');
                    }

                    // Сохраняем токен создателя
                    const creatorTokens = JSON.parse(localStorage.getItem('pollCreatorTokens') || '{}');
                    creatorTokens[data.poll_id] = data.creator_token;
                    localStorage.setItem('pollCreatorTokens', JSON.stringify(creatorTokens));

                    showPollCreatedModal(data.poll_url, data.poll_id);
                    loadMyPolls();

                } catch (error) {
                    showToast(error.message, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Создать опрос из победителей';
                }
            });
        });
    }

    // Периодически проверяем новые результаты опросов
    setInterval(loadMyPolls, 10000); // Каждые 10 секунд

    // --- Конец функционала опросов ---

    // --- Функционал "Опрос по бейджу" ---
    const badgePollBtn = document.getElementById('badge-poll-btn');
    const badgePollDropdown = document.querySelector('.badge-poll-dropdown');
    const badgePollMenu = document.getElementById('badge-poll-menu');
    const badgePollOptions = document.querySelectorAll('.badge-poll-option');

    // Загружаем статистику по бейджам
    async function loadBadgeStats() {
        try {
            const response = await fetch('/api/library/badges/stats');
            if (!response.ok) throw new Error('Не удалось загрузить статистику');
            
            const stats = await response.json();
            
            // Обновляем счетчики и состояние кнопок
            badgePollOptions.forEach(option => {
                const badgeType = option.dataset.badge;
                const count = stats[badgeType] || 0;
                const countElement = option.querySelector('.badge-count');
                if (countElement) {
                    countElement.textContent = `(${count})`;
                }
                
                // Активируем только если фильмов >= 2
                option.disabled = count < 2;
            });
        } catch (error) {
            console.error('Ошибка загрузки статистики бейджей:', error);
        }
    }

    // Загружаем статистику при загрузке страницы
    loadBadgeStats();

    // Открытие/закрытие выпадающего меню
    badgePollBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        badgePollDropdown.classList.toggle('active');
        loadBadgeStats(); // Обновляем статистику при открытии
    });

    // Закрытие при клике вне меню
    document.addEventListener('click', (e) => {
        if (!badgePollDropdown.contains(e.target)) {
            badgePollDropdown.classList.remove('active');
        }
    });

    // Создание опроса по бейджу
    badgePollOptions.forEach(option => {
        option.addEventListener('click', async (e) => {
            e.preventDefault();
            if (option.disabled) return;

            const badgeType = option.dataset.badge;
            const badgeName = option.querySelector('.badge-name').textContent;
            const badgeIcon = option.querySelector('.badge-icon').textContent;

            // Закрываем меню
            badgePollDropdown.classList.remove('active');

            // Показываем модальное окно подтверждения
            const confirmHtml = `
                <h2>Создать опрос по бейджу</h2>
                <div style="text-align: center; margin: 20px 0;">
                    <span style="font-size: 48px;">${badgeIcon}</span>
                    <h3 style="margin: 10px 0;">${badgeName}</h3>
                </div>
                <p>Вы действительно хотите создать опрос со всеми фильмами, имеющими бейдж "${badgeName}"?</p>
                <p style="font-size: 14px; color: #adb5bd; margin-top: 10px;">
                    Опрос будет доступен друзьям по ссылке в течение 24 часов.
                </p>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button class="secondary-button" id="cancel-badge-poll" style="flex: 1; padding: 15px; margin: 0;">Отмена</button>
                    <button class="cta-button" id="confirm-badge-poll" style="flex: 1; padding: 15px; margin: 0;">Создать опрос</button>
                </div>
            `;

            modal.open();
            modal.renderCustomContent(confirmHtml);

            // Обработка кнопок подтверждения
            const confirmBtn = document.getElementById('confirm-badge-poll');
            const cancelBtn = document.getElementById('cancel-badge-poll');

            cancelBtn.addEventListener('click', () => {
                modal.close();
            });

            confirmBtn.addEventListener('click', async () => {
                confirmBtn.disabled = true;
                confirmBtn.textContent = 'Создание...';

                try {
                    // Получаем фильмы с выбранным бейджем
                    const response = await fetch(`/api/library/badges/${badgeType}/movies`);
                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(data.error || 'Не удалось получить фильмы');
                    }

                    // Показываем уведомление, если список был ограничен до 25
                    if (data.limited) {
                        showToast(`Внимание: в опрос добавлены только первые 25 фильмов из ${data.total}`, 'warning');
                    }

                    // Создаём опрос
                    const createResponse = await fetch('/api/polls/create', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ movies: data.movies })
                    });

                    const createData = await createResponse.json();

                    if (!createResponse.ok) {
                        throw new Error(createData.error || 'Не удалось создать опрос');
                    }

                    // Сохраняем токен создателя в localStorage
                    const creatorTokens = JSON.parse(localStorage.getItem('pollCreatorTokens') || '{}');
                    creatorTokens[createData.poll_id] = createData.creator_token;
                    localStorage.setItem('pollCreatorTokens', JSON.stringify(creatorTokens));

                    // Показываем модальное окно с результатом
                    showPollCreatedModal(createData.poll_url, createData.poll_id);

                    // Обновляем кнопку "Мои опросы"
                    loadMyPolls();

                    showToast(`Опрос "${badgeName}" успешно создан!`, 'success');

                } catch (error) {
                    showToast(error.message, 'error');
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Создать опрос';
                }
            });
        });
    });

    // --- Конец функционала "Опрос по бейджу" ---

    // --- Функционал фильтрации по бейджам ---
    const badgeFilters = document.querySelectorAll('.badge-filter');
    let currentFilter = 'all';

    // Обновляем счетчики фильтров
    async function updateBadgeFilterStats() {
        try {
            const response = await fetch('/api/library/badges/stats');
            if (!response.ok) throw new Error('Не удалось загрузить статистику');
            
            const stats = await response.json();
            
            // Подсчитываем общее количество фильмов и фильмы без бейджа
            const allCards = document.querySelectorAll('.library-card');
            const totalMovies = allCards.length;
            
            let moviesWithBadges = 0;
            Object.values(stats).forEach(count => {
                moviesWithBadges += count;
            });
            
            const noBadgeCount = totalMovies - moviesWithBadges;
            
            // Обновляем счетчики
            badgeFilters.forEach(filter => {
                const badgeType = filter.dataset.badge;
                const countElement = filter.querySelector('.badge-filter-count');
                
                if (countElement) {
                    let count = 0;
                    if (badgeType === 'all') {
                        count = totalMovies;
                    } else if (badgeType === 'none') {
                        count = noBadgeCount;
                    } else {
                        count = stats[badgeType] || 0;
                    }
                    countElement.textContent = `(${count})`;
                }
            });
        } catch (error) {
            console.error('Ошибка загрузки статистики фильтров:', error);
        }
    }

    // Фильтрация карточек фильмов
    function applyBadgeFilter(filterType) {
        currentFilter = filterType;
        const allCards = document.querySelectorAll('.library-card');
        let visibleCount = 0;
        
        allCards.forEach(card => {
            const cardBadge = card.dataset.badge || '';
            let shouldShow = false;
            
            if (filterType === 'all') {
                shouldShow = true;
            } else if (filterType === 'none') {
                shouldShow = cardBadge === '';
            } else {
                shouldShow = cardBadge === filterType;
            }
            
            if (shouldShow) {
                card.style.display = '';
                visibleCount++;
            } else {
                card.style.display = 'none';
            }
        });
        
        // Показываем/скрываем сообщение о пустой библиотеке
        const emptyMessage = document.querySelector('.library-empty-message');
        if (emptyMessage) {
            emptyMessage.style.display = visibleCount === 0 ? 'block' : 'none';
            if (visibleCount === 0 && filterType !== 'all') {
                emptyMessage.textContent = 'Фильмов с выбранным бейджем не найдено.';
            } else if (visibleCount === 0) {
                emptyMessage.textContent = 'В библиотеке пока нет фильмов.';
            }
        }
    }

    // Обработчики кликов на фильтры
    badgeFilters.forEach(filter => {
        filter.addEventListener('click', () => {
            const filterType = filter.dataset.badge;
            
            // Обновляем активное состояние
            badgeFilters.forEach(f => f.classList.remove('active'));
            filter.classList.add('active');
            
            // Применяем фильтр
            applyBadgeFilter(filterType);
        });
    });

    // Загружаем статистику фильтров при загрузке страницы
    updateBadgeFilterStats();

    // Переопределяем функции setBadge и removeBadge для обновления фильтров
    const originalUpdateBadgeOnCard = updateBadgeOnCard;
    window.updateBadgeOnCard = function(card, badgeType) {
        originalUpdateBadgeOnCard(card, badgeType);
        updateBadgeFilterStats();
        // Применяем текущий фильтр заново
        applyBadgeFilter(currentFilter);
    };

    // --- Конец функционала фильтрации по бейджам ---

    // --- Функционал быстрого просмотра постера ---
    let posterPreviewOverlay = null;
    let isLongPress = false;
    let longPressTimer = null;
    let currentPreviewCard = null;
    const LONG_PRESS_DURATION = 300; // мс для определения длинного нажатия

    function createPosterPreview(posterUrl) {
        // Создаем overlay если его еще нет
        if (!posterPreviewOverlay) {
            posterPreviewOverlay = document.createElement('div');
            posterPreviewOverlay.className = 'poster-preview-overlay';
            document.body.appendChild(posterPreviewOverlay);
        }

        // Создаем изображение
        const img = document.createElement('img');
        img.className = 'poster-preview-image';
        img.src = posterUrl;
        img.alt = 'Постер фильма';

        // Очищаем и добавляем новое изображение
        posterPreviewOverlay.innerHTML = '';
        posterPreviewOverlay.appendChild(img);

        // Показываем overlay
        requestAnimationFrame(() => {
            posterPreviewOverlay.classList.add('active');
        });
    }

    function closePosterPreview() {
        if (posterPreviewOverlay && posterPreviewOverlay.classList.contains('active')) {
            posterPreviewOverlay.classList.remove('active');
            // Удаляем содержимое после анимации
            setTimeout(() => {
                if (posterPreviewOverlay) {
                    posterPreviewOverlay.innerHTML = '';
                }
            }, 200);
        }
        isLongPress = false;
        currentPreviewCard = null;
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
    }

    // Обработчик для карточек фильмов
    function initPosterPreview() {
        const movieCards = document.querySelectorAll('.library-card');

        movieCards.forEach(card => {
            const img = card.querySelector('img');
            if (!img) return;

            // Удаляем старые обработчики если есть
            img.removeEventListener('mousedown', img._posterMouseDown);
            img.removeEventListener('mouseup', img._posterMouseUp);
            img.removeEventListener('mouseleave', img._posterMouseLeave);

            // Mousedown - начинаем отсчет для длинного нажатия
            img._posterMouseDown = (e) => {
                // Только левая кнопка мыши
                if (e.button !== 0) return;
                
                const posterUrl = card.dataset.moviePoster;
                if (!posterUrl || posterUrl === 'https://via.placeholder.com/200x300.png?text=No+Image') {
                    return; // Позволяем обычному клику работать
                }

                currentPreviewCard = card;
                
                // Запускаем таймер для длинного нажатия
                longPressTimer = setTimeout(() => {
                    isLongPress = true;
                    createPosterPreview(posterUrl);
                    // Предотвращаем клик только при длинном нажатии
                    e.preventDefault();
                }, LONG_PRESS_DURATION);
            };

            // Mouseup - отменяем или закрываем
            img._posterMouseUp = (e) => {
                if (longPressTimer) {
                    clearTimeout(longPressTimer);
                    longPressTimer = null;
                }

                if (isLongPress) {
                    e.preventDefault();
                    e.stopPropagation();
                    closePosterPreview();
                }
                // Если не было длинного нажатия - позволяем обычному клику сработать
            };

            // Mouseleave - отменяем превью
            img._posterMouseLeave = () => {
                if (longPressTimer) {
                    clearTimeout(longPressTimer);
                    longPressTimer = null;
                }
                if (isLongPress) {
                    closePosterPreview();
                }
            };

            img.addEventListener('mousedown', img._posterMouseDown);
            img.addEventListener('mouseup', img._posterMouseUp);
            img.addEventListener('mouseleave', img._posterMouseLeave);
        });
    }

    // Глобальные обработчики для закрытия превью
    document.addEventListener('mouseup', (e) => {
        if (isLongPress && !e.target.closest('.poster-preview-overlay')) {
            closePosterPreview();
        }
    });

    // Инициализируем при загрузке
    initPosterPreview();

    // Переинициализируем после изменений в DOM (например, после удаления фильма)
    const originalToggleDownloadIcon = toggleDownloadIcon;
    window.toggleDownloadIcon = function(...args) {
        originalToggleDownloadIcon(...args);
        // Небольшая задержка для обновления DOM
        setTimeout(initPosterPreview, 100);
    };

    // --- Конец функционала быстрого просмотра постера ---

    const getMovieDataFromCard = (card) => {
        const ds = card.dataset;
        return {
            id: ds.movieId,
            kinopoisk_id: ds.kinopoiskId,
            name: ds.movieName,
            search_name: ds.movieSearchName,
            year: ds.movieYear,
            poster: ds.moviePoster,
            description: ds.movieDescription,
            rating_kp: ds.movieRating,
            genres: ds.movieGenres,
            countries: ds.movieCountries,
            has_magnet: ds.hasMagnet === 'true',
            magnet_link: ds.magnetLink,
            is_on_client: card.classList.contains('has-torrent-on-client'),
            torrent_hash: ds.torrentHash,
            badge: ds.badge || null,
        };
    };

    // --- Функционал управления бейджами ---
    const badgeModal = document.getElementById('badge-selector-modal');
    const badgeOptions = badgeModal.querySelectorAll('.badge-option');
    const removeBadgeBtn = badgeModal.querySelector('.remove-badge-btn');
    const cancelBadgeBtn = badgeModal.querySelector('.cancel-badge-btn');
    let currentBadgeCard = null;

    const badgeIcons = {
        'favorite': '⭐',
        'watchlist': '👁️',
        'top': '🏆',
        'watched': '✅',
        'new': '🔥'
    };

    function openBadgeSelector(card) {
        currentBadgeCard = card;
        const currentBadge = card.dataset.badge;

        // Снимаем выделение со всех опций
        badgeOptions.forEach(opt => opt.classList.remove('selected'));

        // Выделяем текущий бейдж, если есть
        if (currentBadge) {
            const selectedOption = Array.from(badgeOptions).find(opt => opt.dataset.badge === currentBadge);
            if (selectedOption) selectedOption.classList.add('selected');
        }

        badgeModal.classList.add('active');
    }

    function closeBadgeSelector() {
        badgeModal.classList.remove('active');
        currentBadgeCard = null;
    }

    async function setBadge(movieId, badgeType) {
        try {
            const response = await fetch(`/api/library/${movieId}/badge`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ badge: badgeType })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Не удалось установить бейдж');
            }

            return data;
        } catch (error) {
            showToast(error.message, 'error');
            throw error;
        }
    }

    async function removeBadge(movieId) {
        try {
            const response = await fetch(`/api/library/${movieId}/badge`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Не удалось удалить бейдж');
            }

            return data;
        } catch (error) {
            showToast(error.message, 'error');
            throw error;
        }
    }

    function updateBadgeOnCard(card, badgeType) {
        card.dataset.badge = badgeType || '';
        
        let badgeElement = card.querySelector('.movie-badge');
        
        if (badgeType) {
            if (!badgeElement) {
                badgeElement = document.createElement('div');
                badgeElement.className = 'movie-badge';
                card.appendChild(badgeElement);
            }
            badgeElement.dataset.badgeType = badgeType;
            badgeElement.textContent = badgeIcons[badgeType] || '';
        } else if (badgeElement) {
            badgeElement.remove();
        }
    }

    // Обработчик клика по опциям бейджа
    badgeOptions.forEach(option => {
        option.addEventListener('click', async () => {
            if (!currentBadgeCard) return;

            const badgeType = option.dataset.badge;
            const movieId = currentBadgeCard.dataset.movieId;

            try {
                await setBadge(movieId, badgeType);
                updateBadgeOnCard(currentBadgeCard, badgeType);
                showToast('Бейдж установлен', 'success');
                closeBadgeSelector();
                // Обновляем статистику бейджей
                loadBadgeStats();
            } catch (error) {
                // Ошибка уже обработана в setBadge
            }
        });
    });

    // Обработчик кнопки "Убрать бейдж"
    removeBadgeBtn.addEventListener('click', async () => {
        if (!currentBadgeCard) return;

        const movieId = currentBadgeCard.dataset.movieId;

        try {
            await removeBadge(movieId);
            updateBadgeOnCard(currentBadgeCard, null);
            showToast('Бейдж удалён', 'success');
            closeBadgeSelector();
            // Обновляем статистику бейджей
            loadBadgeStats();
        } catch (error) {
            // Ошибка уже обработана в removeBadge
        }
    });

    // Обработчик кнопки "Отмена"
    cancelBadgeBtn.addEventListener('click', () => {
        closeBadgeSelector();
    });

    // Закрытие по клику вне модального окна
    badgeModal.addEventListener('click', (e) => {
        if (e.target === badgeModal) {
            closeBadgeSelector();
        }
    });

    // --- Конец функционала управления бейджами ---

    const notify = (message, type = 'info') => {
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            const logger = type === 'error' ? console.error : console.log;
            logger(message);
        }
    };

    const handleOpenModal = (card) => {
        const movieData = getMovieDataFromCard(card);
        modalElement.dataset.activeCardId = card.dataset.movieId || '';
        modal.open();
        const actions = {
            onSaveMagnet: async (kinopoiskId, magnetLink) => {
                const result = await movieApi.saveMagnetLink(kinopoiskId, magnetLink);
                notify(result.message, 'success');
                // Обновляем данные и иконку на карточке
                card.dataset.hasMagnet = result.has_magnet.toString();
                card.dataset.magnetLink = result.magnet_link;
                toggleDownloadIcon(card, result.has_magnet);
                handleOpenModal(card);
            },
            onDeleteFromLibrary: () => {
                movieApi.deleteLibraryMovie(movieData.id).then(data => {
                    if (data.success) {
                        modal.close();
                        card.remove();
                    }
                    notify(data.message, data.success ? 'success' : 'error');
                });
            },
            onSetBadge: async (movieId, badgeType) => {
                try {
                    await setBadge(movieId, badgeType);
                    updateBadgeOnCard(card, badgeType);
                    notify('Бейдж установлен', 'success');
                    handleOpenModal(card);
                } catch (error) {
                    // Ошибка уже обработана в setBadge
                }
            },
            onRemoveBadge: async (movieId) => {
                try {
                    await removeBadge(movieId);
                    updateBadgeOnCard(card, null);
                    notify('Бейдж удалён', 'success');
                    handleOpenModal(card);
                } catch (error) {
                    // Ошибка уже обработана в removeBadge
                }
            },
            onDownload: async () => {
                try {
                    const result = await downloadTorrentToClient({
                        magnetLink: card.dataset.magnetLink,
                        title: movieData.name,
                    });
                    const status = result.success ? 'success' : 'info';
                    notify(result.message || 'Операция выполнена.', status);
                    if (result.success) {
                        card.classList.add('has-torrent-on-client');
                        card.dataset.torrentHash = result.torrent_hash || card.dataset.torrentHash || '';
                        handleOpenModal(card);
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
                    if (result.success) {
                        card.classList.remove('has-torrent-on-client');
                        card.dataset.torrentHash = '';
                        handleOpenModal(card);
                    }
                } catch (error) {
                    notify(error.message || 'Не удалось удалить торрент с клиента.', 'error');
                }
            }
        };

        modal.renderLibraryModal(movieData, actions);
    };

    // АВТОПОИСК МАГНЕТ-ССЫЛОК ОТКЛЮЧЕН
    // Пользователь вручную вводит магнет-ссылки через модальное окно
    // Кнопка RuTracker для поиска на сайте сохранена

    gallery.addEventListener('click', (event) => {
        const card = event.target.closest('.gallery-item');
        if (!card) return;

        const { movieId, kinopoiskId, movieName, movieYear, movieSearchName, hasMagnet, magnetLink } = card.dataset;
        const button = event.target.closest('.icon-button');
        const checkbox = event.target.closest('.movie-checkbox');
        const badgeControlBtn = event.target.closest('.badge-control-btn');

        // Если клик по чекбоксу, не открываем модальное окно
        if (checkbox) {
            event.stopPropagation();
            return;
        }

        // Если клик по кнопке управления бейджами
        if (badgeControlBtn) {
            event.stopPropagation();
            openBadgeSelector(card);
            return;
        }

        if (button) {
            event.stopPropagation();
            if (button.classList.contains('delete-button')) {
                movieApi.deleteLibraryMovie(movieId).then(data => {
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
        } else {
            handleOpenModal(card);
        }
    });

    document.querySelectorAll('.date-badge').forEach(badge => {
        badge.textContent = formatDate(badge.dataset.date);
    });
});