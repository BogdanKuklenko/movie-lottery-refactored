const ENDPOINT = '/api/settings/search-priority';

const notify = (message, type = 'info') => {
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // eslint-disable-next-line no-console
        console[type === 'error' ? 'error' : 'log'](message);
    }
};

const form = document.getElementById('search-priority-form');

if (form) {
    const qualityInput = document.getElementById('quality-priority-input');
    const voiceInput = document.getElementById('voice-priority-input');
    const sizeInput = document.getElementById('size-priority-input');
    const autoSearchToggle = document.getElementById('auto-search-toggle');
    const submitButton = form.querySelector('button[type="submit"]');

    const fillForm = (data) => {
        if (!data) return;
        if (qualityInput) qualityInput.value = data.quality_priority ?? 0;
        if (voiceInput) voiceInput.value = data.voice_priority ?? 0;
        if (sizeInput) sizeInput.value = data.size_priority ?? 0;
        if (autoSearchToggle) autoSearchToggle.checked = data.auto_search_enabled ?? true;
    };

    const parseInputValue = (input) => {
        if (!input) {
            throw new Error('Поле не найдено');
        }
        const value = Number.parseInt(input.value, 10);
        if (Number.isNaN(value)) {
            throw new Error('Введите числовое значение для всех приоритетов.');
        }
        return value;
    };

    const toggleFormDisabled = (disabled) => {
        if (submitButton) {
            submitButton.disabled = disabled;
        }
        [qualityInput, voiceInput, sizeInput, autoSearchToggle].forEach((input) => {
            if (input) input.disabled = disabled;
        });
    };

    const loadPreferences = async () => {
        try {
            const response = await fetch(ENDPOINT, { method: 'GET' });
            if (!response.ok) {
                throw new Error('Не удалось загрузить настройки.');
            }
            const data = await response.json();
            fillForm(data);
        } catch (error) {
            notify(error.message || 'Не удалось загрузить настройки.', 'error');
        }
    };

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
            const payload = {
                quality_priority: parseInputValue(qualityInput),
                voice_priority: parseInputValue(voiceInput),
                size_priority: parseInputValue(sizeInput),
                auto_search_enabled: Boolean(autoSearchToggle?.checked ?? true),
            };

            toggleFormDisabled(true);

            const response = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            const data = await response.json().catch(() => null);

            if (!response.ok || !data?.success) {
                const message = data?.message || 'Не удалось сохранить настройки.';
                throw new Error(message);
            }

            fillForm(data.settings);
            notify('Настройки сохранены.', 'success');
        } catch (error) {
            notify(error.message || 'Произошла ошибка при сохранении.', 'error');
        } finally {
            toggleFormDisabled(false);
        }
    });

    loadPreferences();
} else {
    // eslint-disable-next-line no-console
    console.warn('Форма настроек поиска не найдена на странице.');
}
