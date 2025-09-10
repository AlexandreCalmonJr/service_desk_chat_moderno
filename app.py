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
import spacy
import spacy.cli
import click
from flask.cli import with_appcontext
from flask_caching import Cache
from sqlalchemy.orm import aliased
import cloudinary
import cloudinary.uploader
import cloudinary.api
from sqlalchemy import func
import random

app = Flask(__name__)

# --- CONFIGURAÇÕES DA APLICAÇÃO ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'uma-chave-secreta-padrao-para-desenvolvimento')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'  # Adicionado para corrigir erro em /admin/faq

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
try:
    nlp = spacy.load('pt_core_news_sm')
except OSError:
    print("Modelo pt_core_news_sm não encontrado. Fazendo download...")
    spacy.cli.download('pt_core_news_sm')
    nlp = spacy.load('pt_core_news_sm')

# --- MODELOS DA BASE DE DADOS ---
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
    day = db.Column(db.Date, unique=True, nullable=False, default=date.today)  # Corrigido para date.today
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
    return render_template('dashboard.html', daily_challenge=daily_challenge)

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'error')
        return redirect(url_for('index'))
    all_users = User.query.order_by(User.name).all()
    return render_template('admin_users.html', users=all_users)

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

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    user_to_modify = User.query.get_or_404(user_id)
    if user_to_modify.id == current_user.id:
        flash('Você não pode alterar sua própria permissão de administrador.', 'error')
        return redirect(url_for('admin_users'))
    user_to_modify.is_admin = not user_to_modify.is_admin
    db.session.commit()
    status = "administrador" if user_to_modify.is_admin else "usuário normal"
    flash(f'O usuário {user_to_modify.name} é agora um {status}.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/chat-page')
