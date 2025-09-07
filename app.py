from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_file
import io
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import csv
import json
import re
from PyPDF2 import PdfReader
from datetime import datetime
import spacy
import spacy.cli
import click
from flask.cli import with_appcontext
from flask_caching import Cache
from sqlalchemy.orm import aliased

app = Flask(__name__)

# --- CONFIGURAÇÕES DA APLICAÇÃO ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'uma-chave-secreta-padrao-para-desenvolvimento')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# --- INICIALIZAÇÃO DAS EXTENSÕES ---
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# Configuração do spaCy
try:
    nlp = spacy.load('pt_core_news_sm')
except OSError:
    print("Modelo pt_core_news_sm não encontrado. A fazer o download...")
    spacy.cli.download('pt_core_news_sm')
    nlp = spacy.load('pt_core_news_sm')

# --- MODELOS DA BASE DE DADOS ---
class Level(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    min_points = db.Column(db.Integer, unique=True, nullable=False, index=True)
    insignia = db.Column(db.String(10), nullable=False, default='🌱')

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

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # ADICIONE ESTA LINHA PARA CRIAR O RELACIONAMENTO COM O DONO
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
    feedback = db.Column(db.String(20))  # 'helpful', 'unhelpful'

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
    
    # Inicializar níveis
    for level_name, level_data in LEVELS.items():
        if not Level.query.filter_by(name=level_name).first():
            level = Level(
                name=level_name,
                min_points=level_data['min_points'],
                insignia=level_data['insignia']
            )
            db.session.add(level)
    
    # Inicializar categorias
    categories = ['Hardware', 'Software', 'Rede', 'Outros', 'Mobile', 'Automation']
    for category_name in categories:
        if not Category.query.filter_by(name=category_name).first():
            category = Category(name=category_name)
            db.session.add(category)
    
    db.session.commit()

# Funções de utilidade
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
    """Verifica se uma URL termina com uma extensão de imagem comum."""
    if not url: return False
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp')
    return url.lower().endswith(image_extensions)

def is_video_url(url):
    """Verifica se uma URL é de um vídeo (YouTube ou extensão de vídeo comum)."""
    if not url: return False
    video_extensions = ('.mp4', '.webm', '.ogg')
    return any(url.lower().endswith(ext) for ext in video_extensions) or 'youtube.com' in url.lower() or 'youtu.be' in url.lower()

# >>>>>>>>> AQUI ESTÁ A FUNÇÃO UNIFICADA E CORRIGIDA <<<<<<<<<<<
def format_faq_response(faq_id, question, answer, image_url=None, video_url=None, file_name=None):
    """
    Formata a resposta da FAQ para HTML, combinando a lógica de secções
    com a incorporação de imagens, vídeos e ficheiros.
    """
    # Inicia a resposta com a pergunta
    formatted_response = f"<strong>{question}</strong><br><br>"
    
    # Lógica para formatar o texto com secções (Pré-requisitos, Etapas, etc.)
    has_sections = any(section in answer for section in ["Pré-requisitos:", "Etapa", "Atenção:", "Finalizar:", "Pós-instalação:"])
    
    if has_sections:
        # Divide a resposta com base nas palavras-chave das secções
        parts = re.split(r'(Pré-requisitos:|Etapa \d+:|Atenção:|Finalizar:|Pós-instalação:)', answer)
        # Processa a primeira parte do texto que vem antes de qualquer secção
        formatted_response += parts[0].replace('\n', '<br>')

        # Processa as secções formatadas
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
        # Se não houver secções, apenas formata o texto com quebras de linha
        formatted_response += answer.replace('\n', '<br>')

    # Adiciona a imagem, se existir
    if image_url and is_image_url(image_url):
        formatted_response += f'<br><img src="{image_url}" alt="Imagem de suporte" style="max-width: 100%; border-radius: 8px; margin-top: 10px;">'
    
    # Adiciona o vídeo, se existir
    if video_url and is_video_url(video_url):
        if 'youtube.com' in video_url or 'youtu.be' in video_url:
            video_id_match = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', video_url)
            if video_id_match:
                video_id = video_id_match.group(1)
                formatted_response += f'<div style="position: relative; padding-bottom: 56.25%; margin-top: 10px; height: 0; overflow: hidden; max-width: 100%;"><iframe src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe></div>'
        else:
            formatted_response += f'<br><video controls style="max-width: 100%; border-radius: 8px; margin-top: 10px;"><source src="{video_url}" type="video/mp4">O seu navegador não suporta o vídeo.</video>'
    
    # Adiciona o link de download do ficheiro, se existir
    if file_name:
        formatted_response += f'<br><br><a href="/download/{faq_id}" class="text-blue-400 hover:underline" target="_blank">📎 Baixar ficheiro: {file_name}</a>'
    
    return formatted_response
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

@cache.cached(timeout=600, key_prefix='faq_search')
def find_faq_by_nlp(message):
    """Usa o spaCy para extrair palavras-chave e encontrar FAQs relevantes."""
    doc = nlp(message.lower())
    keywords = {token.lemma_ for token in doc if not token.is_stop and not token.is_punct and token.pos_ in ['NOUN', 'PROPN', 'VERB']}
    if not keywords:
        return []
    faqs = FAQ.query.all()
    matches = []
    for faq in faqs:
        question_doc = nlp(faq.question.lower())
        answer_doc = nlp(faq.answer.lower())
        faq_keywords = {token.lemma_ for token in question_doc if not token.is_stop and not token.is_punct}
        faq_keywords.update({token.lemma_ for token in answer_doc if not token.is_stop and not token.is_punct})
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

# Context processors
@app.context_processor
def inject_user_gamification_data():
    if current_user.is_authenticated and current_user.level:
        return dict(user_level_insignia=current_user.level.insignia)
    return dict(user_level_insignia='')

# --- ROTAS ---
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem ver esta página.', 'error')
        return redirect(url_for('index'))

    all_users = User.query.order_by(User.name).all()
    return render_template('admin_users.html', users=all_users)

@app.route('/ranking')
@login_required
def ranking():
    ranked_users = User.query.order_by(User.points.desc()).all()
    all_teams = Team.query.all()
    ranked_teams = sorted(all_teams, key=lambda t: t.total_points, reverse=True)
    return render_template('ranking.html', ranked_users=ranked_users, ranked_teams=ranked_teams)

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    user_to_modify = User.query.get_or_404(user_id)

    if user_to_modify.id == current_user.id:
        flash('Você não pode remover a sua própria permissão de administrador.', 'error')
        return redirect(url_for('admin_users'))

    user_to_modify.is_admin = not user_to_modify.is_admin
    db.session.commit()

    status = "administrador" if user_to_modify.is_admin else "utilizador normal"
    flash(f'O utilizador {user_to_modify.name} é agora um {status}.', 'success')
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
            flash('Email já registado.', 'error')
            return redirect(url_for('register'))

        initial_level = Level.query.order_by(Level.min_points).first()
        if not initial_level:
            flash('Erro de sistema: Nenhum nível inicial encontrado. Contacte o administrador.', 'error')
            return redirect(url_for('register'))

        user = User(
            name=name,
            email=email,
            password=password,
            is_admin=False,
            level_id=initial_level.id
        )
        db.session.add(user)
        db.session.commit()
        flash('Registo concluído! Faça login.', 'success')
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
        'options': []
    }

    ticket_response = process_ticket_command(mensagem)
    if ticket_response:
        resposta['text'] = ticket_response
    else:
        solution_response = suggest_solution(mensagem)
        if solution_response:
            resposta['text'] = solution_response
        else:
            faq_matches = find_faq_by_nlp(mensagem)
            if faq_matches:
                if len(faq_matches) == 1:
                    faq = faq_matches[0]
                    resposta['text'] = format_faq_response(faq.id, faq.question, faq.answer, faq.image_url, faq.video_url, faq.file_name)
                    resposta['html'] = True
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
    
    return jsonify({'status': 'error', 'message': 'Message not found or unauthorized'}), 404

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
        flash('Não foi possível determinar o seu nível. Por favor, contacte o suporte.', 'error')
        return redirect(url_for('index'))

    completed_challenges_ids = [uc.challenge_id for uc in current_user.completed_challenges]
    user_min_points = current_user.level.min_points
    
    RequiredLevel = aliased(Level)

    all_challenges_query = db.session.query(Challenge).filter(Challenge.id.notin_(completed_challenges_ids))
    all_challenges_query = all_challenges_query.join(RequiredLevel, Challenge.level_required == RequiredLevel.name)

    unlocked_challenges = all_challenges_query.filter(RequiredLevel.min_points <= user_min_points).all()
    locked_challenges = all_challenges_query.filter(RequiredLevel.min_points > user_min_points).all()

    return render_template('challenges.html', 
                           unlocked_challenges=unlocked_challenges, 
                           locked_challenges=locked_challenges)

