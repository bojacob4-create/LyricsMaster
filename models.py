from app import db
from datetime import datetime

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    artist = db.Column(db.String(255), nullable=False)
    song = db.Column(db.String(255), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'artist': self.artist,
            'song': self.song,
            'added_at': self.added_at
        }
