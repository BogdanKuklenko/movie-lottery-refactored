# F:\GPT\movie-lottery V2\movie_lottery\routes\main_routes.py
from flask import Blueprint, render_template
from ..models import Lottery, Movie, LibraryMovie, MovieIdentifier
from ..utils.qbittorrent import get_active_torrents_map
from ..utils.helpers import get_background_photos # Мы создадим этот файл на следующем шаге

# Создаем "Blueprint". Это как мини-приложение для наших маршрутов.
# Мы можем зарегистрировать все эти маршруты в основном приложении под одним префиксом.
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html', background_photos=get_background_photos())

@main_bp.route('/wait/<lottery_id>')
def wait_for_result(lottery_id):
    Lottery.query.get_or_404(lottery_id)
    # play_url будет сгенерирован в шаблоне с помощью url_for
    return render_template('wait.html', lottery_id=lottery_id, background_photos=get_background_photos())

@main_bp.route('/history')
def history():
    lotteries = Lottery.query.order_by(Lottery.created_at.desc()).all()
    active_torrents = get_active_torrents_map()
    identifiers = {}
    
    for lottery in lotteries:
        # Находим фильм-победитель
        winner_movie = next((m for m in lottery.movies if m.name == lottery.result_name), None)
        if winner_movie and winner_movie.kinopoisk_id:
            kp_id = winner_movie.kinopoisk_id
            if kp_id not in identifiers:
                identifiers[kp_id] = MovieIdentifier.query.get(kp_id)
            
            # Добавляем новые атрибуты прямо в объект фильма для передачи в шаблон
            winner_movie.is_on_client = kp_id in active_torrents
            winner_movie.torrent_hash = active_torrents.get(kp_id)

    return render_template(
        'history.html',
        lotteries=lotteries,
        identifiers=identifiers,
        background_photos=get_background_photos()
    )

@main_bp.route('/library')
def library():
    library_movies = LibraryMovie.query.order_by(LibraryMovie.added_at.desc()).all()
    active_torrents = get_active_torrents_map()
    
    for movie in library_movies:
        if movie.kinopoisk_id:
            identifier = MovieIdentifier.query.get(movie.kinopoisk_id)
            movie.has_magnet = bool(identifier)
            movie.magnet_link = identifier.magnet_link if identifier else ''
            movie.is_on_client = movie.kinopoisk_id in active_torrents
            movie.torrent_hash = active_torrents.get(movie.kinopoisk_id)
        else:
            movie.has_magnet = False
            movie.magnet_link = ''
            movie.is_on_client = False
            movie.torrent_hash = None
            
    return render_template(
        'library.html',
        library_movies=library_movies,
        background_photos=get_background_photos()
    )

@main_bp.route('/l/<lottery_id>')
def play_lottery(lottery_id):
    lottery = Lottery.query.get_or_404(lottery_id)
    result_obj = {
        "name": lottery.result_name, 
        "poster": lottery.result_poster, 
        "year": lottery.result_year
    } if lottery.result_name else None
    
    return render_template(
        'play.html', 
        lottery=lottery, 
        result=result_obj, 
        background_photos=get_background_photos()
    )

# Служебный маршрут для инициализации БД (оставим его здесь для удобства)
@main_bp.route('/init-db/super-secret-key-for-db-init-12345')
def init_db():
    from .. import db
    with db.get_app().app_context():
        db.drop_all()
        db.create_all()
    return "База данных полностью очищена и создана заново!"