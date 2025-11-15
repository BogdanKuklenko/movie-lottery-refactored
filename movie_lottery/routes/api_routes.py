import random
import secrets
from datetime import datetime
from flask import Blueprint, request, jsonify, url_for

from .. import db
from ..models import Movie, Lottery, MovieIdentifier, LibraryMovie, Poll, PollMovie, Vote
from ..utils.kinopoisk import get_movie_data_from_kinopoisk
from ..utils.helpers import generate_unique_id, ensure_background_photo, generate_unique_poll_id

api_bp = Blueprint('api', __name__, url_prefix='/api')

# --- Routes for movies and lotteries ---

@api_bp.route('/fetch-movie', methods=['POST'])
def get_movie_info():
    query = request.json.get('query')
    if not query:
        return jsonify({"error": "Пустой запрос"}), 400
    movie_data = get_movie_data_from_kinopoisk(query)
    if movie_data:
        # Add poster to background when fetched from Kinopoisk
        if poster := movie_data.get('poster'):
            ensure_background_photo(poster)
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

    db.session.commit()

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
    
    # Collect all kinopoisk IDs to fetch identifiers in one query (avoid N+1)
    kp_ids = [m.kinopoisk_id for m in lottery.movies if m.kinopoisk_id]
    identifiers_map = {}
    if kp_ids:
        identifiers = MovieIdentifier.query.filter(MovieIdentifier.kinopoisk_id.in_(kp_ids)).all()
        identifiers_map = {i.kinopoisk_id: i for i in identifiers}
    
    movies_data = []
    for m in lottery.movies:
        identifier = identifiers_map.get(m.kinopoisk_id)
        movies_data.append({
            "kinopoisk_id": m.kinopoisk_id,
            "name": m.name,
            "search_name": m.search_name,
            "poster": m.poster,
            "year": m.year,
            "description": m.description,
            "rating_kp": m.rating_kp,
            "genres": m.genres,
            "countries": m.countries,
            "has_magnet": bool(identifier),
            "magnet_link": identifier.magnet_link if identifier else None,
            "is_on_client": False,
            "torrent_hash": None
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
    db.session.delete(lottery_to_delete)
    db.session.commit()
    return jsonify({"success": True, "message": "Лотерея успешно удалена."})

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
        existing_movie = LibraryMovie.query.filter_by(
            name=movie_data['name'], 
            year=movie_data.get('year')
        ).first()

    if existing_movie:
        for key, value in movie_data.items():
            if hasattr(existing_movie, key) and value is not None:
                setattr(existing_movie, key, value)
        existing_movie.added_at = db.func.now()
        message = "Фильм уже есть в библиотеке"
    else:
        new_movie = LibraryMovie(**movie_data)
        db.session.add(new_movie)
        message = "Фильм добавлен в библиотеку"

    # Add poster to background when movie is added to library
    if poster := movie_data.get('poster'):
        ensure_background_photo(poster)

    db.session.commit()
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


# Torrent functionality removed - магнет-ссылки сохраняются, но без автоматической загрузки


# --- Маршруты для опросов ---

@api_bp.route('/polls/create', methods=['POST'])
def create_poll():
    """Создание нового опроса"""
    movies_json = request.json.get('movies')
    if not movies_json or len(movies_json) < 2:
        return jsonify({"error": "Нужно добавить хотя бы два фильма"}), 400
    
    if len(movies_json) > 25:
        return jsonify({"error": "Максимум 25 фильмов в опросе"}), 400

    new_poll = Poll(id=generate_unique_poll_id())
    db.session.add(new_poll)

    for movie_data in movies_json:
        new_movie = PollMovie(
            kinopoisk_id=movie_data.get('kinopoisk_id'),
            name=movie_data['name'],
            search_name=movie_data.get('search_name'),
            poster=movie_data.get('poster'),
            year=movie_data.get('year'),
            description=movie_data.get('description'),
            rating_kp=movie_data.get('rating_kp'),
            genres=movie_data.get('genres'),
            countries=movie_data.get('countries'),
            poll=new_poll
        )
        db.session.add(new_movie)
        if poster := movie_data.get('poster'):
            ensure_background_photo(poster)

    db.session.commit()

    poll_url = url_for('main.view_poll', poll_id=new_poll.id, _external=True)
    return jsonify({
        "poll_id": new_poll.id,
        "poll_url": poll_url,
        "creator_token": new_poll.creator_token
    })


@api_bp.route('/polls/<poll_id>', methods=['GET'])
def get_poll(poll_id):
    """Получение данных опроса"""
    poll = Poll.query.get_or_404(poll_id)
    
    if poll.is_expired:
        return jsonify({"error": "Опрос истёк"}), 410
    
    # Получаем токен голосующего из cookie или генерируем новый
    voter_token = request.cookies.get('voter_token')
    if not voter_token:
        voter_token = secrets.token_hex(16)
    
    # Проверяем, голосовал ли уже этот пользователь
    existing_vote = Vote.query.filter_by(poll_id=poll_id, voter_token=voter_token).first()
    
    movies_data = []
    for m in poll.movies:
        movies_data.append({
            "id": m.id,
            "kinopoisk_id": m.kinopoisk_id,
            "name": m.name,
            "search_name": m.search_name,
            "poster": m.poster,
            "year": m.year,
            "description": m.description,
            "rating_kp": m.rating_kp,
            "genres": m.genres,
            "countries": m.countries,
        })
    
    response = jsonify({
        "poll_id": poll.id,
        "movies": movies_data,
        "created_at": poll.created_at.isoformat() + "Z",
        "expires_at": poll.expires_at.isoformat() + "Z",
        "has_voted": bool(existing_vote),
        "total_votes": len(poll.votes)
    })
    
    # Устанавливаем cookie с токеном голосующего
    if not request.cookies.get('voter_token'):
        response.set_cookie('voter_token', voter_token, max_age=60*60*24*30)  # 30 дней
    
    return response


@api_bp.route('/polls/<poll_id>/vote', methods=['POST'])
def vote_in_poll(poll_id):
    """Голосование в опросе"""
    poll = Poll.query.get_or_404(poll_id)
    
    if poll.is_expired:
        return jsonify({"error": "Опрос истёк"}), 410
    
    movie_id = request.json.get('movie_id')
    if not movie_id:
        return jsonify({"error": "Не указан фильм"}), 400
    
    # Проверяем, что фильм принадлежит этому опросу
    movie = PollMovie.query.filter_by(id=movie_id, poll_id=poll_id).first()
    if not movie:
        return jsonify({"error": "Фильм не найден в опросе"}), 404
    
    # Получаем или создаём токен голосующего
    voter_token = request.cookies.get('voter_token')
    if not voter_token:
        voter_token = secrets.token_hex(16)
    
    # Проверяем, не голосовал ли уже этот пользователь
    existing_vote = Vote.query.filter_by(poll_id=poll_id, voter_token=voter_token).first()
    if existing_vote:
        return jsonify({"error": "Вы уже проголосовали в этом опросе"}), 400
    
    # Создаём новый голос
    new_vote = Vote(
        poll_id=poll_id,
        movie_id=movie_id,
        voter_token=voter_token
    )
    db.session.add(new_vote)
    db.session.commit()
    
    response = jsonify({
        "success": True,
        "message": "Голос учтён! Приятного просмотра!",
        "movie_name": movie.name
    })
    
    # Устанавливаем cookie с токеном
    if not request.cookies.get('voter_token'):
        response.set_cookie('voter_token', voter_token, max_age=60*60*24*30)
    
    return response


@api_bp.route('/polls/<poll_id>/results', methods=['GET'])
def get_poll_results(poll_id):
    """Получение результатов опроса (только для создателя)"""
    poll = Poll.query.get_or_404(poll_id)
    
    creator_token = request.args.get('creator_token')
    if not creator_token or creator_token != poll.creator_token:
        return jsonify({"error": "Доступ запрещён"}), 403
    
    if poll.is_expired:
        return jsonify({"error": "Опрос истёк"}), 410
    
    # Получаем статистику голосов
    vote_counts = poll.get_vote_counts()
    winners = poll.winners
    
    movies_with_votes = []
    for movie in poll.movies:
        votes = vote_counts.get(movie.id, 0)
        movies_with_votes.append({
            "id": movie.id,
            "kinopoisk_id": movie.kinopoisk_id,
            "name": movie.name,
            "search_name": movie.search_name,
            "poster": movie.poster,
            "year": movie.year,
            "description": movie.description,
            "rating_kp": movie.rating_kp,
            "genres": movie.genres,
            "countries": movie.countries,
            "votes": votes,
            "is_winner": movie in winners
        })
    
    # Сортируем по количеству голосов
    movies_with_votes.sort(key=lambda x: x['votes'], reverse=True)
    
    return jsonify({
        "poll_id": poll.id,
        "movies": movies_with_votes,
        "total_votes": len(poll.votes),
        "winners": [{"id": w.id, "name": w.name, "poster": w.poster, "year": w.year} for w in winners],
        "created_at": poll.created_at.isoformat() + "Z",
        "expires_at": poll.expires_at.isoformat() + "Z"
    })


@api_bp.route('/polls/my-polls', methods=['GET'])
def get_my_polls():
    """Получение всех опросов пользователя"""
    creator_token = request.args.get('creator_token')
    if not creator_token:
        return jsonify({"polls": []})
    
    # Находим все опросы, созданные этим пользователем
    polls = Poll.query.filter_by(creator_token=creator_token).filter(
        Poll.expires_at > datetime.utcnow()
    ).order_by(Poll.created_at.desc()).all()
    
    polls_data = []
    for poll in polls:
        # Проверяем, есть ли голоса
        if len(poll.votes) == 0:
            continue
        
        vote_counts = poll.get_vote_counts()
        winners = poll.winners
        
        polls_data.append({
            "poll_id": poll.id,
            "created_at": poll.created_at.isoformat() + "Z",
            "expires_at": poll.expires_at.isoformat() + "Z",
            "total_votes": len(poll.votes),
            "movies_count": len(poll.movies),
            "winners": [{"id": w.id, "name": w.name, "poster": w.poster, "year": w.year, "votes": vote_counts.get(w.id, 0)} for w in winners],
            "poll_url": url_for('main.view_poll', poll_id=poll.id, _external=True)
        })
    
    return jsonify({"polls": polls_data})


@api_bp.route('/polls/cleanup-expired', methods=['POST'])
def cleanup_expired_polls():
    """Удаление истёкших опросов (можно вызывать по cron или вручную)"""
    expired_polls = Poll.query.filter(Poll.expires_at <= datetime.utcnow()).all()
    count = len(expired_polls)
    
    for poll in expired_polls:
        db.session.delete(poll)
    
    db.session.commit()
    return jsonify({"success": True, "deleted_count": count})


# --- Маршруты для управления бейджами ---

@api_bp.route('/library/<int:movie_id>/badge', methods=['PUT'])
def set_movie_badge(movie_id):
    """Установка бейджа для фильма в библиотеке"""
    library_movie = LibraryMovie.query.get_or_404(movie_id)
    
    badge_type = request.json.get('badge')
    allowed_badges = ['favorite', 'watchlist', 'top', 'watched', 'new']
    
    if badge_type and badge_type not in allowed_badges:
        return jsonify({"success": False, "message": "Недопустимый тип бейджа"}), 400
    
    library_movie.badge = badge_type
    db.session.commit()
    
    return jsonify({
        "success": True, 
        "message": "Бейдж установлен" if badge_type else "Бейдж удалён",
        "badge": badge_type
    })

@api_bp.route('/library/<int:movie_id>/badge', methods=['DELETE'])
def remove_movie_badge(movie_id):
    """Удаление бейджа у фильма в библиотеке"""
    library_movie = LibraryMovie.query.get_or_404(movie_id)
    library_movie.badge = None
    db.session.commit()
    
    return jsonify({"success": True, "message": "Бейдж удалён"})

@api_bp.route('/library/badges/stats', methods=['GET'])
def get_badge_stats():
    """Получение статистики по бейджам в библиотеке"""
    from sqlalchemy import func
    
    badge_stats = db.session.query(
        LibraryMovie.badge,
        func.count(LibraryMovie.id).label('count')
    ).filter(
        LibraryMovie.badge.isnot(None)
    ).group_by(
        LibraryMovie.badge
    ).all()
    
    stats = {badge: count for badge, count in badge_stats}
    
    # Добавляем все типы бейджей с нулевыми значениями для отсутствующих
    all_badges = ['favorite', 'watchlist', 'top', 'watched', 'new']
    result = {badge: stats.get(badge, 0) for badge in all_badges}
    
    return jsonify(result)

@api_bp.route('/library/badges/<badge_type>/movies', methods=['GET'])
def get_movies_by_badge(badge_type):
    """Получение списка фильмов с определённым бейджем для создания опроса"""
    allowed_badges = ['favorite', 'watchlist', 'top', 'watched', 'new']
    
    if badge_type not in allowed_badges:
        return jsonify({"error": "Недопустимый тип бейджа"}), 400
    
    movies = LibraryMovie.query.filter_by(badge=badge_type).all()
    
    if len(movies) < 2:
        return jsonify({"error": f"Недостаточно фильмов с бейджем '{badge_type}' для создания опроса (минимум 2)"}), 400
    
    # Ограничиваем количество фильмов до 25
    limited = False
    if len(movies) > 25:
        movies = movies[:25]
        limited = True
    
    movies_data = []
    for movie in movies:
        movies_data.append({
            'id': movie.id,
            'kinopoisk_id': movie.kinopoisk_id,
            'name': movie.name,
            'search_name': movie.search_name,
            'year': movie.year,
            'poster': movie.poster,
            'description': movie.description,
            'rating_kp': movie.rating_kp,
            'genres': movie.genres,
            'countries': movie.countries,
            'badge': movie.badge
        })
    
    return jsonify({
        'movies': movies_data,
        'total': len(movies),
        'limited': limited
    })