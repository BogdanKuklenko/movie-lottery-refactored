from datetime import datetime, timedelta
from . import db
import secrets

class MovieIdentifier(db.Model):
    __tablename__ = 'movie_identifier'
    kinopoisk_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    magnet_link = db.Column(db.Text, nullable=False)

class Lottery(db.Model):
    id = db.Column(db.String(6), primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    result_name = db.Column(db.String(200), nullable=True)
    result_poster = db.Column(db.String(500), nullable=True)
    result_year = db.Column(db.String(10), nullable=True)
    movies = db.relationship('Movie', backref='lottery', lazy=True, cascade="all, delete-orphan")

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kinopoisk_id = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(200), nullable=False)
    search_name = db.Column(db.String(200), nullable=True)
    poster = db.Column(db.String(500), nullable=True)
    year = db.Column(db.String(10), nullable=False)
    lottery_id = db.Column(db.String(6), db.ForeignKey('lottery.id'), nullable=False)
    description = db.Column(db.Text, nullable=True)
    rating_kp = db.Column(db.Float, nullable=True)
    genres = db.Column(db.String(200), nullable=True)
    countries = db.Column(db.String(200), nullable=True)

class LibraryMovie(db.Model):
    __tablename__ = 'library_movie'
    id = db.Column(db.Integer, primary_key=True)
    kinopoisk_id = db.Column(db.Integer, unique=True, nullable=True)
    name = db.Column(db.String(200), nullable=False)
    search_name = db.Column(db.String(200), nullable=True)
    poster = db.Column(db.String(500), nullable=True)
    year = db.Column(db.String(10), nullable=True)
    description = db.Column(db.Text, nullable=True)
    rating_kp = db.Column(db.Float, nullable=True)
    genres = db.Column(db.String(200), nullable=True)
    countries = db.Column(db.String(200), nullable=True)
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_interaction_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    badge = db.Column(db.String(20), nullable=True)  # Бейдж: favorite, watchlist, top, watched, new

class BackgroundPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poster_url = db.Column(db.String(500), unique=True, nullable=False)
    pos_top = db.Column(db.Float, nullable=False)
    pos_left = db.Column(db.Float, nullable=False)
    rotation = db.Column(db.Integer, nullable=False)
    z_index = db.Column(db.Integer, nullable=False)
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Poll(db.Model):
    id = db.Column(db.String(8), primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    creator_token = db.Column(db.String(32), nullable=False)  # Токен для идентификации создателя
    movies = db.relationship('PollMovie', backref='poll', lazy=True, cascade="all, delete-orphan")
    votes = db.relationship('Vote', backref='poll', lazy=True, cascade="all, delete-orphan")
    
    def __init__(self, **kwargs):
        super(Poll, self).__init__(**kwargs)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=24)
        if not self.creator_token:
            self.creator_token = secrets.token_hex(16)
    
    @property
    def is_expired(self):
        return datetime.utcnow() > self.expires_at
    
    @property
    def winners(self):
        """Возвращает список фильмов-победителей с максимальным количеством голосов"""
        if not self.votes:
            return []
        
        # Подсчитываем голоса для каждого фильма
        vote_counts = {}
        for vote in self.votes:
            vote_counts[vote.movie_id] = vote_counts.get(vote.movie_id, 0) + 1
        
        if not vote_counts:
            return []
        
        max_votes = max(vote_counts.values())
        winner_movie_ids = [movie_id for movie_id, count in vote_counts.items() if count == max_votes]
        
        return [movie for movie in self.movies if movie.id in winner_movie_ids]
    
    def get_vote_counts(self):
        """Возвращает словарь {movie_id: количество голосов}"""
        vote_counts = {}
        for vote in self.votes:
            vote_counts[vote.movie_id] = vote_counts.get(vote.movie_id, 0) + 1
        return vote_counts

class PollMovie(db.Model):
    __tablename__ = 'poll_movie'
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.String(8), db.ForeignKey('poll.id'), nullable=False)
    kinopoisk_id = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(200), nullable=False)
    search_name = db.Column(db.String(200), nullable=True)
    poster = db.Column(db.String(500), nullable=True)
    year = db.Column(db.String(10), nullable=True)
    description = db.Column(db.Text, nullable=True)
    rating_kp = db.Column(db.Float, nullable=True)
    genres = db.Column(db.String(200), nullable=True)
    countries = db.Column(db.String(200), nullable=True)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.String(8), db.ForeignKey('poll.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('poll_movie.id'), nullable=False)
    voter_token = db.Column(db.String(32), nullable=False)  # Токен для идентификации голосующего
    voted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('poll_id', 'voter_token', name='unique_voter_per_poll'),
    )