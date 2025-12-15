from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import csv
import json
import re
from PyPDF2 import PdfReader
from datetime import datetime, date, timedelta
try:
    import spacy
    import spacy.cli
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    print("spaCy não está disponível. Algumas funcionalidades de NLP estarão desabilitadas.")
    
import click
from flask.cli import with_appcontext
from flask_caching import Cache
from sqlalchemy.orm import aliased
import cloudinary
import cloudinary.uploader
import cloudinary.api
from sqlalchemy import func
import random
from flask_wtf import FlaskForm
from wtforms import HiddenField
import uuid
import io

app = Flask(__name__)

# --- CONFIGURAÇÕES DA APLICAÇÃO ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'uma-chave-secreta-padrao-para-desenvolvimento')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('CSRF_SECRET_KEY', app.config['SECRET_KEY'])

# --- CONFIGURAÇÃO DO CLOUDINARY ---
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

# --- INICIALIZAÇÃO DAS EXTENSÕES ---
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

redis_url = os.getenv('REDIS_URL')
if redis_url:
    cache = Cache(app, config={'CACHE_TYPE': 'RedisCache', 'CACHE_REDIS_URL': redis_url})
else:
    cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# Configuração do spaCy
nlp = None
if SPACY_AVAILABLE:
    try:
        nlp = spacy.load('pt_core_news_sm')
    except OSError:
        print("Modelo pt_core_news_sm não encontrado. Funcionalidades de NLP estarão desabilitadas.")
        nlp = None

# --- MODELOS DA BASE DE DADOS ---
class BaseForm(FlaskForm):
    csrf_token = HiddenField()

class InvitationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(36), unique=True, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    used_by_user = db.relationship('User', backref='used_invitation_code')

class Level(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    min_points = db.Column(db.Integer, unique=True, nullable=False, index=True)
    insignia = db.Column(db.String(255), nullable=True)  # URL ou emoji

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

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
    level_id = db.Column(db.Integer, db.ForeignKey('level.id'), nullable=True)
    level = db.relationship('Level', backref='users')
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    avatar_url = db.Column(db.String(255), nullable=True)

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner = db.relationship('User', foreign_keys=[owner_id])
    members = db.relationship('User', foreign_keys='User.team_id', backref='team', lazy='dynamic')
    
    @property
    def total_points(self):
        return sum(member.points for member in self.members)

class FAQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    video_url = db.Column(db.String(500))
    file_name = db.Column(db.String(255))
    file_data = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.relationship('Category', backref='faqs')

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Aberto')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    expected_answer = db.Column(db.String(500), nullable=False)
    points_reward = db.Column(db.Integer, default=10)
    level_required = db.Column(db.String(50), default='Iniciante')
    is_team_challenge = db.Column(db.Boolean, default=False)
    hint = db.Column(db.Text, nullable=True)
    hint_cost = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    challenge_type = db.Column(db.String(50), nullable=False, default='text')
    expected_output = db.Column(db.Text, nullable=True)

class UserChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='completed_challenges')
    challenge = db.relationship('Challenge')

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    feedback = db.Column(db.String(20))

class PathChallenge(db.Model):
    path_id = db.Column(db.Integer, db.ForeignKey('learning_path.id'), primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), primary_key=True)
    step = db.Column(db.Integer, nullable=False)
    challenge = db.relationship('Challenge')
    path = db.relationship('LearningPath', back_populates='challenges')

class LearningPath(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    reward_points = db.Column(db.Integer, default=100)
    is_active = db.Column(db.Boolean, default=True)
    challenges = db.relationship('PathChallenge', order_by='PathChallenge.step', cascade='all, delete-orphan', back_populates='path')

class UserPathProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    path_id = db.Column(db.Integer, db.ForeignKey('learning_path.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')
    path = db.relationship('LearningPath')

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(255), nullable=True)
    trigger_type = db.Column(db.String(50), nullable=False)
    trigger_value = db.Column(db.Integer, nullable=False)

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='achievements')
    achievement = db.relationship('Achievement')

class DailyChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, unique=True, nullable=False, default=date.today)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), nullable=False)
    bonus_points = db.Column(db.Integer, default=20)
    challenge = db.relationship('Challenge')

class BossFight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    reward_points = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    image_url = db.Column(db.String(255), nullable=True)
    stages = db.relationship('BossFightStage', backref='boss_fight', lazy='dynamic', order_by='BossFightStage.order')

