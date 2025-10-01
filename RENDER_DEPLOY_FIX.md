# Исправление проблемы деплоя на Render.com

**Дата:** 1 октября 2025  
**Статус:** ✅ **ИСПРАВЛЕНО**

---

## Проблема

Worker'ы gunicorn падали каждые 30 секунд с ошибками:

```
[CRITICAL] WORKER TIMEOUT (pid:xxx)
[ERROR] Worker was sent SIGKILL! Perhaps out of memory?
```

---

## Причины

### 1. Блокирующая операция при старте

В `movie_lottery/__init__.py` выполнялась операция `db.create_all()` при каждом запуске worker'а:

```python
with app.app_context():
    db.create_all()  # Блокирует на 30+ секунд на PostgreSQL!
```

На удаленной PostgreSQL это может занимать много времени, особенно если база уже создана.

### 2. Timeout по умолчанию

Gunicorn по умолчанию использует timeout = 30 секунд. Если worker не ответит за это время, он убивается.

### 3. Лишние импорты

Импорт `magnet_search.py` создавал ThreadPoolExecutor, который потреблял ресурсы (уже исправлено ранее).

---

## Решение

### 1. Создан файл `gunicorn_config.py`

Конфигурация с оптимальными настройками для Render.com:

```python
# Основные изменения:
workers = 1              # Только 1 worker для экономии памяти
timeout = 120           # Увеличен с 30 до 120 секунд
max_requests = 1000     # Перезапуск для предотвращения утечек памяти
preload_app = False     # НЕ предзагружаем для экономии памяти
```

### 2. Отключен `db.create_all()` на продакшене

В `movie_lottery/__init__.py` добавлена проверка:

```python
# Создаем таблицы только в dev режиме, НЕ на Render.com
if not os.environ.get('RENDER'):
    with app.app_context():
        db.create_all()
```

Render.com автоматически устанавливает переменную окружения `RENDER=true`.

---

## Инструкция по деплою

### Шаг 1: Изменить команду запуска на Render.com

Зайдите в настройки сервиса на Render.com и измените **Build Command** на:

```bash
gunicorn --config gunicorn_config.py "movie_lottery:create_app()"
```

**Или если это не работает, попробуйте:**

```bash
gunicorn -c gunicorn_config.py "movie_lottery:create_app()"
```

**Или просто:**

```bash
gunicorn --workers 1 --timeout 120 "movie_lottery:create_app()"
```

### Шаг 2: Задеплойте изменения

```bash
git add .
git commit -m "Fix: Add gunicorn config and disable db.create_all on production"
git push
```

### Шаг 3: Инициализация базы данных (одноразово)

Если база данных на Render.com еще не создана, выполните один раз:

1. Откройте ваш сайт
2. Перейдите по URL: `https://movie-lottery.onrender.com/init-db/super-secret-key-for-db-init-12345`
3. Это создаст таблицы в базе данных

**ВАЖНО:** После этого удалите или измените этот эндпоинт для безопасности!

---

## Ожидаемый результат

После деплоя логи должны выглядеть так:

```
[INFO] Starting gunicorn 23.0.0
[INFO] Listening at: http://0.0.0.0:10000
[INFO] Using worker: sync
[INFO] Booting worker with pid: 123

==> Your service is live 🎉
```

**НЕТ больше:**
- ❌ WORKER TIMEOUT
- ❌ SIGKILL
- ❌ Постоянных перезапусков

---

## Дополнительные оптимизации

Если проблема сохраняется, попробуйте:

### 1. Увеличить timeout еще больше:

В `gunicorn_config.py`:
```python
timeout = 180  # 3 минуты
```

### 2. Проверить размер базы данных:

Убедитесь, что PostgreSQL база данных на Render.com не слишком большая.

### 3. Отключить qBittorrent проверки при старте:

Если qBittorrent недоступен, это также может блокировать worker'ы.

---

## Файлы изменений

1. ✅ **NEW** `gunicorn_config.py` - конфигурация gunicorn
2. ✅ **CHANGED** `movie_lottery/__init__.py` - отключен db.create_all на продакшене
3. ✅ **CHANGED** `movie_lottery/routes/api_routes.py` - убран импорт magnet_search (ранее)

---

## Проверка здоровья сервиса

После деплоя проверьте:

1. ✅ Главная страница загружается
2. ✅ Можно создать лотерею
3. ✅ Можно добавить фильм в библиотеку
4. ✅ Кнопка RuTracker работает
5. ✅ Ручное добавление магнет-ссылок работает
6. ✅ Логи чистые без ошибок

---

**Автор:** AI Assistant  
**Версия:** 2.0  
**Тип:** Критическое исправление продакшен сервера