@app.route('/challenges/submit/<int:challenge_id>', methods=['POST'])
@login_required
def submit_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    submitted_answer = request.form.get('answer').strip()

    if submitted_answer == challenge.expected_answer:
        existing_completion = UserChallenge.query.filter_by(user_id=current_user.id, challenge_id=challenge_id).first()
        if not existing_completion:
            current_user.points += challenge.points_reward
            update_user_level(current_user)
            
            completion = UserChallenge(user_id=current_user.id, challenge_id=challenge_id)
            db.session.add(completion)
            db.session.commit()

            flash(f'Parabéns! Você completou o desafio "{challenge.title}" e ganhou {challenge.points_reward} pontos!', 'success')
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
            flash('Você já pertence a um time. Saia do seu time atual para criar um novo.', 'error')
            return redirect(url_for('teams_list'))

        team_name = request.form.get('team_name')
        if Team.query.filter_by(name=team_name).first():
            flash('Já existe um time com este nome.', 'error')
        else:
            new_team = Team(name=team_name, owner_id=current_user.id)
            db.session.add(new_team)
            current_user.team = new_team
            db.session.commit()
            flash(f'Time "{team_name}" criado com sucesso!', 'success')
            return redirect(url_for('teams_list'))

    all_teams = Team.query.all()
    return render_template('teams.html', teams=all_teams)