@login_required
def chat_page():
    session.pop('faq_selection', None)
    return render_template('chat.html')

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
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            next_page = request.args.get('next')
            flash('Login realizado com sucesso!', 'success')
            return redirect(next_page or url_for('index'))
        flash('Email ou senha inválidos.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(email=email).first():
            flash('Email já registrado.', 'error')
            return redirect(url_for('register'))
        initial_level = Level.query.order_by(Level.min_points).first()
        if not initial_level:
            flash('Erro de sistema: Nenhum nível inicial encontrado. Contate o administrador.', 'error')
            return redirect(url_for('register'))
        user = User(name=name, email=email, password=password, is_admin=False, level_id=initial_level.id)
        db.session.add(user)
        db.session.commit()
        flash('Registro concluído! Faça login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu com sucesso.', 'success')
    return redirect(url_for('login'))

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    mensagem = data.get('mensagem', '').strip()
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

@app.route('/admin/faq', methods=['GET', 'POST'])
@login_required
def admin_faq():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem gerenciar FAQs.', 'error')
        return redirect(url_for('index'))
    categories = Category.query.all()
    if request.method == 'POST':
        if 'add_question' in request.form:
            category_id = request.form['category']
            question = request.form['question']
            answer = request.form['answer']
            image_url = request.form.get('image_url')
            video_url = request.form.get('video_url')
            file = request.files.get('file')
            file_name = file.filename if file else None
            file_data = file.read() if file else None
            if category_id and question and answer:
                faq = FAQ(category_id=category_id, question=question, answer=answer, image_url=image_url, video_url=video_url, file_name=file_name, file_data=file_data)
                db.session.add(faq)
                db.session.commit()
                flash('FAQ adicionada com sucesso!', 'success')
            else:
                flash('Preencha todos os campos obrigatórios.', 'error')
        elif 'import_faqs' in request.form:
            file = request.files['faq_file']
            if file and file.filename.endswith(('.json', '.csv', '.pdf')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)  # Garante que o diretório existe
                file.save(file_path)
                try:
                    if file.filename.endswith('.json'):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if not isinstance(data, list):
                                flash('Arquivo JSON deve conter uma lista de FAQs.', 'error')
                                os.remove(file_path)
                                return redirect(url_for('admin_faq'))
                            for item in data:
                                category_name = item.get('category')
                                question = item.get('question')
                                answer = item.get('answer', '')
                                image_url = item.get('image_url')
                                video_url = item.get('video_url')
                                file_name = item.get('file_name')
                                file_data = item.get('file_data', None)
                                if not category_name or not question:
                                    flash('Cada FAQ no JSON deve ter "category" e "question".', 'error')
                                    continue
                                category = Category.query.filter_by(name=category_name).first()
                                if not category:
                                    category = Category(name=category_name)
                                    db.session.add(category)
                                    db.session.commit()
                                faq = FAQ(category_id=category.id, question=question, answer=answer, image_url=image_url, video_url=video_url, file_name=file_name, file_data=file_data)
                                db.session.add(faq)
                    elif file.filename.endswith('.csv'):
                        category_id = request.form['category_import']
                        with open(file_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                faq = FAQ(
                                    category_id=category_id,
                                    question=row.get('question'),
                                    answer=row.get('answer', ''),
                                    image_url=row.get('image_url'),
                                    video_url=row.get('video_url'),
                                    file_name=row.get('file_name'),
                                    file_data=row.get('file_data')
                                )
                                db.session.add(faq)
                    elif file.filename.endswith('.pdf'):
                        category_id = request.form['category_import']
                        faqs_extracted = extract_faqs_from_pdf(file_path)
                        for faq in faqs_extracted:
                            new_faq = FAQ(category_id=category_id, question=faq['question'], answer=faq['answer'], image_url=None, video_url=None, file_name=None, file_data=None)
                            db.session.add(new_faq)
                    db.session.commit()
                    flash('FAQs importadas com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                finally:
                    os.remove(file_path)
            else:
                flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
    return render_template('admin_faq.html', categories=categories)

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
    completed_challenges_ids = [uc.challenge_id for uc in current_user.completed_challenges]
    user_min_points = current_user.level.min_points
    RequiredLevel = aliased(Level)
    all_challenges_query = db.session.query(Challenge).filter(Challenge.id.notin_(completed_challenges_ids))
    all_challenges_query = all_challenges_query.join(RequiredLevel, Challenge.level_required == RequiredLevel.name)
    unlocked_challenges = all_challenges_query.filter(RequiredLevel.min_points <= user_min_points).all()
    locked_challenges = all_challenges_query.filter(RequiredLevel.min_points > user_min_points).all()
    return render_template('challenges.html', unlocked_challenges=unlocked_challenges, locked_challenges=locked_challenges)

@app.route('/challenges/submit/<int:challenge_id>', methods=['POST'])
@login_required
def submit_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    submitted_answer = request.form.get('answer').strip()
    if submitted_answer.lower() == challenge.expected_answer.lower():
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
    if request.method == 'POST':
        if current_user.team_id:
            flash('Você já pertence a uma equipe. Saia da sua equipe atual para criar uma nova.', 'error')
            return redirect(url_for('teams_list'))
        team_name = request.form.get('team_name')
        if Team.query.filter_by(name=team_name).first():
            flash('Já existe uma equipe com este nome.', 'error')
        else:
            new_team = Team(name=team_name, owner_id=current_user.id)
            db.session.add(new_team)
            current_user.team = new_team
            db.session.commit()
            flash(f'Equipe "{team_name}" criada com sucesso!', 'success')
            return redirect(url_for('teams_list'))
    all_teams = Team.query.all()
    team_challenges = Challenge.query.filter_by(is_team_challenge=True).all()
    return render_template('teams.html', teams=all_teams, team_challenges=team_challenges)

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

@app.route('/admin/teams/delete/<int:team_id>', methods=['POST'])
@login_required
def admin_delete_team(team_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    team_to_delete = Team.query.get_or_404(team_id)
    for member in team_to_delete.members:
        member.team_id = None
    db.session.delete(team_to_delete)
    db.session.commit()
    flash(f'A equipe "{team_to_delete.name}" foi dissolvida com sucesso!', 'success')
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

@app.route('/admin/teams')
@login_required
def admin_teams():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    all_teams = Team.query.all()
    return render_template('admin_teams.html', teams=all_teams)

@app.route('/admin/levels/delete/<int:level_id>', methods=['POST'])
@login_required
def admin_delete_level(level_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    level_to_delete = Level.query.get_or_404(level_id)
    if level_to_delete.users:
        flash(f'Não é possível excluir o nível "{level_to_delete.name}", pois existem usuários associados a ele.', 'error')
        return redirect(url_for('admin_levels'))
    db.session.delete(level_to_delete)
    db.session.commit()
    flash(f'O nível "{level_to_delete.name}" foi excluído com sucesso!', 'success')
    return redirect(url_for('admin_levels'))

@app.route('/admin/levels', methods=['GET', 'POST'])
@login_required
def admin_levels():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form.get('name')
        min_points = request.form.get('min_points')
        file = request.files.get('insignia_image')
        existing_level_name = Level.query.filter_by(name=name).first()
        if existing_level_name:
            flash(f'Erro: Já existe um nível com o nome "{name}".', 'error')
            return redirect(url_for('admin_levels'))
        existing_level_points = Level.query.filter_by(min_points=int(min_points)).first()
        if existing_level_points:
            flash(f'Erro: Já existe um nível com {min_points} pontos mínimos (Nível: {existing_level_points.name}).', 'error')
            return redirect(url_for('admin_levels'))
        insignia_url = None
        if file and file.filename:
            try:
                upload_result = cloudinary.uploader.upload(file)
                insignia_url = upload_result['secure_url']
            except Exception as e:
                flash(f'Erro ao fazer upload da imagem: {e}', 'error')
                return redirect(url_for('admin_levels'))
        if name and min_points:
            new_level = Level(name=name, min_points=int(min_points), insignia=insignia_url)
            db.session.add(new_level)
            db.session.commit()
            flash('Nível adicionado com sucesso!', 'success')
        else:
            flash('Nome e pontos mínimos são obrigatórios.', 'error')
        return redirect(url_for('admin_levels'))
    levels = Level.query.order_by(Level.min_points).all()
    return render_template('admin_levels.html', levels=levels)

@app.route('/admin/challenges', methods=['GET', 'POST'])
@login_required
def admin_challenges():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    challenge_to_edit = None
    edit_id = request.args.get('edit_id', type=int)
    if edit_id:
        challenge_to_edit = Challenge.query.get_or_404(edit_id)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_challenge':
            title = request.form.get('title')
            description = request.form.get('description')
            level_required = request.form.get('level_required')
            points_reward = request.form.get('points_reward')
            expected_answer = request.form.get('expected_answer')
            is_team_challenge = request.form.get('is_team_challenge') == 'on'
            hint = request.form.get('hint')
            hint_cost = request.form.get('hint_cost', 5, type=int)
            if title and description and level_required and points_reward and expected_answer:
                new_challenge = Challenge(
                    title=title,
                    description=description,
                    level_required=level_required,
                    points_reward=int(points_reward),
                    expected_answer=expected_answer,
                    is_team_challenge=is_team_challenge,
                    hint=hint,
                    hint_cost=hint_cost
                )
                db.session.add(new_challenge)
                db.session.commit()
                flash('Desafio adicionado com sucesso!', 'success')
            else:
                flash('Todos os campos obrigatórios devem ser preenchidos.', 'error')
        elif action == 'import_challenges':
            file = request.files.get('challenge_file')
            if not file or not file.filename.endswith('.json'):
                flash('Por favor, envie um arquivo .json válido.', 'error')
                return redirect(url_for('admin_challenges'))
            try:
                data = json.load(file.stream)
                count = 0
                for item in data:
                    if item.get('title') and not Challenge.query.filter_by(title=item.get('title')).first():
                        new_challenge = Challenge(
                            title=item.get('title'),
                            description=item.get('description'),
                            expected_answer=item.get('expected_answer'),
                            points_reward=item.get('points_reward', 10),
                            level_required=item.get('level_required', 'Iniciante'),
                            is_team_challenge=item.get('is_team_challenge', False),
                            hint=item.get('hint'),
                            hint_cost=item.get('hint_cost', 5)
                        )
                        db.session.add(new_challenge)
                        count += 1
                db.session.commit()
                flash(f'{count} novos desafios importados com sucesso!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Ocorreu um erro ao processar o arquivo JSON: {e}', 'error')
        return redirect(url_for('admin_challenges'))
    all_levels = Level.query.order_by(Level.min_points).all()
    all_faqs = FAQ.query.order_by(FAQ.question).all()
    all_challenges = Challenge.query.order_by(Challenge.level_required).all()
    return render_template('admin_challenges.html', challenges=all_challenges, levels=all_levels, faqs=all_faqs, challenge_to_edit=challenge_to_edit)

@app.route('/admin/challenges/delete/<int:challenge_id>', methods=['POST'])
@login_required
def admin_delete_challenge(challenge_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    challenge_to_delete = Challenge.query.get_or_404(challenge_id)
    UserChallenge.query.filter_by(challenge_id=challenge_id).delete()
    PathChallenge.query.filter_by(challenge_id=challenge_id).delete()
    db.session.delete(challenge_to_delete)
    db.session.commit()
    flash(f'O desafio "{challenge_to_delete.title}" foi excluído com sucesso!', 'success')
    return redirect(url_for('admin_challenges'))

@app.route('/challenges/hint/<int:challenge_id>', methods=['POST'])
@login_required
def get_challenge_hint(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if not challenge.hint:
        return jsonify({'error': 'Este desafio não tem uma dica disponível.'}), 404
    if current_user.points < challenge.hint_cost:
        return jsonify({'error': 'Você não tem pontos suficientes para comprar esta dica.'}), 403
    current_user.points -= challenge.hint_cost
    db.session.commit()
    flash(f'Você gastou {challenge.hint_cost} pontos para ver uma dica!', 'info')
    return jsonify({'hint': challenge.hint})

@app.route('/admin/paths', methods=['GET', 'POST'])
@login_required
def admin_paths():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'import_paths':
            file = request.files.get('path_file')
            if not file or not file.filename.endswith('.json'):
                flash('Por favor, envie um arquivo .json válido.', 'error')
                return redirect(url_for('admin_paths'))
            try:
                data = json.load(file.stream)
                count = 0
                for item in data:
                    path_name = item.get('name')
                    if path_name and not LearningPath.query.filter_by(name=path_name).first():
                        new_path = LearningPath(
                            name=path_name,
                            description=item.get('description'),
                            reward_points=item.get('reward_points', 100)
                        )
                        db.session.add(new_path)
                        db.session.flush()
                        for challenge_data in item.get('challenges', []):
                            challenge_title = challenge_data.get('title')
                            challenge = Challenge.query.filter_by(title=challenge_title).first()
                            if challenge:
                                new_path_challenge = PathChallenge(
                                    path_id=new_path.id,
                                    challenge_id=challenge.id,
                                    step=challenge_data.get('step')
                                )
                                db.session.add(new_path_challenge)
                        count += 1
                db.session.commit()
                flash(f'{count} novas trilhas importadas com sucesso!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Ocorreu um erro ao processar o arquivo: {e}', 'error')
        return redirect(url_for('admin_paths'))
    all_paths = LearningPath.query.all()
    all_challenges = Challenge.query.all()
    return render_template('admin_paths.html', paths=all_paths, challenges=all_challenges)

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

@app.route('/admin/paths/remove_challenge/<int:path_id>/<int:challenge_id>', methods=['POST'])
@login_required
def admin_remove_challenge_from_path(path_id, challenge_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
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
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_achievement':
            name = request.form.get('name')
            description = request.form.get('description')
            trigger_type = request.form.get('trigger_type')
            trigger_value = request.form.get('trigger_value', type=int)
            file = request.files.get('icon_image')
            icon_url = None
            if file and file.filename:
                try:
                    upload_result = cloudinary.uploader.upload(file)
                    icon_url = upload_result['secure_url']
                except Exception as e:
                    flash(f'Erro ao fazer upload da imagem: {e}', 'error')
                    return redirect(url_for('admin_achievements'))
            if name and description and trigger_type and trigger_value is not None:
                new_achievement = Achievement(
                    name=name,
                    description=description,
                    icon=icon_url,
                    trigger_type=trigger_type,
                    trigger_value=trigger_value
                )
                db.session.add(new_achievement)
                db.session.commit()
                flash('Conquista criada com sucesso!', 'success')
            else:
                flash('Erro ao criar conquista. Verifique os campos.', 'error')
        elif action == 'import_achievements':
            file = request.files.get('achievement_file')
            if not file or not file.filename.endswith('.json'):
                flash('Por favor, envie um arquivo .json válido.', 'error')
                return redirect(url_for('admin_achievements'))
            try:
                data = json.load(file.stream)
                count = 0
                for item in data:
                    name = item.get('name')
                    if name and not Achievement.query.filter_by(name=name).first():
                        new_achievement = Achievement(
                            name=name,
                            description=item.get('description'),
                            icon=item.get('icon', 'fas fa-star'),
                            trigger_type=item.get('trigger_type'),
                            trigger_value=item.get('trigger_value')
                        )
                        db.session.add(new_achievement)
                        count += 1
                db.session.commit()
                flash(f'{count} novas conquistas importadas com sucesso!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Ocorreu um erro ao processar o arquivo: {e}', 'error')
        return redirect(url_for('admin_achievements'))
    achievements = Achievement.query.all()
    return render_template('admin_achievements.html', achievements=achievements)

@app.route('/admin/daily_challenges')
@login_required
def admin_daily_challenges():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    history = DailyChallenge.query.order_by(DailyChallenge.day.desc()).all()
    return render_template('admin_daily_challenges.html', history=history)

@app.route('/admin/achievements/edit/<int:achievement_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_achievement(achievement_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    achievement_to_edit = Achievement.query.get_or_404(achievement_id)
    if request.method == 'POST':
        achievement_to_edit.name = request.form.get('name')
        achievement_to_edit.description = request.form.get('description')
        achievement_to_edit.icon = request.form.get('icon')
        achievement_to_edit.trigger_type = request.form.get('trigger_type')
        achievement_to_edit.trigger_value = request.form.get('trigger_value', type=int)
        db.session.commit()
        flash('Conquista atualizada com sucesso!', 'success')
        return redirect(url_for('admin_achievements'))
    return render_template('admin_edit_achievement.html', achievement=achievement_to_edit)

@app.route('/admin/achievements/delete/<int:achievement_id>', methods=['POST'])
@login_required
def admin_delete_achievement(achievement_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    achievement_to_delete = Achievement.query.get_or_404(achievement_id)
    UserAchievement.query.filter_by(achievement_id=achievement_id).delete()
    db.session.delete(achievement_to_delete)
    db.session.commit()
    flash('Conquista excluída com sucesso!', 'success')
    return redirect(url_for('admin_achievements'))

@app.route('/admin/bossfights', methods=['GET', 'POST'])
@login_required
def admin_boss_fights():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_boss':
            name = request.form.get('name')
            description = request.form.get('description')
            reward_points = request.form.get('reward_points', type=int)
            file = request.files.get('boss_image')
            image_url = None
            if file and file.filename:
                try:
                    upload_result = cloudinary.uploader.upload(file, folder="boss_fights")
                    image_url = upload_result['secure_url']
                except Exception as e:
                    flash(f'Erro ao fazer upload da imagem: {e}', 'error')
                    return redirect(url_for('admin_boss_fights'))
            if name and description and reward_points:
                new_boss = BossFight(name=name, description=description, reward_points=reward_points, image_url=image_url, is_active=True)
                db.session.add(new_boss)
                db.session.commit()
                flash('Boss Fight criado com sucesso!', 'success')
        elif action == 'create_step':
            stage_id = request.form.get('stage_id', type=int)
            description = request.form.get('description')
            expected_answer = request.form.get('expected_answer')
            if stage_id and description and expected_answer:
                new_step = BossFightStep(stage_id=stage_id, description=description, expected_answer=expected_answer)
                db.session.add(new_step)
                db.session.commit()
                flash('Tarefa adicionada à etapa!', 'success')
        return redirect(url_for('admin_boss_fights'))
    all_boss_fights = BossFight.query.all()
    return render_template('admin_boss_fights.html', boss_fights=all_boss_fights)

@app.route('/admin/bossfights/edit/<int:boss_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_boss_fight(boss_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    boss_to_edit = BossFight.query.get_or_404(boss_id)
    if request.method == 'POST':
        boss_to_edit.name = request.form.get('name')
        boss_to_edit.description = request.form.get('description')
        boss_to_edit.reward_points = request.form.get('reward_points', type=int)
        boss_to_edit.is_active = request.form.get('is_active') == 'on'
        file = request.files.get('boss_image')
        if file and file.filename:
            try:
                upload_result = cloudinary.uploader.upload(file, folder="boss_fights")
                boss_to_edit.image_url = upload_result['secure_url']
            except Exception as e:
                flash(f'Erro ao atualizar a imagem: {e}', 'error')
        db.session.commit()
        flash('Boss Fight atualizado com sucesso!', 'success')
        return redirect(url_for('admin_boss_fights'))
    return render_template('admin_edit_boss_fight.html', boss=boss_to_edit)

@app.route('/admin/bossfights/delete/<int:boss_id>', methods=['POST'])
@login_required
def admin_delete_boss_fight(boss_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    boss = BossFight.query.get_or_404(boss_id)
    db.session.delete(boss)
    db.session.commit()
    flash('Boss Fight excluído com sucesso!', 'success')
    return redirect(url_for('admin_boss_fights'))

@app.route('/admin/bossfights/stage/delete/<int:stage_id>', methods=['POST'])
@login_required
def admin_delete_boss_stage(stage_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    stage = BossFightStage.query.get_or_404(stage_id)
    db.session.delete(stage)
    db.session.commit()
    flash('Etapa excluída com sucesso!', 'success')
    return redirect(url_for('admin_boss_fights'))

@app.route('/admin/bossfights/step/delete/<int:step_id>', methods=['POST'])
@login_required
def admin_delete_boss_step(step_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
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

@app.route('/admin/challenges/edit/<int:challenge_id>', methods=['POST'])
@login_required
def admin_edit_challenge(challenge_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Acesso negado'}), 403
    challenge_to_edit = Challenge.query.get_or_404(challenge_id)
    challenge_to_edit.title = request.form.get('title')
    challenge_to_edit.description = request.form.get('description')
    challenge_to_edit.level_required = request.form.get('level_required')
    challenge_to_edit.points_reward = request.form.get('points_reward', type=int)
    challenge_to_edit.expected_answer = request.form.get('expected_answer')
    challenge_to_edit.is_team_challenge = request.form.get('is_team_challenge') == 'true'
    challenge_to_edit.hint = request.form.get('hint')
    challenge_to_edit.hint_cost = request.form.get('hint_cost', type=int)
    db.session.commit()
    return jsonify({'success': 'Desafio atualizado com sucesso!'})

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