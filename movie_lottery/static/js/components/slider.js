// F:\GPT\movie-lottery V2\movie_lottery\static\js\components\slider.js

/**
 * Инициализирует и управляет поведением ползунка для удаления.
 * @param {HTMLElement} sliderContainer - DOM-элемент контейнера слайдера.
 * @param {Function} onDelete - Функция обратного вызова, которая будет выполнена после успешного сдвига ползунка.
 */
export function initSlider(sliderContainer, onDelete) {
    const thumb = sliderContainer.querySelector('.slide-to-delete-thumb');
    const track = sliderContainer.querySelector('.slide-to-delete-track');
    const fill = sliderContainer.querySelector('.slide-to-delete-fill');

    // Проверяем, что все элементы на месте
    if (!thumb || !track || !fill) {
        console.error('Slider elements not found in container.', sliderContainer);
        return;
    }

    const getPointerClientX = (event, fallback = 0) => {
        if (typeof event.clientX === 'number' && !Number.isNaN(event.clientX)) {
            return event.clientX;
        }
        if (event.touches && event.touches.length > 0) {
            return event.touches[0].clientX;
        }
        if (event.changedTouches && event.changedTouches.length > 0) {
            return event.changedTouches[0].clientX;
        }
        return fallback;
    };

    let isDragging = false;
    let startX = 0;
    // Рассчитываем максимальное расстояние для перетаскивания
    const maxDrag = track.offsetWidth - thumb.offsetWidth - 4; // 4px - это сумма боковых отступов/границ бегунка

    // Функция, которая срабатывает при движении мыши/пальца
    const onMouseMove = (e) => {
        if (!isDragging) return;
        // Получаем текущую координату X (работает и для мыши, и для тач-событий)
        const currentX = getPointerClientX(e, startX);
        let moveX = currentX - startX;

        // Ограничиваем движение бегунка в пределах трека
        moveX = Math.max(0, Math.min(moveX, maxDrag));

        // Двигаем бегунок и заполняем фон
        thumb.style.transform = `translateX(${moveX}px)`;
        fill.style.width = `${moveX + (thumb.offsetWidth / 2)}px`;
    };

    // Функция, которая срабатывает, когда пользователь отпускает кнопку мыши/палец
    const onMouseUp = (e) => {
        if (!isDragging) return;
        isDragging = false;

        const currentX = getPointerClientX(e, startX);
        const moveX = currentX - startX;

        // Проверяем, дотащил ли пользователь бегунок до конца
        if (moveX > maxDrag * 0.9) { // Срабатываем, если пройдено 90% пути
            // Успех! Вызываем функцию обратного вызова.
            if (typeof onDelete === 'function') {
                onDelete();
            }
        } else {
            // Если не дотащил, плавно возвращаем бегунок в начало
            thumb.style.transition = 'transform 0.3s ease';
            fill.style.transition = 'width 0.3s ease';
            thumb.style.transform = 'translateX(0px)';
            fill.style.width = '0px';

            // Убираем transition после анимации, чтобы следующее перетаскивание было мгновенным
            setTimeout(() => {
                thumb.style.transition = '';
                fill.style.transition = '';
            }, 300);
        }

        // Удаляем глобальные обработчики событий
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.removeEventListener('touchmove', onMouseMove);
        document.removeEventListener('touchend', onMouseUp);
    };

    // Функция, которая срабатывает, когда пользователь нажимает на бегунок
    const onMouseDown = (e) => {
        // Предотвращаем стандартное поведение, например, выделение текста
        e.preventDefault();

        isDragging = true;
        startX = getPointerClientX(e, startX);

        // Добавляем глобальные обработчики на весь документ
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('touchmove', onMouseMove);
        document.addEventListener('touchend', onMouseUp);
    };

    // Навешиваем начальные обработчики на сам бегунок
    thumb.addEventListener('mousedown', onMouseDown);
    thumb.addEventListener('touchstart', onMouseDown);
}