class BossFightStage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    boss_fight_id = db.Column(db.Integer, db.ForeignKey('boss_fight.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    steps = db.relationship('BossFightStep', backref='stage', lazy='dynamic', order_by='BossFightStep.id', cascade='all, delete-orphan')

class BossFightStep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stage_id = db.Column(db.Integer, db.ForeignKey('boss_fight_stage.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    expected_answer = db.Column(db.String(500), nullable=False)

class TeamBossProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('boss_fight_step.id'), nullable=False)
    completed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    team = db.relationship('Team')
    step = db.relationship('BossFightStep')
    user = db.relationship('User')

class TeamBossCompletion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    boss_fight_id = db.Column(db.Integer, db.ForeignKey('boss_fight.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    team = db.relationship('Team')
    boss_fight = db.relationship('BossFight')

class ScavengerHunt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    reward_points = db.Column(db.Integer, default=100)
    steps = db.relationship('ScavengerHuntStep', backref='hunt', lazy='dynamic', order_by='ScavengerHuntStep.step_number', cascade='all, delete-orphan')

class ScavengerHuntStep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hunt_id = db.Column(db.Integer, db.ForeignKey('scavenger_hunt.id'), nullable=False)
    step_number = db.Column(db.Integer, nullable=False)
    clue_text = db.Column(db.Text, nullable=False) # A pista que o bot dá ao utilizador
    target_type = db.Column(db.String(50), nullable=False) # Ex: 'FAQ', 'CHALLENGE'
    target_identifier = db.Column(db.String(200), nullable=False) # Ex: O título do desafio ou parte da pergunta da FAQ
    hidden_clue = db.Column(db.Text, nullable=False) # A próxima pista a ser revelada

class UserHuntProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    hunt_id = db.Column(db.Integer, db.ForeignKey('scavenger_hunt.id'), nullable=False)
    current_step = db.Column(db.Integer, default=1, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User', backref='hunt_progress')
    hunt = db.relationship('ScavengerHunt')

class GlobalEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    total_hp = db.Column(db.BigInteger, nullable=False) # Usamos BigInteger para vidas muito grandes
    current_hp = db.Column(db.BigInteger, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    reward_points_on_win = db.Column(db.Integer, default=200)
    # Poderíamos adicionar uma conquista aqui também no futuro
    
class GlobalEventContribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('global_event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contribution_points = db.Column(db.Integer, nullable=False) # Quantos "pontos de dano" o user causou
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    event = db.relationship('GlobalEvent', backref=db.backref('contributions', cascade='all, delete-orphan'))
    user = db.relationship('User', backref='event_contributions')
    
class TeamBattle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    challenging_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    challenged_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default='active')  # 'active', 'completed', 'expired'
    winner_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)  
    reward_points = db.Column(db.Integer, default=150) # Pontos para cada membro da equipa vencedora
    challenging_team = db.relationship('Team', foreign_keys=[challenging_team_id])
    challenged_team = db.relationship('Team', foreign_keys=[challenged_team_id])
    winner_team = db.relationship('Team', foreign_keys=[winner_team_id])

class TeamBattleChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey('team_battle.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), nullable=False)
    completed_by_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    battle = db.relationship('TeamBattle', backref=db.backref('battle_challenges', cascade='all, delete-orphan'))
    challenge = db.relationship('Challenge')
    
# Constante de níveis
LEVELS = {
    'Iniciante': {'min_points': 0, 'insignia': '🌱'},
    'Básico': {'min_points': 50, 'insignia': '🌿'},
    'Intermediário': {'min_points': 150, 'insignia': '🌳'},
    'Avançado': {'min_points': 350, 'insignia': '🏆'},
    'Expert': {'min_points': 600, 'insignia': '⭐'},
    'Master': {'min_points': 1000, 'insignia': '👑'}
}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def initialize_database():
    """Inicializa o banco de dados com dados padrão"""
    with app.app_context():
        db.create_all()
        
        for level_name, level_data in LEVELS.items():
            if not Level.query.filter_by(name=level_name).first():
                level = Level(name=level_name, min_points=level_data['min_points'], insignia=level_data['insignia'])
                db.session.add(level)
        
        categories = ['Hardware', 'Software', 'Rede', 'Outros', 'Mobile', 'Automation']
        for category_name in categories:
            if not Category.query.filter_by(name=category_name).first():
                category = Category(name=category_name)
                db.session.add(category)
        
        db.session.commit()
    
def generate_invitation_code():
    """Gera um código de convite único."""
    code = str(uuid.uuid4())
    invitation = InvitationCode(code=code)
    db.session.add(invitation)
    db.session.commit()
    return code

# --- FUNÇÕES DE UTILIDADE ---
def process_ticket_command(message):
    match = re.match(r"Encerrar chamado (\d+)", message)
    if match:
        ticket_id = match.group(1)
        ticket = Ticket.query.filter_by(ticket_id=ticket_id).first()
        if ticket:
            if ticket.status == 'Aberto':
                ticket.status = 'Fechado'
                db.session.commit()
                return f"Chamado {ticket_id} encerrado com sucesso."
            else:
                return f"Chamado {ticket_id} já está fechado."
        return f"Chamado {ticket_id} não encontrado."
    return None

def suggest_solution(message):
    match = re.match(r"Sugerir solução para (.+)", message)
    if match:
        problem = match.group(1).lower()
        solutions = {
            "computador não liga": "Verifique a fonte de energia e reinicie o dispositivo.",
            "internet lenta": "Reinicie o roteador e verifique a conexão.",
            "configurar uma vpn": "Acesse as configurações de rede e insira as credenciais da VPN fornecidas pelo TI."
        }
        return solutions.get(problem, "Desculpe, não tenho uma solução para esse problema no momento.")
    return None

def extract_faqs_from_pdf(file_path):
    try:
        faqs = []
        pdf_reader = PdfReader(file_path)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for i in range(0, len(lines) - 1, 2):
            question = lines[i]
            answer = lines[i + 1]
            faqs.append({"question": question, "answer": answer, "image_url": None, "video_url": None})
        return faqs
    except Exception as e:
        flash(f"Erro ao processar o PDF: {str(e)}", 'error')
        return []

def is_image_url(url):
    if not url:
        return False
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp')
    return url.lower().endswith(image_extensions)

def is_video_url(url):
    if not url:
        return False
    video_extensions = ('.mp4', '.webm', '.ogg')
    return any(url.lower().endswith(ext) for ext in video_extensions) or 'youtube.com' in url.lower() or 'youtu.be' in url.lower()

def format_faq_response(faq_id, question, answer, image_url=None, video_url=None, file_name=None):
    formatted_response = f"<strong>{question}</strong><br><br>"
    has_sections = any(section in answer for section in ["Pré-requisitos:", "Etapa", "Atenção:", "Finalizar:", "Pós-instalação:"])
    
    if has_sections:
        parts = re.split(r'(Pré-requisitos:|Etapa \d+:|Atenção:|Finalizar:|Pós-instalação:)', answer)
        formatted_response += parts[0].replace('\n', '<br>')
        for i in range(1, len(parts), 2):
            header = parts[i]
            content = parts[i+1].replace('\n', '<br>').strip()
            if "Pré-requisitos:" in header:
                formatted_response += f"<strong>✅ {header}</strong><br>{content}<br>"
            elif "Etapa" in header:
                formatted_response += f"<strong>🔧 {header}</strong><br>{content}<br>"
            elif "Atenção:" in header:
                formatted_response += f"<strong>⚠️ {header}</strong><br>{content}<br>"
            elif "Finalizar:" in header:
                formatted_response += f"<strong>⏳ {header}</strong><br>{content}<br>"
            elif "Pós-instalação:" in header:
                formatted_response += f"<strong>✅ {header}</strong><br>{content}<br>"
    else:
        formatted_response += answer.replace('\n', '<br>')

    if image_url and is_image_url(image_url):
        formatted_response += f'<br><img src="{image_url}" alt="Imagem de suporte" style="max-width: 100%; border-radius: 8px; margin-top: 10px;">'
    
    if video_url and is_video_url(video_url):
        if 'youtube.com' in video_url or 'youtu.be' in video_url:
            video_id_match = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', video_url)
            if video_id_match:
                video_id = video_id_match.group(1)
                formatted_response += f'<div style="position: relative; padding-bottom: 56.25%; margin-top: 10px; height: 0; overflow: hidden; max-width: 100%;"><iframe src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe></div>'
        else:
            formatted_response += f'<br><video controls style="max-width: 100%; border-radius: 8px; margin-top: 10px;"><source src="{video_url}" type="video/mp4">O seu navegador não suporta o vídeo.</video>'
    
    if file_name:
        formatted_response += f'<br><br><a href="/download/{faq_id}" class="text-blue-400 hover:underline" target="_blank">📎 Baixar arquivo: {file_name}</a>'
    
    return formatted_response

def get_or_create_daily_challenge():
    today = date.today()
    daily_challenge_entry = DailyChallenge.query.filter_by(day=today).first()
    if daily_challenge_entry:
        return daily_challenge_entry
    thirty_days_ago = today - timedelta(days=30)
    recent_daily_ids = [dc.challenge_id for dc in DailyChallenge.query.filter(DailyChallenge.day > thirty_days_ago).all()]
    available_challenges = Challenge.query.filter(Challenge.id.notin_(recent_daily_ids)).all()
    if not available_challenges:
        available_challenges = Challenge.query.all()
    if available_challenges:
        selected_challenge = random.choice(available_challenges)
        new_daily = DailyChallenge(challenge_id=selected_challenge.id)
        db.session.add(new_daily)
        db.session.commit()
        return new_daily
    return None

def find_faqs_by_keywords(message):
    search_words = set(message.lower().split())
    if not search_words:
        return []
    faqs = FAQ.query.all()
    matches = []
    for faq in faqs:
        question_words = set(faq.question.lower().split())
        answer_words = set(faq.answer.lower().split())
        score = len(search_words.intersection(question_words)) * 2
        score += len(search_words.intersection(answer_words))
        if score > 0:
            matches.append((faq, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches]

def find_faq_by_nlp(message):
    if nlp is None:
        # Fallback to keyword search if spacy is not available
        return find_faqs_by_keywords(message)
    doc = nlp(message.lower())
    keywords = {token.lemma_ for token in doc if not token.is_stop and not token.is_punct}
    if not keywords:
        return []
    faqs = FAQ.query.all()
    matches = []
    for faq in faqs:
        faq_text = f"{faq.question.lower()} {faq.answer.lower()}"
        faq_doc = nlp(faq_text)
        faq_keywords = {token.lemma_ for token in faq_doc if not token.is_stop and not token.is_punct}
        score = len(keywords.intersection(faq_keywords))
        if score > 0:
            matches.append((faq, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches]

def update_user_level(user):
    current_level_id = user.level_id
    new_level = Level.query.filter(Level.min_points <= user.points).order_by(Level.min_points.desc()).first()
    if new_level and new_level.id != current_level_id:
        user.level_id = new_level.id
        flash(f'Subiu de nível! Você agora é {new_level.name}!', 'success')

def check_and_award_achievements(user):
    user_achievements_ids = {ua.achievement_id for ua in user.achievements}
    potential_achievements = Achievement.query.filter(Achievement.id.notin_(user_achievements_ids)).all()
    if not potential_achievements:
        return
    challenges_completed_count = len(user.completed_challenges)
    paths_completed_count = UserPathProgress.query.filter_by(user_id=user.id).count()
    for achievement in potential_achievements:
        unlocked = False
        if achievement.trigger_type == 'challenges_completed':
            if challenges_completed_count >= achievement.trigger_value:
                unlocked = True
        elif achievement.trigger_type == 'points_earned':
            if user.points >= achievement.trigger_value:
                unlocked = True
        elif achievement.trigger_type == 'paths_completed':
            if paths_completed_count >= achievement.trigger_value:
                unlocked = True
        elif achievement.trigger_type == 'first_team_join':
            if user.team_id is not None and achievement.trigger_value == 1:
                unlocked = True
        if unlocked:
            user_achievement = UserAchievement(user_id=user.id, achievement_id=achievement.id)
            db.session.add(user_achievement)
            flash(f'Nova conquista desbloqueada: {achievement.name}!', 'success')

def check_boss_fight_completion(team_id, boss_id):
    boss = BossFight.query.get(boss_id)
    team = Team.query.get(team_id)
    if TeamBossCompletion.query.filter_by(team_id=team_id, boss_fight_id=boss_id).first():
        return
    total_steps_required = db.session.query(func.count(BossFightStep.id))\
        .join(BossFightStage).filter(BossFightStage.boss_fight_id == boss_id).scalar()
    steps_completed_by_team = TeamBossProgress.query.filter_by(team_id=team_id)\
        .join(BossFightStep).join(BossFightStage)\
        .filter(BossFightStage.boss_fight_id == boss_id).count()
    if total_steps_required > 0 and steps_completed_by_team >= total_steps_required:
        for member in team.members:
            member.points += boss.reward_points
            update_user_level(member)
        completion_record = TeamBossCompletion(team_id=team_id, boss_fight_id=boss_id)
        db.session.add(completion_record)
        db.session.commit()
        flash(f'Parabéns Equipe "{team.name}"! Vocês derrotaram o Boss "{boss.name}" e cada membro ganhou {boss.reward_points} pontos!', 'success')

def check_and_complete_paths(user, completed_challenge_id):
    paths_containing_challenge = PathChallenge.query.filter_by(challenge_id=completed_challenge_id).all()
    if not paths_containing_challenge:
        return
    user_completed_challenges = {uc.challenge_id for uc in user.completed_challenges}
    for pc in paths_containing_challenge:
        path = pc.path
        if UserPathProgress.query.filter_by(user_id=user.id, path_id=path.id).first():
            continue
        all_challenges_in_path = {c.challenge_id for c in path.challenges}
        if all_challenges_in_path.issubset(user_completed_challenges):
            user.points += path.reward_points
            progress = UserPathProgress(user_id=user.id, path_id=path.id)
            db.session.add(progress)
            db.session.commit()
            check_and_award_achievements(user)
            flash(f'Trilha "{path.name}" concluída! Você ganhou {path.reward_points} pontos de bônus!', 'success')

def finalize_ended_battles():
    """
    Verifica todas as batalhas ativas, finaliza as que já terminaram,
    calcula o vencedor e distribui os prémios.
    """
    ended_battles = TeamBattle.query.filter(
        TeamBattle.status == 'active',
        TeamBattle.end_time <= datetime.utcnow()
    ).all()

    battles_finalized_count = 0
    for battle in ended_battles:
        # Contar quantos desafios cada equipa completou
        challenger_score = TeamBattleChallenge.query.filter(
            TeamBattleChallenge.battle_id == battle.id,
            TeamBattleChallenge.completed_by_team_id == battle.challenging_team_id
        ).count()
        
        challenged_score = TeamBattleChallenge.query.filter(
            TeamBattleChallenge.battle_id == battle.id,
            TeamBattleChallenge.completed_by_team_id == battle.challenged_team_id
        ).count()

        # Determinar o vencedor
        winner = None
        if challenger_score > challenged_score:
            winner = battle.challenging_team
        elif challenged_score > challenger_score:
            winner = battle.challenged_team
        # Em caso de empate, ninguém vence

        if winner:
            battle.winner_team_id = winner.id
            # Distribuir os pontos para cada membro da equipa vencedora
            for member in winner.members:
                member.points += battle.reward_points
                update_user_level(member) # Atualiza o nível do membro, se aplicável
            flash(f'A equipa "{winner.name}" venceu a batalha contra "{battle.challenged_team.name if winner.id == battle.challenging_team_id else battle.challenging_team.name}"!', 'success')
        
        battle.status = 'completed'
        battles_finalized_count += 1
    
    if battles_finalized_count > 0:
        db.session.commit()
    
    return battles_finalized_count

# --- CONTEXT PROCESSORS ---
@app.context_processor
def inject_user_gamification_data():
    if current_user.is_authenticated and current_user.level:
        return dict(user_level_insignia=current_user.level.insignia)
    return dict(user_level_insignia='')

@app.context_processor
def inject_gamification_progress():
    if not current_user.is_authenticated:
        return {}
    progress_data = {'percentage': 0, 'next_level_points': None}
    if current_user.level:
        current_level = current_user.level
        next_level = Level.query.filter(Level.min_points > current_level.min_points).order_by(Level.min_points.asc()).first()
        if next_level:
            points_for_level = next_level.min_points - current_level.min_points
            points_achieved = current_user.points - current_level.min_points
            progress_data['percentage'] = max(0, min(100, (points_achieved / points_for_level) * 100 if points_for_level > 0 else 100))
            progress_data['next_level_points'] = next_level.min_points
        else:
            progress_data['percentage'] = 100
    return dict(progress=progress_data)

# --- ROTAS ---
@app.route('/')
@login_required
def index():
    daily_challenge = get_or_create_daily_challenge()
    active_hunt = ScavengerHunt.query.filter_by(is_active=True).first()
    hunt_progress = None
    if active_hunt:
        hunt_progress = UserHuntProgress.query.filter_by(user_id=current_user.id, hunt_id=active_hunt.id).first()

    
    active_event = GlobalEvent.query.filter(
        GlobalEvent.is_active == True,
        GlobalEvent.end_date >= datetime.utcnow(),
        GlobalEvent.current_hp > 0
    ).first()

    event_progress = 0
    if active_event:
        event_progress = ((active_event.total_hp - active_event.current_hp) / active_event.total_hp) * 100

    return render_template('dashboard.html', 
                            daily_challenge=daily_challenge,
                            active_hunt=active_hunt, 
                            hunt_progress=hunt_progress,
                            active_event=active_event,      
                            event_progress=event_progress)

@app.route('/hunt/start/<int:hunt_id>', methods=['POST'])
@login_required
def start_hunt(hunt_id):
    hunt = ScavengerHunt.query.get_or_404(hunt_id)
    existing_progress = UserHuntProgress.query.filter_by(user_id=current_user.id, hunt_id=hunt.id).first()
    if not existing_progress:
        new_progress = UserHuntProgress(user_id=current_user.id, hunt_id=hunt.id, current_step=1)
        db.session.add(new_progress)
        db.session.commit()
        flash('Você começou a caça ao tesouro! Boa sorte!', 'success')
    return redirect(url_for('index'))

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    all_users = User.query.order_by(User.name).all()
    return render_template('admin_users.html', users=all_users, form=form)

@app.route('/ranking')
@login_required
def ranking():
    ranked_users = User.query.order_by(User.points.desc()).all()
    all_teams = Team.query.all()
    ranked_teams = sorted(all_teams, key=lambda t: t.total_points, reverse=True)
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_leaders = db.session.query(
        User, func.sum(Challenge.points_reward).label('monthly_points')
    ).join(UserChallenge, User.id == UserChallenge.user_id).join(Challenge, Challenge.id == UserChallenge.challenge_id).filter(UserChallenge.completed_at >= start_of_month).group_by(User).order_by(func.sum(Challenge.points_reward).desc()).limit(10).all()
    start_of_week = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_leaders = db.session.query(
        User, func.sum(Challenge.points_reward).label('weekly_points')
    ).join(UserChallenge, User.id == UserChallenge.user_id).join(Challenge, Challenge.id == UserChallenge.challenge_id).filter(UserChallenge.completed_at >= start_of_week).group_by(User).order_by(func.sum(Challenge.points_reward).desc()).limit(10).all()
    return render_template(
        'ranking.html', 
        ranked_users=ranked_users, 
        ranked_teams=ranked_teams,
        monthly_leaders=monthly_leaders,
        weekly_leaders=weekly_leaders
    )
@app.route('/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_users'))
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f'Usuário {"promovido a admin" if user.is_admin else "removido como admin"} com sucesso!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Apaga um utilizador e todos os seus dados associados de forma segura."""
    if not current_user.is_admin or current_user.id == user_id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('admin_users'))

    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_users'))

    user_to_delete = User.query.get_or_404(user_id)

    # 1. Lidar com a posse da equipa
    owned_team = Team.query.filter_by(owner_id=user_to_delete.id).first()
    if owned_team:
        other_members = owned_team.members.filter(User.id != user_to_delete.id).order_by(User.registered_at).all()
        if other_members:
            # Transfere a posse para o membro mais antigo
            new_owner = other_members[0]
            owned_team.owner_id = new_owner.id
            flash(f"A posse da equipa '{owned_team.name}' foi transferida para {new_owner.name}.", 'info')
        else:
            # Apaga a equipa se for o único membro
            TeamBossCompletion.query.filter_by(team_id=owned_team.id).delete()
            TeamBossProgress.query.filter_by(team_id=owned_team.id).delete()
            db.session.delete(owned_team)
            flash(f"A equipa '{owned_team.name}' foi dissolvida pois o dono foi apagado.", 'info')

    # 2. Apagar todas as dependências
    UserChallenge.query.filter_by(user_id=user_to_delete.id).delete()
    UserPathProgress.query.filter_by(user_id=user_to_delete.id).delete()
    UserAchievement.query.filter_by(user_id=user_to_delete.id).delete()
    TeamBossProgress.query.filter_by(completed_by_user_id=user_to_delete.id).delete()
    ChatMessage.query.filter_by(user_id=user_to_delete.id).delete()
    
    # Desvincula o código de convite em vez de apagar
    InvitationCode.query.filter_by(used_by_user_id=user_to_delete.id).update({'used_by_user_id': None, 'used': False})
    
    # 3. Apagar o utilizador
    db.session.delete(user_to_delete)
    db.session.commit()

    flash(f'Utilizador {user_to_delete.name} e todos os seus dados foram apagados com sucesso.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/chat-page')
@login_required
def chat_page():
    session.pop('faq_selection', None)
    return render_template('chat.html')

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    mensagem = data.get('mensagem', '').strip()
    
    active_hunt = ScavengerHunt.query.filter_by(is_active=True).first()
    if active_hunt:
        progress = UserHuntProgress.query.filter_by(user_id=current_user.id, hunt_id=active_hunt.id).first()
        if progress and not progress.completed_at:
            current_step_info = ScavengerHuntStep.query.filter_by(hunt_id=active_hunt.id, step_number=progress.current_step).first()
            
            # Verifica se a mensagem do utilizador resolve o passo atual
            if current_step_info and current_step_info.target_identifier.lower() in mensagem.lower():
                next_step_info = ScavengerHuntStep.query.filter_by(hunt_id=active_hunt.id, step_number=progress.current_step + 1).first()
                
                if next_step_info:
                    progress.current_step += 1
                    db.session.commit()
                    resposta_caca = f"🎉 **Pista Encontrada!**<br><br>{current_step_info.hidden_clue}<br><br><strong>Próxima Pista:</strong> {next_step_info.clue_text}"
                    return jsonify({'text': resposta_caca, 'html': True, 'state': 'normal', 'options': []})
                else:
                    # O aluno encontrou a última pista e completou a caça!
                    progress.completed_at = datetime.utcnow()
                    current_user.points += active_hunt.reward_points
                    update_user_level(current_user)
                    check_and_award_achievements(current_user)
                    db.session.commit()
                    resposta_final = f"🏆 **Parabéns!** Você completou a caça ao tesouro '{active_hunt.name}' e ganhou {active_hunt.reward_points} pontos! A última pista era: {current_step_info.hidden_clue}"
                    return jsonify({'text': resposta_final, 'html': True, 'state': 'normal', 'options': []})
                
    resposta = {
        'text': "Desculpe, não entendi. Tente reformular a pergunta.",
        'html': False,
        'state': 'normal',
        'options': [],
        'suggestion': None
    }
    ticket_response = process_ticket_command(mensagem)
    if ticket_response:
        resposta['text'] = ticket_response
        return jsonify(resposta)
    solution_response = suggest_solution(mensagem)
    if solution_response:
        resposta['text'] = solution_response
        return jsonify(resposta)
    faq_matches = find_faq_by_nlp(mensagem)
    if faq_matches:
        if len(faq_matches) == 1:
            faq = faq_matches[0]
            resposta['text'] = format_faq_response(faq.id, faq.question, faq.answer, faq.image_url, faq.video_url, faq.file_name)
            resposta['html'] = True
            doc = nlp(faq.question.lower())
            keywords = {token.lemma_ for token in doc if not token.is_stop and not token.is_punct and token.pos_ == 'NOUN'}
            if keywords:
                relevant_challenge = Challenge.query.filter(Challenge.title.ilike(f'%{next(iter(keywords))}%')).first()
                if relevant_challenge:
                    is_completed = UserChallenge.query.filter_by(user_id=current_user.id, challenge_id=relevant_challenge.id).first()
                    if not is_completed:
                        resposta['suggestion'] = {
                            'text': f"Parece que você está interessado neste tópico! Que tal tentar o desafio '{relevant_challenge.title}' e ganhar {relevant_challenge.points_reward} pontos?",
                            'challenge_id': relevant_challenge.id
                        }
        else:
            faq_ids = [faq.id for faq in faq_matches]
            session['faq_selection'] = faq_ids
            resposta['state'] = 'faq_selection'
            resposta['text'] = "Encontrei várias FAQs relacionadas. Clique na que você deseja:"
            resposta['html'] = True
            resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches][:5]
    else:
        resposta['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta."
    return jsonify(resposta)

@app.route('/chat/faq_select', methods=['POST'])
@login_required
def chat_faq_select():
    """Endpoint chamado quando o utilizador clica numa das opções de FAQ."""
    data = request.get_json()
    faq_id = data.get('faq_id')
    if not faq_id:
        return jsonify({'text': 'ID da FAQ não fornecido.', 'html': True}), 400
    faq = FAQ.query.get(faq_id)
    if not faq:
        return jsonify({'text': 'FAQ não encontrada.', 'html': True}), 404
    response_text = format_faq_response(
        faq.id, faq.question, faq.answer,
        faq.image_url, faq.video_url, faq.file_name
    )
    return jsonify({
        'text': response_text,
        'html': True,
        'state': 'normal',
        'options': []
    })

@app.route('/chat/feedback', methods=['POST'])
@login_required
def chat_feedback():
    data = request.get_json()
    message_id = data.get('message_id')
    feedback_type = data.get('feedback')
    message = ChatMessage.query.get(message_id)
    if message and message.user_id == current_user.id:
        message.feedback = feedback_type
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Mensagem não encontrada ou não autorizada'}), 404

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.phone = request.form.get('phone')
        file = request.files.get('avatar')
        if file and file.filename:
            try:
                upload_result = cloudinary.uploader.upload(file, folder="avatars")
                current_user.avatar_url = upload_result['secure_url']
            except Exception as e:
                flash(f'Erro ao fazer upload do avatar: {e}', 'error')
        db.session.commit()
        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html')

@app.route('/faqs', methods=['GET'])
@login_required
def faqs():
    categories = Category.query.all()
    faqs = FAQ.query.all()
    faq_to_edit = None
    if request.args.get('edit'):
        faq_id = request.args.get('edit')
        faq_to_edit = FAQ.query.get_or_404(faq_id)
    return render_template('faqs.html', faqs=faqs, categories=categories, faq_to_edit=faq_to_edit)

@app.route('/faqs/edit/<int:faq_id>', methods=['GET', 'POST'])
@login_required
def edit_faq(faq_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem gerenciar FAQs.', 'error')
        return redirect(url_for('faqs'))
    faq = FAQ.query.get_or_404(faq_id)
    if request.method == 'POST':
        faq.category_id = request.form['edit_category']
        faq.question = request.form['edit_question']
        faq.answer = request.form['edit_answer']
        faq.image_url = request.form.get('edit_image_url') or None
        faq.video_url = request.form.get('edit_video_url') or None
        file = request.files.get('edit_file')
        if file and file.filename:
            faq.file_name = file.filename
            faq.file_data = file.read()
        db.session.commit()
        flash('FAQ atualizada com sucesso!', 'success')
        return redirect(url_for('faqs'))
    return redirect(url_for('faqs', edit=faq_id))

@app.route('/faqs/delete/<int:faq_id>', methods=['POST'])
@login_required
def delete_faq(faq_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem gerenciar FAQs.', 'error')
        return redirect(url_for('faqs'))
    faq = FAQ.query.get_or_404(faq_id)
    db.session.delete(faq)
    db.session.commit()
    flash('FAQ excluída com sucesso!', 'success')
    return redirect(url_for('faqs'))

@app.route('/faqs/delete-multiple', methods=['POST'])
@login_required
def delete_multiple_faqs():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem gerenciar FAQs.', 'error')
        return redirect(url_for('faqs'))
    faq_ids = request.form.getlist('faq_ids')
    if faq_ids:
        FAQs_to_delete = FAQ.query.filter(FAQ.id.in_(faq_ids)).all()
        for faq in FAQs_to_delete:
            db.session.delete(faq)
        db.session.commit()
        flash(f'{len(faq_ids)} FAQs excluídas com sucesso!', 'success')
    else:
        flash('Nenhuma FAQ selecionada para exclusão.', 'error')
    return redirect(url_for('faqs'))

@app.route('/download/<int:faq_id>')
@login_required
def download(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    if faq.file_data:
        return send_file(io.BytesIO(faq.file_data), download_name=faq.file_name, as_attachment=True)
    flash('Nenhum arquivo encontrado.', 'error')
    return redirect(url_for('faqs'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('login'))
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        flash('Email ou senha inválidos.', 'error')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('register'))
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        invitation_code = request.form['invitation_code']
        invitation = InvitationCode.query.filter_by(code=invitation_code, used=False).first()
        if not invitation:
            flash('Código de convite inválido ou já utilizado.', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email já registrado.', 'error')
            return redirect(url_for('register'))
        initial_level = Level.query.order_by(Level.min_points).first()
        if not initial_level:
            flash('Erro de sistema: Nenhum nível inicial encontrado. Contate o administrador.', 'error')
            return redirect(url_for('register'))
        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            is_admin=False,
            level_id=initial_level.id
        )
        db.session.add(user)
        db.session.commit()
        
        invitation.used = True
        invitation.used_by_user_id = user.id
        db.session.commit()
        
        flash('Registro concluído! Faça login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/generate_invitation', methods=['POST'])
@login_required
def generate_invitation():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_users'))
    user_id = request.form.get('user_id')
    code = generate_invitation_code()
    return jsonify({'code': code})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu com sucesso.', 'success')
    return redirect(url_for('login'))

@app.route('/admin/faq', methods=['GET', 'POST'])
@login_required
def admin_faq():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('admin_faq'))
        action = request.form.get('action')
        if action == 'create_faq':
            category_id = request.form['category']
            question = request.form['question']
            answer = request.form['answer']
            image_url = request.form.get('image_url')
            video_url = request.form.get('video_url')
            file = request.files.get('file')
            file_name = None
            file_data = None
            if file:
                file_name = secure_filename(file.filename)
                file_data = file.read()
            faq = FAQ(
                category_id=category_id,
                question=question,
                answer=answer,
                image_url=image_url,
                video_url=video_url,
                file_name=file_name,
                file_data=file_data
            )
            db.session.add(faq)
            db.session.commit()
            flash('FAQ criada com sucesso!', 'success')
        elif action == 'import_faqs':
            category_id = request.form['category_import']
            file = request.files['faq_file']
            if file:
                if file.filename.endswith('.json'):
                    try:
                        data = json.load(file)
                        for faq_data in data:
                            faq = FAQ(
                                category_id=category_id,
                                question=faq_data['question'],
                                answer=faq_data['answer'],
                                image_url=faq_data.get('image_url'),
                                video_url=faq_data.get('video_url')
                            )
                            db.session.add(faq)
                        db.session.commit()
                        flash('FAQs importadas com sucesso!', 'success')
                    except Exception as e:
                        flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                elif file.filename.endswith('.csv'):
                    try:
                        csv_data = csv.DictReader(file.stream.read().decode('utf-8').splitlines())
                        for row in csv_data:
                            faq = FAQ(
                                category_id=category_id,
                                question=row['question'],
                                answer=row['answer'],
                                image_url=row.get('image_url'),
                                video_url=row.get('video_url')
                            )
                            db.session.add(faq)
                        db.session.commit()
                        flash('FAQs importadas com sucesso!', 'success')
                    except Exception as e:
                        flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                elif file.filename.endswith('.pdf'):
                    try:
                        pdf = PdfReader(file)
                        text = ''
                        for page in pdf.pages:
                            text += page.extract_text()
                        doc = nlp(text)
                        for sent in doc.sents:
                            faq = FAQ(
                                category_id=category_id,
                                question=sent.text[:200],
                                answer=sent.text
                            )
                            db.session.add(faq)
                        db.session.commit()
                        flash('FAQs extraídas do PDF com sucesso!', 'success')
                    except Exception as e:
                        flash(f'Erro ao importar FAQs do PDF: {str(e)}', 'error')
                else:
                    flash('Formato de arquivo não suportado.', 'error')
            else:
                flash('Por favor, envie um arquivo válido.', 'error')
        return redirect(url_for('admin_faq'))
    faqs = FAQ.query.order_by(FAQ.id.desc()).all()
    categories = Category.query.all()
    return render_template('admin_faq.html', faqs=faqs, categories=categories, form=form)

@app.route('/admin/export/faqs')
@login_required
def export_faqs():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    faqs = FAQ.query.all()
    faqs_list = []
    for faq in faqs:
        faqs_list.append({
            'category': faq.category.name,
            'question': faq.question,
            'answer': faq.answer,
            'image_url': faq.image_url,
            'video_url': faq.video_url
        })
    response = jsonify(faqs_list)
    response.headers['Content-Disposition'] = 'attachment; filename=faqs_backup.json'
    return response

@app.route('/challenges')
@login_required
def list_challenges():
    if not current_user.level:
        flash('Não foi possível determinar o seu nível. Contate o suporte.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    completed_challenges_ids = [uc.challenge_id for uc in current_user.completed_challenges]
    user_min_points = current_user.level.min_points
    RequiredLevel = aliased(Level)
    all_challenges_query = db.session.query(Challenge).filter(Challenge.id.notin_(completed_challenges_ids))
    all_challenges_query = all_challenges_query.join(RequiredLevel, Challenge.level_required == RequiredLevel.name)
    unlocked_challenges = all_challenges_query.filter(RequiredLevel.min_points <= user_min_points).all()
    locked_challenges = all_challenges_query.filter(RequiredLevel.min_points > user_min_points).all()
    return render_template('challenges.html', unlocked_challenges=unlocked_challenges, locked_challenges=locked_challenges, form=form)

@app.route('/challenges/hint/<int:challenge_id>', methods=['POST'])
@login_required
def get_challenge_hint(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if not challenge.hint:
        return jsonify({'error': 'Este desafio não possui dica.'}), 404
    
    if current_user.points < challenge.hint_cost:
        return jsonify({'error': 'Você não tem pontos suficientes para comprar esta dica.'}), 400
    
    current_user.points -= challenge.hint_cost
    db.session.commit()
    
    return jsonify({'hint': challenge.hint, 'new_points': current_user.points})

@app.route('/challenges/submit/<int:challenge_id>', methods=['POST'])
@login_required
def submit_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('list_challenges'))
        
    submitted_answer = request.form.get('answer').strip()
    
    is_correct = False
    if challenge.challenge_type == 'code':
        is_correct = submitted_answer == challenge.expected_answer
    else:
        is_correct = submitted_answer.lower() == challenge.expected_answer.lower()

    if is_correct:
        existing_completion = UserChallenge.query.filter_by(user_id=current_user.id, challenge_id=challenge_id).first()
        if not existing_completion:
            current_user.points += challenge.points_reward
            flash_message = f'Parabéns! Completou o desafio "{challenge.title}" e ganhou {challenge.points_reward} pontos!'
            
            today_challenge_entry = DailyChallenge.query.filter_by(day=date.today()).first()
            if today_challenge_entry and today_challenge_entry.challenge_id == challenge.id:
                current_user.points += today_challenge_entry.bonus_points
                flash_message += f' Você ganhou {today_challenge_entry.bonus_points} pontos de bônus por completar o desafio do dia!'
            
            completion = UserChallenge(user_id=current_user.id, challenge_id=challenge_id)
            db.session.add(completion)

            # Lógica do Evento Global (World Boss) - já implementada
            active_event = GlobalEvent.query.filter(
                GlobalEvent.is_active == True,
                GlobalEvent.start_date <= datetime.utcnow(),
                GlobalEvent.end_date >= datetime.utcnow(),
                GlobalEvent.current_hp > 0
            ).first()

            if active_event:
                damage = challenge.points_reward
                active_event.current_hp = max(0, active_event.current_hp - damage)
                contribution = GlobalEventContribution.query.filter_by(event_id=active_event.id, user_id=current_user.id).first()
                if contribution:
                    contribution.contribution_points += damage
                else:
                    contribution = GlobalEventContribution(event_id=active_event.id, user_id=current_user.id, contribution_points=damage)
                    db.session.add(contribution)
                flash(f'Você causou {damage} de dano ao Boss Global!', 'success')
                if active_event.current_hp == 0:
                    flash(f'O Boss Global "{active_event.name}" foi derrotado!', 'success')

            # ### NOVO: LÓGICA DA BATALHA DE EQUIPAS ###
            if current_user.team:
                active_battles = TeamBattle.query.filter(
                    (TeamBattle.challenging_team_id == current_user.team_id) | (TeamBattle.challenged_team_id == current_user.team_id),
                    TeamBattle.status == 'active'
                ).all()

                for battle in active_battles:
                    battle_challenge = TeamBattleChallenge.query.filter_by(battle_id=battle.id, challenge_id=challenge_id).first()
                    # Se o desafio faz parte desta batalha e ainda não foi completado por nenhuma equipa na batalha
                    if battle_challenge and not battle_challenge.completed_by_team_id:
                        battle_challenge.completed_by_team_id = current_user.team_id
                        battle_challenge.completed_at = datetime.utcnow()
                        flash(f'A sua equipa marcou pontos na batalha contra "{battle.challenged_team.name if battle.challenging_team_id == current_user.team_id else battle.challenging_team.name}"!', 'info')

            # ### FIM DA LÓGICA DA BATALHA ###

            check_and_complete_paths(current_user, challenge_id)
            update_user_level(current_user)
            db.session.commit()
            check_and_award_achievements(current_user)
            db.session.commit()
            flash(flash_message, 'success')
        else:
            flash('Você já completou este desafio.', 'info')
    else:
        flash('Resposta incorreta. Tente novamente!', 'error')
        
    return redirect(url_for('list_challenges'))

@app.route('/teams', methods=['GET', 'POST'])
@login_required
def teams_list():
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação.', 'error')
            return redirect(url_for('teams_list'))
            
        if current_user.team_id:
            flash('Você já pertence a uma equipe. Saia da sua equipe atual para criar uma nova.', 'error')
            return redirect(url_for('teams_list'))
        team_name = request.form.get('team_name')
        if Team.query.filter_by(name=team_name).first():
            flash('Já existe uma equipe com este nome.', 'error')
        else:
            new_team = Team(name=team_name, owner_id=current_user.id)
            db.session.add(new_team)
            db.session.commit()
            current_user.team = new_team
            db.session.commit()
            flash(f'Equipe "{team_name}" criada com sucesso!', 'success')
        return redirect(url_for('teams_list'))
            
    all_teams = Team.query.all()
    
    # Adicionado: Buscar batalhas ativas para o utilizador atual
    active_battles = []
    if current_user.team:
        active_battles = TeamBattle.query.filter(
            (TeamBattle.challenging_team_id == current_user.team_id) | (TeamBattle.challenged_team_id == current_user.team_id),
            TeamBattle.status == 'active'
        ).all()

    return render_template('teams.html', teams=all_teams, form=form, active_battles=active_battles)


@app.route('/team/<int:team_id>')
@login_required
def view_team(team_id):
    team = Team.query.get_or_404(team_id)
    team_challenges = Challenge.query.filter_by(is_team_challenge=True).all()
    return render_template('view_team.html', team=team, team_challenges=team_challenges)

@app.route('/teams/join/<int:team_id>', methods=['POST'])
@login_required
def join_team(team_id):
    if current_user.team_id:
        flash('Você já pertence a uma equipe.', 'error')
        return redirect(url_for('teams_list'))
    team_to_join = Team.query.get_or_404(team_id)
    current_user.team = team_to_join
    db.session.commit()
    check_and_award_achievements(current_user)
    db.session.commit()
    flash(f'Você entrou na equipe "{team_to_join.name}"!', 'success')
    return redirect(url_for('teams_list'))

@app.route('/teams/leave', methods=['POST'])
@login_required
def leave_team():
    if not current_user.team_id:
        flash('Você não pertence a nenhuma equipe.', 'error')
        return redirect(url_for('teams_list'))
    team = current_user.team
    if team.owner_id == current_user.id:
        flash('Você é o dono da equipe e não pode sair. Considere transferir a posse ou dissolver a equipe.', 'warning')
        return redirect(url_for('teams_list'))
    current_user.team_id = None
    db.session.commit()
    flash(f'Você saiu da equipe "{team.name}".', 'success')
    return redirect(url_for('teams_list'))

@app.route('/admin/delete_team/<int:team_id>', methods=['POST'])
@login_required
def admin_delete_team(team_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_teams'))
    team = Team.query.get_or_404(team_id)
    for member in team.members:
        member.team_id = None
    db.session.delete(team)
    db.session.commit()
    flash('Time dissolvido com sucesso!', 'success')
    return redirect(url_for('admin_teams'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    stats = {
        'total_users': User.query.count(),
        'total_faqs': FAQ.query.count(),
        'total_teams': Team.query.count(),
        'total_challenges_completed': UserChallenge.query.count(),
    }
    return render_template('admin_dashboard.html', stats=stats)

@app.route('/admin/teams', methods=['GET'])
@login_required
def admin_teams():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    all_teams = Team.query.all()
    return render_template('admin_teams.html', teams=all_teams, form=form)

@app.route('/admin/delete_level/<int:level_id>', methods=['POST'])
@login_required
def admin_delete_level(level_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_levels'))
    level = Level.query.get_or_404(level_id)
    db.session.delete(level)
    db.session.commit()
    flash('Nível excluído com sucesso!', 'success')
    return redirect(url_for('admin_levels'))

@app.route('/admin/levels', methods=['GET', 'POST'])
@login_required
def admin_levels():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('admin_levels'))
        action = request.form.get('action')
        if action == 'create_level':
            name = request.form['name']
            min_points = request.form['min_points']
            insignia_file = request.files.get('insignia_image')
            insignia_url = None
            if insignia_file:
                upload_result = cloudinary.uploader.upload(insignia_file)
                insignia_url = upload_result['secure_url']
            level = Level(name=name, min_points=min_points, insignia=insignia_url)
            db.session.add(level)
            db.session.commit()
            flash('Nível criado com sucesso!', 'success')
        elif action == 'import_levels':
            file = request.files['level_file']
            if file and file.filename.endswith('.json'):
                try:
                    data = json.load(file)
                    for level_data in data:
                        level = Level(
                            name=level_data['name'],
                            min_points=level_data['min_points'],
                            insignia=level_data.get('insignia')
                        )
                        db.session.add(level)
                    db.session.commit()
                    flash('Níveis importados com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao importar níveis: {str(e)}', 'error')
            else:
                flash('Por favor, envie um arquivo JSON válido.', 'error')
        return redirect(url_for('admin_levels'))
    levels = Level.query.all()
    return render_template('admin_levels.html', levels=levels, form=form)

@app.route('/admin/challenges', methods=['GET', 'POST'])
@login_required
def admin_challenges():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('admin_challenges'))
        action = request.form.get('action')
        if action == 'create_challenge':
            challenge = Challenge(
                title=request.form['title'],
                description=request.form['description'],
                level_required=request.form['level_required'],
                points_reward=request.form['points_reward'],
                challenge_type=request.form['challenge_type'],
                expected_answer=request.form['expected_answer'],
                expected_output=request.form.get('expected_output'),
                hint=request.form.get('hint'),
                hint_cost=request.form.get('hint_cost', 5),
                is_team_challenge='is_team_challenge' in request.form
            )
            db.session.add(challenge)
            db.session.commit()
            flash('Desafio criado com sucesso!', 'success')
        elif action == 'import_challenges':
            file = request.files.get('challenge_file')
            if file and file.filename.endswith('.json'):
                try:
                    data = json.load(file)
                    for challenge_data in data:
                        challenge = Challenge(
                            title=challenge_data['title'],
                            description=challenge_data['description'],
                            level_required=challenge_data['level_required'],
                            points_reward=challenge_data.get('points_reward', 10),
                            expected_answer=challenge_data['expected_answer'],
                            challenge_type=challenge_data.get('challenge_type', 'text'),
                            expected_output=challenge_data.get('expected_output'),
                            hint=challenge_data.get('hint'),
                            hint_cost=challenge_data.get('hint_cost', 5),
                            is_team_challenge=challenge_data.get('is_team_challenge', False)
                        )
                        db.session.add(challenge)
                    db.session.commit()
                    flash('Desafios importados com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao importar desafios: {str(e)}', 'error')
            else:
                flash('Por favor, envie um arquivo JSON válido.', 'error')
        return redirect(url_for('admin_challenges'))
    challenges = Challenge.query.all()
    levels = Level.query.all()
    faqs = FAQ.query.all()
    challenge_to_edit = None
    return render_template('admin_challenges.html', challenges=challenges, levels=levels, faqs=faqs, challenge_to_edit=challenge_to_edit, form=form)

@app.route('/admin/paths', methods=['GET', 'POST'])
@login_required
def admin_paths():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('admin_paths'))
        action = request.form.get('action')
        if action == 'create_path':
            new_path = LearningPath(
                name=request.form['name'],
                description=request.form.get('description'),
                reward_points=request.form.get('reward_points', 100, type=int),
                is_active='is_active' in request.form
            )
            db.session.add(new_path)
            db.session.commit()
            flash('Nova trilha de aprendizagem criada com sucesso!', 'success')
        elif action == 'add_challenge_to_path':
            path_id = request.form.get('path_id')
            challenge_id = request.form.get('challenge_id')
            step = request.form.get('step', type=int)
            path = LearningPath.query.get(path_id)
            if path and step is not None:
                existing = PathChallenge.query.filter_by(path_id=path_id, challenge_id=challenge_id).first()
                if not existing:
                    path_challenge = PathChallenge(path_id=path_id, challenge_id=challenge_id, step=step)
                    db.session.add(path_challenge)
                    db.session.commit()
                    flash('Desafio adicionado à trilha com sucesso!', 'success')
                else:
                    flash('Este desafio já faz parte desta trilha.', 'warning')
            else:
                flash('Falha ao adicionar desafio. Trilha ou passo inválido.', 'error')
        elif action == 'import_path':
            file = request.files.get('path_file')
            if file and file.filename.endswith('.json'):
                try:
                    data = json.load(file)
                    new_path = LearningPath(
                        name=data['name'],
                        description=data.get('description'),
                        reward_points=data.get('reward_points', 100),
                        is_active=data.get('is_active', True)
                    )
                    db.session.add(new_path)
                    db.session.flush()
                    for challenge_data in data.get('challenges', []):
                        challenge = Challenge.query.filter_by(title=challenge_data['title']).first()
                        if challenge:
                            path_challenge = PathChallenge(
                                path_id=new_path.id,
                                challenge_id=challenge.id,
                                step=challenge_data['step']
                            )
                            db.session.add(path_challenge)
                        else:
                            flash(f"Aviso: Desafio '{challenge_data['title']}' não encontrado e foi ignorado.", 'warning')
                    db.session.commit()
                    flash('Trilha de aprendizagem importada com sucesso!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Erro ao importar a trilha: {str(e)}', 'error')
            else:
                flash('Por favor, envie um arquivo JSON válido.', 'error')
        return redirect(url_for('admin_paths'))
    all_paths = LearningPath.query.all()
    all_challenges = Challenge.query.all()
    return render_template('admin_paths.html', paths=all_paths, challenges=all_challenges, form=form)

@app.route('/path/<int:path_id>')
@login_required
def view_path(path_id):
    """Mostra os detalhes de uma trilha de aprendizagem específica."""
    path = LearningPath.query.get_or_404(path_id)
    if not path.is_active and not current_user.is_admin:
        flash('Esta trilha de aprendizagem não está ativa no momento.', 'warning')
        return redirect(url_for('list_paths'))
    
    user_completed_challenges = {uc.challenge_id for uc in current_user.completed_challenges}
    
    return render_template('view_path.html', path=path, user_completed_challenges=user_completed_challenges)

@app.route('/admin/paths/edit/<int:path_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_path(path_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    path_to_edit = LearningPath.query.get_or_404(path_id)
    if request.method == 'POST':
        path_to_edit.name = request.form.get('name')
        path_to_edit.description = request.form.get('description')
        path_to_edit.reward_points = request.form.get('reward_points', type=int)
        path_to_edit.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Trilha de aprendizagem atualizada com sucesso!', 'success')
        return redirect(url_for('admin_paths'))
    return render_template('admin_edit_path.html', path=path_to_edit)

@app.route('/admin/paths/delete/<int:path_id>', methods=['POST'])
@login_required
def admin_delete_path(path_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    path_to_delete = LearningPath.query.get_or_404(path_id)
    db.session.delete(path_to_delete)
    db.session.commit()
    flash('Trilha de aprendizagem excluída com sucesso!', 'success')
    return redirect(url_for('admin_paths'))

@app.route('/admin/remove_challenge_from_path/<int:path_id>/<int:challenge_id>', methods=['POST'])
@login_required
def admin_remove_challenge_from_path(path_id, challenge_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_paths'))
    path_challenge = PathChallenge.query.filter_by(path_id=path_id, challenge_id=challenge_id).first_or_404()
    db.session.delete(path_challenge)
    db.session.commit()
    flash('Desafio removido da trilha com sucesso!', 'success')
    return redirect(url_for('admin_paths'))

@app.route('/paths')
@login_required
def list_paths():
    all_paths = LearningPath.query.filter_by(is_active=True).all()
    completed_challenges_ids = {uc.challenge_id for uc in current_user.completed_challenges}
    completed_paths_ids = {up.path_id for up in UserPathProgress.query.filter_by(user_id=current_user.id).all()}
    paths_with_progress = []
    for path in all_paths:
        total_steps = len(path.challenges)
        completed_steps = 0
        for pc in path.challenges:
            if pc.challenge_id in completed_challenges_ids:
                completed_steps += 1
        progress_percentage = (completed_steps / total_steps) * 100 if total_steps > 0 else 0
        paths_with_progress.append({
            'path': path,
            'progress': progress_percentage,
            'is_completed': path.id in completed_paths_ids
        })
    return render_template('paths.html', paths_data=paths_with_progress)

@app.route('/teams/manage')
@login_required
def manage_team():
    if not current_user.team or current_user.id != current_user.team.owner_id:
        flash('Você não é o dono de uma equipe para gerenciá-la.', 'error')
        return redirect(url_for('teams_list'))
    team = current_user.team
    return render_template('manage_team.html', team=team)

@app.route('/teams/kick/<int:user_id>', methods=['POST'])
@login_required
def kick_from_team(user_id):
    team = current_user.team
    if not team or current_user.id != team.owner_id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('teams_list'))
    user_to_kick = User.query.get_or_404(user_id)
    if user_to_kick in team.members:
        user_to_kick.team_id = None
        db.session.commit()
        flash(f'{user_to_kick.name} foi expulso da equipe.', 'success')
    else:
        flash('Este usuário não faz parte da sua equipe.', 'error')
    return redirect(url_for('manage_team'))

@app.route('/admin/achievements', methods=['GET', 'POST'])
@login_required
def admin_achievements():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('admin_achievements'))
        action = request.form.get('action')
        if action == 'create_achievement':
            name = request.form['name']
            description = request.form['description']
            trigger_type = request.form['trigger_type']
            trigger_value = request.form['trigger_value']
            icon_file = request.files.get('icon_image')
            icon_url = None
            if icon_file:
                upload_result = cloudinary.uploader.upload(icon_file)
                icon_url = upload_result['secure_url']
            achievement = Achievement(
                name=name,
                description=description,
                trigger_type=trigger_type,
                trigger_value=trigger_value,
                icon=icon_url
            )
            db.session.add(achievement)
            db.session.commit()
            flash('Conquista criada com sucesso!', 'success')
        elif action == 'import_achievements':
            file = request.files['achievement_file']
            if file and file.filename.endswith('.json'):
                try:
                    data = json.load(file)
                    for ach_data in data:
                        achievement = Achievement(
                            name=ach_data['name'],
                            description=ach_data.get('description'),
                            trigger_type=ach_data['trigger_type'],
                            trigger_value=ach_data['trigger_value'],
                            icon=ach_data.get('icon')
                        )
                        db.session.add(achievement)
                    db.session.commit()
                    flash('Conquistas importadas com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao importar conquistas: {str(e)}', 'error')
            else:
                flash('Por favor, envie um arquivo JSON válido.', 'error')
        return redirect(url_for('admin_achievements'))
    achievements = Achievement.query.all()
    return render_template('admin_achievements.html', achievements=achievements, form=form)

@app.route('/admin/daily_challenges')
@login_required
def admin_daily_challenges():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    history = DailyChallenge.query.order_by(DailyChallenge.day.desc()).all()
    return render_template('admin_daily_challenges.html', history=history)

@app.route('/admin/edit_achievement/<int:achievement_id>', methods=['POST'])
@login_required
def admin_edit_achievement(achievement_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_achievements'))
    achievement = Achievement.query.get_or_404(achievement_id)
    achievement.name = request.form['name']
    achievement.description = request.form['description']
    achievement.trigger_type = request.form['trigger_type']
    achievement.trigger_value = request.form['trigger_value']
    db.session.commit()
    flash('Conquista atualizada com sucesso!', 'success')
    return redirect(url_for('admin_achievements'))

@app.route('/admin/delete_achievement/<int:achievement_id>', methods=['POST'])
@login_required
def admin_delete_achievement(achievement_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_achievements'))
    achievement = Achievement.query.get_or_404(achievement_id)
    db.session.delete(achievement)
    db.session.commit()
    flash('Conquista excluída com sucesso!', 'success')
    return redirect(url_for('admin_achievements'))

@app.route('/admin/bossfights', methods=['GET', 'POST'])
@login_required
def admin_boss_fights():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('admin_boss_fights'))
        action = request.form.get('action')
        if action == 'create_boss':
            name = request.form['name']
            description = request.form['description']
            reward_points = request.form['reward_points']
            boss_image = request.files.get('boss_image')
            image_url = None
            if boss_image:
                upload_result = cloudinary.uploader.upload(boss_image)
                image_url = upload_result['secure_url']
            boss = BossFight(
                name=name,
                description=description,
                reward_points=reward_points,
                image_url=image_url
            )
            db.session.add(boss)
            db.session.commit()
            flash('Boss Fight criado com sucesso!', 'success')
        elif action == 'create_stage':
            boss_id = request.form['boss_id']
            name = request.form['name']
            order = request.form['order']
            stage = BossFightStage(boss_id=boss_id, name=name, order=order)
            db.session.add(stage)
            db.session.commit()
            flash('Etapa adicionada com sucesso!', 'success')
        elif action == 'create_step':
            stage_id = request.form['stage_id']
            description = request.form['description']
            expected_answer = request.form['expected_answer']
            step = BossFightStep(
                stage_id=stage_id,
                description=description,
                expected_answer=expected_answer
            )
            db.session.add(step)
            db.session.commit()
            flash('Tarefa adicionada com sucesso!', 'success')
        elif action == 'import_boss':
            file = request.files.get('boss_file')
            if file and file.filename.endswith('.json'):
                try:
                    data = json.load(file)
                    new_boss = BossFight(
                        name=data['name'],
                        description=data.get('description'),
                        reward_points=data.get('reward_points', 500),
                        is_active=data.get('is_active', False),
                        image_url=data.get('image_url')
                    )
                    db.session.add(new_boss)
                    db.session.flush()
                    for stage_data in data.get('stages', []):
                        new_stage = BossFightStage(
                            boss_fight_id=new_boss.id,
                            name=stage_data['name'],
                            order=stage_data['order']
                        )
                        db.session.add(new_stage)
                        db.session.flush()
                        for step_data in stage_data.get('steps', []):
                            new_step = BossFightStep(
                                stage_id=new_stage.id,
                                description=step_data['description'],
                                expected_answer=step_data['expected_answer']
                            )
                            db.session.add(new_step)
                    db.session.commit()
                    flash('Boss Fight importado com sucesso!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Erro ao importar Boss Fight: {str(e)}', 'error')
            else:
                flash('Por favor, envie um arquivo JSON válido.', 'error')
        return redirect(url_for('admin_boss_fights'))
    boss_fights = BossFight.query.all()
    return render_template('admin_boss_fights.html', boss_fights=boss_fights, form=form)

@app.route('/admin/edit_boss_fight/<int:boss_id>', methods=['POST'])
@login_required
def admin_edit_boss_fight(boss_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_boss_fights'))
    boss = BossFight.query.get_or_404(boss_id)
    boss.name = request.form['name']
    boss.description = request.form['description']
    boss.reward_points = request.form['reward_points']
    boss.is_active = 'is_active' in request.form
    db.session.commit()
    flash('Boss Fight atualizado com sucesso!', 'success')
    return redirect(url_for('admin_boss_fights'))
@app.route('/admin/delete_boss_fight/<int:boss_id>', methods=['POST'])
@login_required
def admin_delete_boss_fight(boss_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_boss_fights'))
    boss = BossFight.query.get_or_404(boss_id)
    db.session.delete(boss)
    db.session.commit()
    flash('Boss Fight excluído com sucesso!', 'success')
    return redirect(url_for('admin_boss_fights'))

@app.route('/admin/delete_boss_stage/<int:stage_id>', methods=['POST'])
@login_required
def admin_delete_boss_stage(stage_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_boss_fights'))
    stage = BossFightStage.query.get_or_404(stage_id)
    db.session.delete(stage)
    db.session.commit()
    flash('Etapa excluída com sucesso!', 'success')
    return redirect(url_for('admin_boss_fights'))

@app.route('/admin/delete_boss_step/<int:step_id>', methods=['POST'])
@login_required
def admin_delete_boss_step(step_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_boss_fights'))
    step = BossFightStep.query.get_or_404(step_id)
    db.session.delete(step)
    db.session.commit()
    flash('Tarefa excluída com sucesso!', 'success')
    return redirect(url_for('admin_boss_fights'))

@app.route('/bossfights')
@login_required
def list_boss_fights():
    if not current_user.team:
        flash('Você precisa estar em uma equipe para participar de Boss Fights!', 'warning')
        return redirect(url_for('teams_list'))
    all_bosses = BossFight.query.filter_by(is_active=True).all()
    return render_template('boss_fights_list_user.html', bosses=all_bosses)

@app.route('/bossfight/<int:boss_id>')
@login_required
def view_boss_fight(boss_id):
    if not current_user.team:
        flash('Você precisa estar em uma equipe para acessar Boss Fights.', 'warning')
        return redirect(url_for('list_boss_fights'))
    boss = BossFight.query.get_or_404(boss_id)
    team_progress = TeamBossProgress.query.filter_by(team_id=current_user.team_id).all()
    completed_step_ids = {progress.step_id for progress in team_progress}
    return render_template('view_boss_fight.html', boss=boss, completed_step_ids=completed_step_ids, team_progress=team_progress)

@app.route('/bossfight/submit/<int:step_id>', methods=['POST'])
@login_required
def submit_boss_step(step_id):
    if not current_user.team:
        flash('Você precisa estar em uma equipe para acessar Boss Fights.', 'warning')
        return redirect(url_for('list_boss_fights'))
    step = BossFightStep.query.get_or_404(step_id)
    boss = step.stage.boss_fight
    submitted_answer = request.form.get('answer', '').strip()
    if submitted_answer.lower() == step.expected_answer.lower():
        if not TeamBossProgress.query.filter_by(team_id=current_user.team_id, step_id=step_id).first():
            progress = TeamBossProgress(
                team_id=current_user.team_id,
                step_id=step_id,
                completed_by_user_id=current_user.id
            )
            db.session.add(progress)
            db.session.commit()
            flash(f'Parabéns! Você completou a tarefa "{step.description}" para sua equipe!', 'success')
            check_boss_fight_completion(current_user.team_id, boss.id)
        else:
            flash('Esta tarefa já foi completada pela sua equipe.', 'info')
    else:
        flash('Resposta incorreta. Tente novamente!', 'error')
    return redirect(url_for('view_boss_fight', boss_id=boss.id))

@app.route('/admin/edit_challenge/<int:challenge_id>', methods=['POST'])
@login_required
def admin_edit_challenge(challenge_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_challenges'))
    challenge = Challenge.query.get_or_404(challenge_id)
    challenge.title = request.form['title']
    challenge.level_required = request.form['level_required']
    challenge.description=request.form['description']
    challenge.points_reward=request.form['points_reward']
    challenge.expected_answer=request.form['expected_answer']
    db.session.commit()
    flash('Desafio atualizado com sucesso!', 'success')
    return redirect(url_for('admin_challenges'))

@app.route('/admin/delete_challenge/<int:challenge_id>', methods=['POST'])
@login_required
def admin_delete_challenge(challenge_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_challenges'))

    challenge = Challenge.query.get_or_404(challenge_id)

    # Apagar todas as dependências antes de apagar o desafio
    UserChallenge.query.filter_by(challenge_id=challenge.id).delete()
    PathChallenge.query.filter_by(challenge_id=challenge.id).delete()
    DailyChallenge.query.filter_by(challenge_id=challenge.id).delete()

    db.session.delete(challenge)
    db.session.commit()
    
    flash('Desafio e todas as suas referências foram excluídos com sucesso!', 'success')
    return redirect(url_for('admin_challenges'))

@app.route('/admin/hunts', methods=['GET', 'POST'])
@login_required
def admin_hunts():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            flash('Erro de validação CSRF.', 'error')
            return redirect(url_for('admin_hunts'))

        action = request.form.get('action')
        
        if action == 'create_hunt':
            name = request.form['name']
            description = request.form['description']
            reward_points = request.form['reward_points']
            is_active = 'is_active' in request.form
            
            if is_active:
                ScavengerHunt.query.update({ScavengerHunt.is_active: False})

            new_hunt = ScavengerHunt(name=name, description=description, reward_points=reward_points, is_active=is_active)
            db.session.add(new_hunt)
            db.session.commit()
            flash('Evento de Caça ao Tesouro criado com sucesso!', 'success')

        elif action == 'create_step':
            # ... (Lógica para criar um passo, como já tinha)
            hunt_id = request.form['hunt_id']
            step_number = request.form['step_number']
            clue_text = request.form['clue_text']
            target_type = request.form['target_type']
            target_identifier = request.form['target_identifier']
            hidden_clue = request.form['hidden_clue']
            new_step = ScavengerHuntStep(
                hunt_id=hunt_id,
                step_number=step_number,
                clue_text=clue_text,
                target_type=target_type,
                target_identifier=target_identifier,
                hidden_clue=hidden_clue
            )
            db.session.add(new_step)
            db.session.commit()
            flash('Passo adicionado com sucesso!', 'success')
            
        return redirect(url_for('admin_hunts'))

    hunts = ScavengerHunt.query.order_by(ScavengerHunt.id.desc()).all()
    return render_template('admin_hunts.html', hunts=hunts, form=form)


@app.route('/admin/hunts/edit/<int:hunt_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_hunt(hunt_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    hunt = ScavengerHunt.query.get_or_404(hunt_id)
    form = BaseForm()
    
    if form.validate_on_submit():
        hunt.name = request.form['name']
        hunt.description = request.form['description']
        hunt.reward_points = request.form['reward_points']
        is_active = 'is_active' in request.form
        
        if is_active and not hunt.is_active:
            ScavengerHunt.query.filter(ScavengerHunt.id != hunt.id).update({ScavengerHunt.is_active: False})
        
        hunt.is_active = is_active
        db.session.commit()
        flash('Evento atualizado com sucesso!', 'success')
        return redirect(url_for('admin_hunts'))

    return render_template('admin_edit_hunt.html', hunt=hunt, form=form)


@app.route('/admin/hunts/delete/<int:hunt_id>', methods=['POST'])
@login_required
def delete_hunt(hunt_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    form = BaseForm()
    if form.validate_on_submit():
        hunt_to_delete = ScavengerHunt.query.get_or_404(hunt_id)
        UserHuntProgress.query.filter_by(hunt_id=hunt_to_delete.id).delete()
        db.session.delete(hunt_to_delete)
        db.session.commit()
        flash(f'O evento "{hunt_to_delete.name}" foi apagado.', 'success')
    return redirect(url_for('admin_hunts'))


@app.route('/admin/hunts/step/delete/<int:step_id>', methods=['POST'])
@login_required
def delete_hunt_step(step_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    form = BaseForm()
    if form.validate_on_submit():
        step_to_delete = ScavengerHuntStep.query.get_or_404(step_id)
        db.session.delete(step_to_delete)
        db.session.commit()
        flash(f'O passo {step_to_delete.step_number} foi apagado com sucesso.', 'success')
    return redirect(url_for('admin_hunts'))

@app.route('/admin/events', methods=['GET', 'POST'])
@login_required
def admin_events():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    form = BaseForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            return redirect(url_for('admin_events'))

        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M')
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M')
        total_hp = int(request.form['total_hp'])

        new_event = GlobalEvent(
            name=request.form['name'],
            description=request.form['description'],
            total_hp=total_hp,
            current_hp=total_hp, # Começa com a vida cheia
            start_date=start_date,
            end_date=end_date,
            reward_points_on_win=int(request.form['reward_points_on_win']),
            is_active='is_active' in request.form
        )
        db.session.add(new_event)
        db.session.commit()
        flash('Evento Global criado com sucesso!', 'success')
        return redirect(url_for('admin_events'))

    events = GlobalEvent.query.order_by(GlobalEvent.start_date.desc()).all()
    return render_template('admin_events.html', events=events, form=form, now=datetime.utcnow())

@app.route('/admin/events/edit/<int:event_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_event(event_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    event = GlobalEvent.query.get_or_404(event_id)
    form = BaseForm()
    
    if request.method == 'POST':
        if not form.validate_on_submit():
            return redirect(url_for('admin_edit_event', event_id=event.id))
            
        event.name = request.form['name']
        event.description = request.form['description']
        event.total_hp = int(request.form['total_hp'])
        event.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M')
        event.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M')
        event.reward_points_on_win = int(request.form['reward_points_on_win'])
        event.is_active = 'is_active' in request.form
        
        # Opcional: Resetar a vida se o total for alterado
        # event.current_hp = event.total_hp
        
        db.session.commit()
        flash('Evento Global atualizado com sucesso!', 'success')
        return redirect(url_for('admin_events'))

    return render_template('admin_edit_event.html', event=event, form=form)

@app.route('/admin/events/delete/<int:event_id>', methods=['POST'])
@login_required
def admin_delete_event(event_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    form = BaseForm()
    if not form.validate_on_submit():
        return redirect(url_for('admin_events'))

    event = GlobalEvent.query.get_or_404(event_id)
    db.session.delete(event) # As contribuições serão apagadas em cascata
    db.session.commit()
    flash('Evento Global apagado com sucesso.', 'success')
    return redirect(url_for('admin_events'))

# Adicionar em app.py

@app.route('/teams/challenge/<int:team_id>', methods=['POST'])
@login_required
def challenge_team(team_id):
    challenger_team = current_user.team
    challenged_team = Team.query.get_or_404(team_id)
    form = BaseForm()

    if not form.validate_on_submit():
        flash('Erro de validação.', 'error')
        return redirect(url_for('teams_list'))

    if not challenger_team:
        flash('Você precisa de estar numa equipa para desafiar outras.', 'error')
        return redirect(url_for('teams_list'))
    if challenger_team.owner_id != current_user.id:
        flash('Apenas o líder da equipa pode iniciar batalhas.', 'error')
        return redirect(url_for('teams_list'))
    if challenger_team.id == challenged_team.id:
        flash('Você não pode desafiar a sua própria equipa.', 'error')
        return redirect(url_for('teams_list'))

    existing_battle = TeamBattle.query.filter(
        ((TeamBattle.challenging_team_id == challenger_team.id) & (TeamBattle.challenged_team_id == challenged_team.id) |
        (TeamBattle.challenging_team_id == challenged_team.id) & (TeamBattle.challenged_team_id == challenger_team.id)) &
        (TeamBattle.status == 'active')
    ).first()

    if existing_battle:
        flash('Já existe uma batalha ativa entre estas duas equipas.', 'warning')
        return redirect(url_for('teams_list'))

    num_challenges = 5
    available_challenges = Challenge.query.filter_by(is_team_challenge=False).all()
    if len(available_challenges) < num_challenges:
        flash('Não há desafios suficientes na plataforma para iniciar uma batalha.', 'error')
        return redirect(url_for('teams_list'))
    
    selected_challenges = random.sample(available_challenges, num_challenges)
    
    end_time = datetime.utcnow() + timedelta(days=2)
    new_battle = TeamBattle(
        challenging_team_id=challenger_team.id,
        challenged_team_id=challenged_team.id,
        end_time=end_time,
        status='active'
    )
    db.session.add(new_battle)
    db.session.flush()

    for challenge in selected_challenges:
        battle_challenge = TeamBattleChallenge(battle_id=new_battle.id, challenge_id=challenge.id)
        db.session.add(battle_challenge)
    
    db.session.commit()

    flash(f'Desafio enviado para a equipa "{challenged_team.name}"! A batalha termina em 48 horas.', 'success')
    # Alterado para redirecionar para a página da batalha
    return redirect(url_for('view_battle', battle_id=new_battle.id))

@app.route('/admin/battles')
@login_required
def admin_battles():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    battles = TeamBattle.query.order_by(TeamBattle.start_time.desc()).all()
    return render_template('admin_battles.html', battles=battles, form=BaseForm())

@app.route('/admin/battles/delete/<int:battle_id>', methods=['POST'])
@login_required
def admin_delete_battle(battle_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('admin_battles'))
    
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_battles'))

    battle = TeamBattle.query.get_or_404(battle_id)
    
    # Apagar os desafios ligados a esta batalha PRIMEIRO
    TeamBattleChallenge.query.filter_by(battle_id=battle.id).delete()

    db.session.delete(battle)
    db.session.commit()
    flash(f'A batalha entre "{battle.challenging_team.name}" e "{battle.challenged_team.name}" foi apagada.', 'success')
    return redirect(url_for('admin_battles'))



@app.route('/battle/<int:battle_id>')
@login_required
def view_battle(battle_id):
    battle = TeamBattle.query.get_or_404(battle_id)
    if current_user.team_id not in [battle.challenging_team_id, battle.challenged_team_id]:
        flash('A sua equipa não faz parte desta batalha.', 'error')
        return redirect(url_for('teams_list'))
    
    return render_template('view_battle.html', battle=battle)

# Adicione esta rota ao seu ficheiro app.py

@app.route('/admin/battles/finalize', methods=['POST'])
@login_required
def trigger_finalize_battles():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    # Adicione o form para validação de CSRF
    form = BaseForm()
    if not form.validate_on_submit():
        flash('Erro de validação CSRF.', 'error')
        return redirect(url_for('admin_battles'))
    
    count = finalize_ended_battles()
    if count > 0:
        flash(f'{count} batalha(s) foram finalizadas e as recompensas distribuídas.', 'success')
    else:
        flash('Nenhuma batalha ativa precisava de ser finalizada.', 'info')
        
    return redirect(url_for('admin_battles'))

# Adicione esta nova rota ao seu ficheiro app.py, junto com as outras rotas de admin.

@app.route('/admin/import', methods=['GET', 'POST'])
@login_required
def admin_import_content():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    form = BaseForm()
    if form.validate_on_submit():
        file = request.files.get('content_file')
        if not file or not file.filename.endswith('.json'):
            flash('Por favor, envie um ficheiro JSON válido.', 'error')
            return redirect(url_for('admin_import_content'))
        
        try:
            content = json.load(file.stream)
            counts = {'faqs': 0, 'desafios': 0, 'trilhas': 0, 'boss_fights': 0, 'caca_tesouros': 0, 'eventos_globais': 0}

            # --- Processar FAQs ---
            if 'import_faqs' in request.form and 'faqs' in content:
                existing_questions = {f.question for f in FAQ.query.all()}
                for faq_data in content['faqs']:
                    if faq_data['question'] not in existing_questions:
                        category = Category.query.filter_by(name=faq_data['category']).first()
                        if not category:
                            category = Category(name=faq_data['category'])
                            db.session.add(category)
                            db.session.flush()
                        
                        new_faq = FAQ(category_id=category.id, **{k: v for k, v in faq_data.items() if k != 'category'})
                        db.session.add(new_faq)
                        counts['faqs'] += 1

            # --- Processar Desafios ---
            if 'import_desafios' in request.form and 'desafios' in content:
                existing_titles = {c.title for c in Challenge.query.all()}
                for challenge_data in content['desafios']:
                    if challenge_data['title'] not in existing_titles:
                        new_challenge = Challenge(**challenge_data)
                        db.session.add(new_challenge)
                        counts['desafios'] += 1

            # --- Processar Trilhas ---
            if 'import_trilhas' in request.form and 'trilhas' in content:
                existing_names = {p.name for p in LearningPath.query.all()}
                for path_data in content['trilhas']:
                    if path_data['name'] not in existing_names:
                        challenges_in_path_data = path_data.pop('challenges', [])
                        new_path = LearningPath(**path_data)
                        db.session.add(new_path)
                        db.session.flush()
                        for c_data in challenges_in_path_data:
                            challenge = Challenge.query.filter_by(title=c_data['title']).first()
                            if challenge:
                                pc = PathChallenge(path_id=new_path.id, challenge_id=challenge.id, step=c_data['step'])
                                db.session.add(pc)
                        counts['trilhas'] += 1

            # --- Processar Boss Fights ---
            if 'import_boss_fights' in request.form and 'boss_fights' in content:
                existing_names = {b.name for b in BossFight.query.all()}
                for boss_data in content['boss_fights']:
                    if boss_data['name'] not in existing_names:
                        stages_data = boss_data.pop('stages', [])
                        new_boss = BossFight(**boss_data)
                        db.session.add(new_boss)
                        db.session.flush()
                        for s_data in stages_data:
                            steps_data = s_data.pop('steps', [])
                            new_stage = BossFightStage(boss_fight_id=new_boss.id, **s_data)
                            db.session.add(new_stage)
                            db.session.flush()
                            for step_data in steps_data:
                                new_step = BossFightStep(stage_id=new_stage.id, **step_data)
                                db.session.add(new_step)
                        counts['boss_fights'] += 1

            # --- Processar Caça ao Tesouro ---
            if 'import_caca_tesouros' in request.form and 'caca_tesouros' in content:
                existing_names = {h.name for h in ScavengerHunt.query.all()}
                for hunt_data in content['caca_tesouros']:
                    if hunt_data['name'] not in existing_names:
                        steps_data = hunt_data.pop('steps', [])
                        new_hunt = ScavengerHunt(**hunt_data)
                        db.session.add(new_hunt)
                        db.session.flush()
                        for step_data in steps_data:
                            new_step = ScavengerHuntStep(hunt_id=new_hunt.id, **step_data)
                            db.session.add(new_step)
                        counts['caca_tesouros'] += 1
            
            # --- Processar Eventos Globais ---
            if 'import_eventos_globais' in request.form and 'eventos_globais' in content:
                existing_names = {e.name for e in GlobalEvent.query.all()}
                for event_data in content['eventos_globais']:
                    if event_data['name'] not in existing_names:
                        event_data['start_date'] = datetime.fromisoformat(event_data['start_date'])
                        event_data['end_date'] = datetime.fromisoformat(event_data['end_date'])
                        event_data['current_hp'] = event_data['total_hp']
                        
                        new_event = GlobalEvent(**event_data)
                        db.session.add(new_event)
                        counts['eventos_globais'] += 1

            db.session.commit()
            flash(f"Importação concluída! Adicionados: {counts['faqs']} FAQs, {counts['desafios']} Desafios, "
                f"{counts['trilhas']} Trilhas, {counts['boss_fights']} Boss Fights, "
                f"{counts['caca_tesouros']} Caças ao Tesouro, {counts['eventos_globais']} Eventos Globais.", 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Ocorreu um erro durante a importação: {e}', 'error')
        
        return redirect(url_for('admin_import_content'))
    
    return render_template('admin_import.html', form=form)



# --- COMANDO CLI ---
@app.cli.command(name='create-admin')
@with_appcontext
@click.option('--name', required=True, help='O nome do administrador.')
@click.option('--email', required=True, help='O email do administrador.')
@click.option('--password', required=True, help='A senha do administrador.')
def create_admin(name, email, password):
    """Cria um usuário administrador."""
    if User.query.filter_by(email=email).first():
        print(f'Erro: O email {email} já está registrado.')
        return
    initial_level = Level.query.order_by(Level.min_points).first()
    if not initial_level:
        print('Erro: Nenhum nível inicial encontrado. Execute a inicialização do banco de dados primeiro.')
        return
    hashed_password = generate_password_hash(password)
    admin = User(
        name=name,
        email=email,
        password=hashed_password,
        is_admin=True,
        level_id=initial_level.id
    )
    db.session.add(admin)
    db.session.commit()
    print(f'Administrador {name} criado com sucesso!')

# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
with app.app_context():
    initialize_database()

# --- EXECUÇÃO DA APLICAÇÃO ---
if __name__ == '__main__':
    app.run(debug=True)