@app.route('/teams/join/<int:team_id>', methods=['POST'])
@login_required
def join_team(team_id):
    if current_user.team_id:
        flash('Você já pertence a um time.', 'error')
        return redirect(url_for('teams_list'))

    team_to_join = Team.query.get_or_404(team_id)
    current_user.team = team_to_join
    db.session.commit()
    flash(f'Você entrou no time "{team_to_join.name}"!', 'success')
    return redirect(url_for('teams_list'))

@app.route('/teams/leave', methods=['POST'])
@login_required
def leave_team():
    if not current_user.team_id:
        flash('Você não pertence a nenhum time.', 'error')
        return redirect(url_for('teams_list'))

    team = current_user.team
    if team.owner_id == current_user.id:
        flash('Você é o dono do time e não pode sair. (Implementar lógica de transferência de posse ou apagar o time).', 'warning')
        return redirect(url_for('teams_list'))

    current_user.team_id = None
    db.session.commit()
    flash(f'Você saiu do time "{team.name}".', 'success')
    return redirect(url_for('teams_list'))

# Adicione este novo bloco de código no seu app.py

@app.route('/admin/teams/delete/<int:team_id>', methods=['POST'])
@login_required
def admin_delete_team(team_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    team_to_delete = Team.query.get_or_404(team_id)

    # Remove todos os membros do time antes de deletar
    for member in team_to_delete.members:
        member.team_id = None
    
    db.session.delete(team_to_delete)
    db.session.commit()
    
    flash(f'O time "{team_to_delete.name}" foi dissolvido com sucesso!', 'success')
    return redirect(url_for('admin_teams'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    # Recolher estatísticas para o dashboard
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

@app.route('/admin/faqs')
@login_required
def admin_faqs():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    # Supondo que admin_faq.html é a sua página de gestão de FAQs
    categories = Category.query.all()
    return render_template('admin_faq.html', categories=categories)

@app.route('/admin/levels', methods=['GET', 'POST'])
@login_required
def admin_levels():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Lógica para adicionar um novo nível
        name = request.form.get('name')
        min_points = request.form.get('min_points')
        insignia = request.form.get('insignia')
        if name and min_points and insignia:
            new_level = Level(name=name, min_points=int(min_points), insignia=insignia)
            db.session.add(new_level)
            db.session.commit()
            flash('Nível adicionado com sucesso!', 'success')
        else:
            flash('Todos os campos são obrigatórios.', 'error')
        return redirect(url_for('admin_levels'))

    levels = Level.query.order_by(Level.min_points).all()
    return render_template('admin_levels.html', levels=levels)


@app.route('/admin/challenges')
@login_required
def admin_challenges():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    all_challenges = Challenge.query.order_by(Challenge.level_required).all()
    return render_template('admin_challenges.html', challenges=all_challenges)
# Comando CLI para criar administrador
@click.command(name='create-admin')
@with_appcontext
@click.option('--name', required=True, help='O nome do administrador.')
@click.option('--email', required=True, help='O email do administrador.')
@click.option('--password', required=True, help='A senha do administrador.')
def create_admin(name, email, password):
    """Cria um usuário administrador."""
    # Verifica se já existe um usuário com esse email
    if User.query.filter_by(email=email).first():
        click.echo(f"Erro: Já existe um usuário com o email '{email}'.")
        return
    
    # Inicializa o banco de dados se necessário
    initialize_database()
    
    # Pega o nível inicial
    initial_level = Level.query.order_by(Level.min_points).first()
    if not initial_level:
        click.echo("Erro: Nenhum nível encontrado no sistema.")
        return
    
    # Cria o usuário administrador
    admin_user = User(
        name=name,
        email=email,
        password=generate_password_hash(password),
        is_admin=True,
        level_id=initial_level.id
    )
    
    db.session.add(admin_user)
    db.session.commit()
    
    click.echo(f"Administrador '{name}' criado com sucesso!")

app.cli.add_command(create_admin)

# Inicialização do contexto da aplicação
with app.app_context():
    initialize_database()

if __name__ == '__main__':
    app.run(debug=True)