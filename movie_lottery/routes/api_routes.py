# F:\GPT\movie-lottery V2\movie_lottery\routes\api_routes.py
import random
import requests
from flask import Blueprint, request, jsonify, url_for, current_app
from qbittorrentapi import Client, exceptions as qbittorrent_exceptions

from .. import db
from ..models import Movie, Lottery, MovieIdentifier, LibraryMovie, SearchPreference
from ..utils.kinopoisk import get_movie_data_from_kinopoisk
from ..utils.helpers import generate_unique_id, ensure_background_photo
from ..utils.qbittorrent import get_active_torrents_map
from ..utils.torrent_status import qbittorrent_client, torrent_to_json
from ..utils.magnet_search import get_search_status, start_background_search

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _get_or_create_search_preferences():
    preference = SearchPreference.query.get(1)
    if preference is None:
        preference = SearchPreference(id=1)
        db.session.add(preference)
        db.session.commit()
    return preference


def _serialize_preferences(preference: SearchPreference) -> dict:
    return {
        "quality_priority": preference.quality_priority,
        "voice_priority": preference.voice_priority,
        "size_priority": preference.size_priority,
    }


def _parse_priority_value(data: dict, key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or value is None:
        raise ValueError
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError from exc


# --- Маршруты для настроек ---


@api_bp.route('/settings/search-priority', methods=['GET'])
def get_search_priority_settings():
    preference = _get_or_create_search_preferences()
    return jsonify(_serialize_preferences(preference))


@api_bp.route('/settings/search-priority', methods=['POST'])
def update_search_priority_settings():
    data = request.get_json(silent=True) or {}

    try:
        quality_priority = _parse_priority_value(data, 'quality_priority')
        voice_priority = _parse_priority_value(data, 'voice_priority')
        size_priority = _parse_priority_value(data, 'size_priority')
    except ValueError:
        return jsonify({
            "success": False,
            "message": "Некорректные значения приоритетов.",
        }), 400

    preference = _get_or_create_search_preferences()
    preference.quality_priority = quality_priority
    preference.voice_priority = voice_priority
    preference.size_priority = size_priority
    db.session.commit()

    return jsonify({
        "success": True,
        "settings": _serialize_preferences(preference),
    })


def _compose_search_query(
    kinopoisk_id,
    *,
    fallback_name=None,
    fallback_year=None,
    fallback_search_name=None,
):
    def _normalize(value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    titles = []
    search_title_added = False
    year = _normalize(fallback_year)

    normalized_search = _normalize(fallback_search_name)
    if normalized_search:
        titles.append(normalized_search)
        search_title_added = True

    movie = (
        Movie.query.filter_by(kinopoisk_id=kinopoisk_id)
        .order_by(Movie.id.desc())
        .first()
    )
    stored_name = None

    if movie:
        stored_name = _normalize(movie.name)
        year = year or _normalize(movie.year)
        normalized = _normalize(movie.search_name)
        if normalized:
            titles.append(normalized)
            search_title_added = True
    else:
        library_movie = (
            LibraryMovie.query.filter_by(kinopoisk_id=kinopoisk_id)
            .order_by(LibraryMovie.added_at.desc())
            .first()
        )
        if library_movie:
            stored_name = _normalize(library_movie.name)
            year = year or _normalize(library_movie.year)
            normalized = _normalize(library_movie.search_name)
            if normalized:
                titles.append(normalized)
                search_title_added = True

    normalized_fallback_name = _normalize(fallback_name)

    for candidate in (stored_name, normalized_fallback_name):
        if candidate:
            titles.append(candidate)

    deduped_titles = []
    seen_titles = set()
    for title in titles:
        if not title:
            continue
        lowered = title.lower()
        if lowered in seen_titles:
            continue
        deduped_titles.append(title)
        seen_titles.add(lowered)

    if not deduped_titles:
        return ""

    if search_title_added:
        title_part = deduped_titles[0]
    else:
        title_part = " ".join(deduped_titles)

    if year:
        title_part = f"{title_part} {year}".strip()

    return title_part.strip()

# --- Маршруты для работы с фильмами и лотереями ---

@api_bp.route('/fetch-movie', methods=['POST'])
def get_movie_info():
    query = request.json.get('query')
    if not query:
        return jsonify({"error": "Пустой запрос"}), 400
    movie_data = get_movie_data_from_kinopoisk(query)
    if movie_data:
        return jsonify(movie_data)
    else:
        return jsonify({"error": "Фильм не найден"}), 404

@api_bp.route('/create', methods=['POST'])
def create_lottery():
    movies_json = request.json.get('movies')
    if not movies_json or len(movies_json) < 2:
        return jsonify({"error": "Нужно добавить хотя бы два фильма"}), 400

    new_lottery = Lottery(id=generate_unique_id())
    db.session.add(new_lottery)

    search_candidates = []

    for movie_data in movies_json:
        new_movie = Movie(
            kinopoisk_id=movie_data.get('kinopoisk_id'),
            name=movie_data['name'],
            search_name=movie_data.get('search_name'),
            poster=movie_data.get('poster'),
            year=movie_data.get('year'),
            description=movie_data.get('description'),
            rating_kp=movie_data.get('rating_kp'),
            genres=movie_data.get('genres'),
            countries=movie_data.get('countries'),
            lottery=new_lottery
        )
        db.session.add(new_movie)
        if poster := movie_data.get('poster'):
            ensure_background_photo(poster)

        kinopoisk_id = movie_data.get('kinopoisk_id')
        if kinopoisk_id:
            search_candidates.append(
                {
                    'kinopoisk_id': kinopoisk_id,
                    'query': _compose_search_query(
                        kinopoisk_id,
                        fallback_name=movie_data.get('name'),
                        fallback_year=movie_data.get('year'),
                        fallback_search_name=movie_data.get('search_name'),
                    ),
                }
            )

    db.session.commit()

    for candidate in search_candidates:
        if candidate['query']:
            start_background_search(candidate['kinopoisk_id'], candidate['query'])

    # url_for для маршрутов в других blueprint'ах требует указания имени blueprint'а
    wait_url = url_for('main.wait_for_result', lottery_id=new_lottery.id)
    return jsonify({"wait_url": wait_url})

@api_bp.route('/draw/<lottery_id>', methods=['POST'])
def draw_winner(lottery_id):
    lottery = Lottery.query.get_or_404(lottery_id)
    if lottery.result_name:
        return jsonify({
            "name": lottery.result_name, 
            "poster": lottery.result_poster, 
            "year": lottery.result_year
        })
    
    winner = random.choice(lottery.movies)
    lottery.result_name = winner.name
    lottery.result_poster = winner.poster
    lottery.result_year = winner.year
    db.session.commit()
    return jsonify({
        "name": winner.name, 
        "poster": winner.poster, 
        "year": winner.year
    })

@api_bp.route('/result/<lottery_id>')
def get_result_data(lottery_id):
    lottery = Lottery.query.get_or_404(lottery_id)
    # УБИРАЕМ МЕДЛЕННЫЙ ЗАПРОС К ТОРРЕНТАМ
    movies_data = []

    for m in lottery.movies:
        identifier = MovieIdentifier.query.get(m.kinopoisk_id) if m.kinopoisk_id else None
        # Статус торрента теперь будет определяться на фронтенде
        movies_data.append({
            "kinopoisk_id": m.kinopoisk_id, "name": m.name, "search_name": m.search_name, "poster": m.poster, "year": m.year,
            "description": m.description, "rating_kp": m.rating_kp, "genres": m.genres, "countries": m.countries,
            "has_magnet": bool(identifier), "magnet_link": identifier.magnet_link if identifier else None,
            # Передаем пустые значения по умолчанию
            "is_on_client": False, "torrent_hash": None
        })

    result_data = next((m for m in movies_data if m["name"] == lottery.result_name), None) if lottery.result_name else None
    return jsonify({
        "movies": movies_data, 
        "result": result_data, 
        "createdAt": lottery.created_at.isoformat() + "Z", 
        "play_url": url_for('main.play_lottery', lottery_id=lottery.id, _external=True)
    })
    
    result_data = next((m for m in movies_data if m["name"] == lottery.result_name), None) if lottery.result_name else None
    return jsonify({
        "movies": movies_data, 
        "result": result_data, 
        "createdAt": lottery.created_at.isoformat() + "Z", 
        "play_url": url_for('main.play_lottery', lottery_id=lottery.id, _external=True)
    })
    
@api_bp.route('/delete-lottery/<lottery_id>', methods=['POST'])
def delete_lottery(lottery_id):
    lottery_to_delete = Lottery.query.get_or_404(lottery_id)
    message = ""
    config = current_app.config
    try:
        qbt_client = Client(host=config['QBIT_HOST'], port=config['QBIT_PORT'], username=config['QBIT_USERNAME'], password=config['QBIT_PASSWORD'])
        qbt_client.auth_log_in()
        
        category = f"lottery-{lottery_id}"
        torrents_to_delete = qbt_client.torrents_info(category=category)
        
        if torrents_to_delete:
            hashes_to_delete = [t.hash for t in torrents_to_delete]
            qbt_client.torrents_delete(delete_files=True, torrent_hashes=hashes_to_delete)
            message = "Лотерея и связанный торрент успешно удалены."
        else:
            message = "Торрент не найден в клиенте. Лотерея удалена из истории."
            
        qbt_client.auth_log_out()

    except (qbittorrent_exceptions.APIConnectionError, requests.exceptions.RequestException):
        message = "Не удалось подключиться к qBittorrent. Лотерея будет удалена только из истории."
    except Exception as e:
        message = f"Произошла ошибка qBittorrent: {e}. Лотерея будет удалена только из истории."
    
    db.session.delete(lottery_to_delete)
    db.session.commit()
    return jsonify({"success": True, "message": message})

# --- Маршруты для Библиотеки ---

@api_bp.route('/library', methods=['POST'])
def add_library_movie():
    movie_data = request.json.get('movie', {})
    if not movie_data.get('name'):
        return jsonify({"success": False, "message": "Не удалось определить название фильма."}), 400

    existing_movie = None
    kinopoisk_id = movie_data.get('kinopoisk_id')
    if kinopoisk_id:
        existing_movie = LibraryMovie.query.filter_by(kinopoisk_id=kinopoisk_id).first()

    if not existing_movie:
        existing_movie = LibraryMovie.query.filter_by(name=movie_data['name'], year=movie_data.get('year')).first()

    if existing_movie:
        for key, value in movie_data.items():
            if hasattr(existing_movie, key) and value is not None:
                setattr(existing_movie, key, value)
        existing_movie.added_at = db.func.now()
        message = "Информация о фильме обновлена в библиотеке."
        target_kinopoisk_id = existing_movie.kinopoisk_id or kinopoisk_id
    else:
        new_movie = LibraryMovie(**movie_data)
        db.session.add(new_movie)
        message = "Фильм добавлен в библиотеку."
        target_kinopoisk_id = new_movie.kinopoisk_id

    db.session.commit()

    if target_kinopoisk_id:
        query = _compose_search_query(
            target_kinopoisk_id,
            fallback_name=movie_data.get('name'),
            fallback_year=movie_data.get('year'),
            fallback_search_name=movie_data.get('search_name'),
        )
        if query:
            start_background_search(target_kinopoisk_id, query)

    return jsonify({"success": True, "message": message})

@api_bp.route('/library/<int:movie_id>', methods=['DELETE'])
def remove_library_movie(movie_id):
    library_movie = LibraryMovie.query.get_or_404(movie_id)
    db.session.delete(library_movie)
    db.session.commit()
    return jsonify({"success": True, "message": "Фильм удален из библиотеки."})

# --- Маршруты для работы с торрентами ---

@api_bp.route('/movie-magnet', methods=['POST'])
def save_movie_magnet():
    data = request.json
    kinopoisk_id = data.get('kinopoisk_id')
    magnet_link = (data.get('magnet_link') or '').strip()

    if not kinopoisk_id:
        return jsonify({"success": False, "message": "Отсутствует ID фильма"}), 400

    identifier = MovieIdentifier.query.get(kinopoisk_id)
    
    if magnet_link:
        if identifier:
            identifier.magnet_link = magnet_link
        else:
            identifier = MovieIdentifier(kinopoisk_id=kinopoisk_id, magnet_link=magnet_link)
            db.session.add(identifier)
        message = "Magnet-ссылка сохранена."
    elif identifier:
        db.session.delete(identifier)
        message = "Magnet-ссылка удалена."
    else:
        message = "Действий не требуется."

    db.session.commit()
    refreshed_identifier = MovieIdentifier.query.get(kinopoisk_id)
    return jsonify({
        "success": True, "message": message,
        "has_magnet": bool(refreshed_identifier),
        "magnet_link": refreshed_identifier.magnet_link if refreshed_identifier else "",
    })


@api_bp.route('/search-magnet/<int:kinopoisk_id>', methods=['GET', 'POST'])
def search_magnet(kinopoisk_id):
    if request.method == 'GET':
        status = get_search_status(kinopoisk_id)
        return jsonify(status)

    data = request.json or {}
    force = bool(data.get('force'))
    query = (data.get('query') or '').strip()

    if not query:
        query = _compose_search_query(
            kinopoisk_id,
            fallback_name=data.get('title'),
            fallback_year=data.get('year'),
            fallback_search_name=data.get('search_name') or data.get('searchTitle'),
        )

    if not query:
        return jsonify({
            "status": "failed",
            "kinopoisk_id": kinopoisk_id,
            "has_magnet": False,
            "magnet_link": "",
            "message": "Не удалось определить запрос для поиска.",
        }), 400

    status = start_background_search(kinopoisk_id, query, force=force)
    return jsonify(status)

@api_bp.route('/start-download/<int:kinopoisk_id>', methods=['POST'])
def start_download(kinopoisk_id):
    identifier = MovieIdentifier.query.get_or_404(kinopoisk_id)
    # Определяем категорию
    movie_in_lottery = Movie.query.filter_by(kinopoisk_id=kinopoisk_id).order_by(Movie.id.desc()).first()
    category = f"lottery-{movie_in_lottery.lottery_id}" if movie_in_lottery else "lottery-default"
    
    config = current_app.config
    try:
        qbt_client = Client(host=config['QBIT_HOST'], port=config['QBIT_PORT'], username=config['QBIT_USERNAME'], password=config['QBIT_PASSWORD'])
        qbt_client.auth_log_in()
        qbt_client.torrents_add(
            urls=identifier.magnet_link, category=category,
            is_sequential_download=True, is_first_last_piece_priority=True,
            tags=f"kp-{kinopoisk_id}",
        )
        qbt_client.auth_log_out()
        return jsonify({"success": True, "message": "Загрузка началась!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка qBittorrent: {e}"}), 500

@api_bp.route('/library/start-download/<int:movie_id>', methods=['POST'])
def start_library_download(movie_id):
    library_movie = LibraryMovie.query.get_or_404(movie_id)
    if not library_movie.kinopoisk_id:
        return jsonify({"success": False, "message": "Для фильма не указан kinopoisk_id."}), 400

    identifier = MovieIdentifier.query.get_or_404(library_movie.kinopoisk_id, description="Magnet-ссылка не найдена.")
    
    config = current_app.config
    try:
        qbt_client = Client(host=config['QBIT_HOST'], port=config['QBIT_PORT'], username=config['QBIT_USERNAME'], password=config['QBIT_PASSWORD'])
        qbt_client.auth_log_in()
        qbt_client.torrents_add(
            urls=identifier.magnet_link, category=f"library-{movie_id}",
            is_sequential_download=True, is_first_last_piece_priority=True,
            tags=f"kp-{library_movie.kinopoisk_id}",
        )
        qbt_client.auth_log_out()
        return jsonify({"success": True, "message": "Загрузка началась!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка qBittorrent: {e}"}), 500

@api_bp.route('/delete-torrent/<string:torrent_hash>', methods=['POST'])
def delete_torrent_from_client(torrent_hash):
    if not torrent_hash:
        return jsonify({"success": False, "message": "Не указан хеш торрента"}), 400
    
    config = current_app.config
    try:
        qbt_client = Client(host=config['QBIT_HOST'], port=config['QBIT_PORT'], username=config['QBIT_USERNAME'], password=config['QBIT_PASSWORD'])
        qbt_client.auth_log_in()
        qbt_client.torrents_delete(delete_files=True, torrent_hashes=torrent_hash)
        qbt_client.auth_log_out()
        return jsonify({"success": True, "message": "Торрент и файлы удалены с клиента."})
    
    except qbittorrent_exceptions.NotFound404Error:
        return jsonify({"success": False, "message": "Торрент не найден в клиенте."}), 404
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка qBittorrent: {e}"}), 500


def _normalize_tags(tag_string):
    if not tag_string:
        return []
    return [tag.strip().lower() for tag in tag_string.split(',') if tag.strip()]


def _find_first_torrent(torrents, *, tag=None):
    if not torrents:
        return None
    if tag:
        tag = tag.lower()
        for torrent in torrents:
            if tag in _normalize_tags(getattr(torrent, 'tags', '')):
                return torrent
    return torrents[0]


@api_bp.route('/download-status/<int:kinopoisk_id>')
def get_download_status(kinopoisk_id):
    tag = f"kp-{kinopoisk_id}"
    try:
        with qbittorrent_client() as client:
            torrents = client.torrents_info(tag=tag)
            torrent = _find_first_torrent(torrents, tag=tag)
            if not torrent:
                return jsonify({"status": "not_found", "message": "Торрент с указанным ID не найден."})

            status_payload = torrent_to_json(torrent)

            movie = Movie.query.filter_by(kinopoisk_id=kinopoisk_id).order_by(Movie.id.desc()).first()
            if movie:
                status_payload["name"] = movie.name

            return jsonify(status_payload)
    except (qbittorrent_exceptions.APIConnectionError, requests.exceptions.RequestException):
        return jsonify({"status": "error", "message": "Не удалось подключиться к qBittorrent."}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка qBittorrent: {e}"}), 500


@api_bp.route('/torrent-status/<lottery_id>')
def get_torrent_status_for_lottery(lottery_id):
    lottery = Lottery.query.get(lottery_id)
    if not lottery:
        return jsonify({"status": "error", "message": "Лотерея не найдена."}), 404

    category = f"lottery-{lottery_id}"
    try:
        with qbittorrent_client() as client:
            torrents = client.torrents_info(category=category)
            torrent = _find_first_torrent(torrents)
            if not torrent:
                return jsonify({"status": "not_found", "message": "Торрент для лотереи не найден."})

            status_payload = torrent_to_json(torrent)
            if lottery.result_name:
                status_payload["name"] = lottery.result_name

            return jsonify(status_payload)
    except (qbittorrent_exceptions.APIConnectionError, requests.exceptions.RequestException):
        return jsonify({"status": "error", "message": "Не удалось подключиться к qBittorrent."}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка qBittorrent: {e}"}), 500


@api_bp.route('/library/torrent-status/<int:movie_id>')
def get_torrent_status_for_library(movie_id):
    library_movie = LibraryMovie.query.get(movie_id)
    if not library_movie:
        return jsonify({"status": "error", "message": "Фильм не найден в библиотеке."}), 404

    tag = f"kp-{library_movie.kinopoisk_id}" if library_movie.kinopoisk_id else None
    category = f"library-{movie_id}"

    try:
        with qbittorrent_client() as client:
            torrents = client.torrents_info(category=category)
            torrent = _find_first_torrent(torrents, tag=tag)
            if not torrent and tag:
                torrents = client.torrents_info(tag=tag)
                torrent = _find_first_torrent(torrents, tag=tag)

            if not torrent:
                return jsonify({"status": "not_found", "message": "Торрент для фильма не найден."})

            status_payload = torrent_to_json(torrent)
            status_payload["name"] = library_movie.name
            return jsonify(status_payload)
    except (qbittorrent_exceptions.APIConnectionError, requests.exceptions.RequestException):
        return jsonify({"status": "error", "message": "Не удалось подключиться к qBittorrent."}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка qBittorrent: {e}"}), 500


# --- НОВЫЙ МАРШРУТ ДЛЯ ОПТИМИЗАЦИИ ---
@api_bp.route('/active-downloads')
def get_all_active_downloads():
    """Возвращает словарь всех активных торрентов для быстрой проверки на клиенте."""
    torrents_payload = get_active_torrents_map() or {}

    def _stringify_keys(data):
        if not isinstance(data, dict):
            return {}
        return {str(key): value for key, value in data.items()}

    active_map = torrents_payload.get("active") if isinstance(torrents_payload, dict) else {}
    kp_map = torrents_payload.get("kp") if isinstance(torrents_payload, dict) else {}

    response_payload = {
        "active": _stringify_keys(active_map),
        "kp": _stringify_keys(kp_map),
    }

    # Для обратной совместимости: если карта "kp" пуста, а верхний уровень похож на старый формат,
    # возвращаем старую структуру ключ-значение.
    if not response_payload["kp"] and isinstance(torrents_payload, dict) and torrents_payload and "active" not in torrents_payload:
        response_payload["kp"] = _stringify_keys(torrents_payload)
        response_payload["active"] = _stringify_keys(torrents_payload)

    return jsonify(response_payload)
