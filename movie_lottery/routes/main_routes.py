from flask import Blueprint, render_template, url_for
from ..models import Lottery, LibraryMovie, MovieIdentifier, Poll
from ..utils.helpers import get_background_photos

main_bp = Blueprint('main', __name__)

@main_bp.route('/health')
def health():
    """Health check endpoint for Render.com monitoring"""
    return {"status": "ok"}, 200

@main_bp.route('/')
def index():
    return render_template('index.html', background_photos=get_background_photos())

@main_bp.route('/wait/<lottery_id>')
def wait_for_result(lottery_id):
    lottery = Lottery.query.get_or_404(lottery_id)
    play_url = url_for('main.play_lottery', lottery_id=lottery.id, _external=True)
    return render_template(
        'wait.html',
        lottery_id=lottery_id,
        background_photos=get_background_photos(),
        play_url=play_url
    )

@main_bp.route('/history')
def history():
    lotteries = Lottery.query.order_by(Lottery.created_at.desc()).all()
    
    # Collect all unique kinopoisk IDs from winners to avoid N+1 queries
    kp_ids = set()
    for lottery in lotteries:
        winner_movie = next((m for m in lottery.movies if m.name == lottery.result_name), None)
        if winner_movie and winner_movie.kinopoisk_id:
            kp_ids.add(winner_movie.kinopoisk_id)
            winner_movie.is_on_client = False
            winner_movie.torrent_hash = None
    
    # Fetch all identifiers in one query
    identifiers = {}
    if kp_ids:
        identifier_list = MovieIdentifier.query.filter(MovieIdentifier.kinopoisk_id.in_(kp_ids)).all()
        identifiers = {i.kinopoisk_id: i for i in identifier_list}

    return render_template(
        'history.html',
        lotteries=lotteries,
        identifiers=identifiers,
        background_photos=get_background_photos()
    )

@main_bp.route('/library')
def library():
    library_movies = LibraryMovie.query.order_by(LibraryMovie.last_interaction_at.desc()).all()
    
    # Fetch all identifiers in one query to avoid N+1
    kp_ids = [m.kinopoisk_id for m in library_movies if m.kinopoisk_id]
    identifiers_map = {}
    if kp_ids:
        identifiers = MovieIdentifier.query.filter(MovieIdentifier.kinopoisk_id.in_(kp_ids)).all()
        identifiers_map = {i.kinopoisk_id: i for i in identifiers}
    
    for movie in library_movies:
        identifier = identifiers_map.get(movie.kinopoisk_id)
        movie.has_magnet = bool(identifier)
        movie.magnet_link = identifier.magnet_link if identifier else ''
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

@main_bp.route('/p/<poll_id>')
def view_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    return render_template(
        'poll.html',
        poll=poll,
        background_photos=get_background_photos()
    )

@main_bp.route('/init-db/super-secret-key-for-db-init-12345')
def init_db():
    from .. import db
    with db.get_app().app_context():
        db.drop_all()
        db.create_all()
    return "База данных полностью очищена и создана заново!"