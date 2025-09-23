# F:\GPT\movie-lottery V2\movie_lottery\models.py
from . import db
from datetime import datetime

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

class BackgroundPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poster_url = db.Column(db.String(500), unique=True, nullable=False)
    pos_top = db.Column(db.Float, nullable=False)
    pos_left = db.Column(db.Float, nullable=False)
    rotation = db.Column(db.Integer, nullable=False)
    z_index = db.Column(db.Integer, nullable=False)
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class SearchPreference(db.Model):
    __tablename__ = 'search_preference'

    id = db.Column(db.Integer, primary_key=True)
    quality_priority = db.Column(db.Integer, nullable=False, default=0)
    voice_priority = db.Column(db.Integer, nullable=False, default=0)
    size_priority = db.Column(db.Integer, nullable=False, default=0)
