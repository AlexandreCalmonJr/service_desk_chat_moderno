from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from enum import Enum

db = SQLAlchemy()

class TicketStatus(Enum):
    OPEN = 'Aberto'
    CLOSED = 'Fechado'

class FeedbackType(Enum):
    HELPFUL = 'helpful'
    UNHELPFUL = 'unhelpful'

class Level(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    min_points = db.Column(db.Integer, unique=True, nullable=False, index=True)
    insignia = db.Column(db.String(10), nullable=False, default='🌱')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(20))
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    points = db.Column(db.Integer, default=0)
    level_id = db.Column(db.Integer, db.ForeignKey('level.id'), nullable=False)
    level = db.relationship('Level', backref='users')
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    team = db.relationship('Team', backref='members', lazy='select')

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    level_required = db.Column(db.String(50), default='Iniciante')
    points_reward = db.Column(db.Integer, default=10)
    expected_answer = db.Column(db.String(500), nullable=False)
    unlocks_faq_id = db.Column(db.Integer, db.ForeignKey('faq.id'), nullable=True)

class UserChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('completed_challenges', lazy=True))
    challenge = db.relationship('Challenge', backref=db.backref('completions', lazy=True))

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class FAQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(200), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    video_url = db.Column(db.String(500), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('faqs', lazy=True))
    file_name = db.Column(db.String(255), nullable=True)
    file_data = db.Column(db.LargeBinary, nullable=True)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.Enum(TicketStatus), default=TicketStatus.OPEN)
    description = db.Column(db.Text)

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    members = db.relationship('User', foreign_keys='User.team_id', backref='team', lazy='select')

    @property
    def total_points(self):
        return sum(member.points for member in self.members)