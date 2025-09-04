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
from flask_caching import Cache
import click
from flask.cli import with_appcontext
from flask_caching import Cache
from PIL import Image

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')
# Configuração do Cache (simples, em memória)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})
# Configuração do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')
    
app.config['CACHE_TYPE'] = 'RedisCache'
app.config['CACHE_REDIS_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
cache = Cache(app)

# Configuração do spaCy
try:
    nlp = spacy.load('pt_core_news_sm')
except OSError:
    print("Modelo pt_core_news_sm não encontrado. A fazer o download...")
    spacy.cli.download('pt_core_news_sm')
    nlp = spacy.load('pt_core_news_sm')


# Modelos

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
    
    
class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    level_required = db.Column(db.String(50), default='Iniciante')
    points_reward = db.Column(db.Integer, default=10)
    # Resposta esperada (para verificação simples)
    expected_answer = db.Column(db.String(500), nullable=False)
    # ID da FAQ que este desafio desbloqueia (opcional)
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

    @property
    def formatted_answer(self):
        return format_faq_response(self.id, self.question, self.answer, self.image_url, self.video_url, self.file_name)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.String(20), default='Aberto')
    description = db.Column(db.Text)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text)
    faq_id_suggestion = db.Column(db.Integer, db.ForeignKey('faq.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    feedback = db.Column(db.String(10), nullable=True) # 'helpful' or 'unhelpful'

    user = db.relationship('User', backref=db.backref('chat_messages', lazy=True))
    
class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamento para aceder aos membros do time
    members = db.relationship('User', foreign_keys='User.team_id', backref='team', lazy='dynamic')
    @property
    def total_points(self):
        # Calcula a pontuação total do time somando os pontos de todos os membros
        return sum(member.points for member in self.members)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_gamification_data():
    """Injeta dados de gamificação em todos os templates."""
    if current_user.is_authenticated:
        # --- CORREÇÃO APLICADA AQUI ---
        # Garante que mesmo que o nível seja nulo, a aplicação não falha
        insignia_url = None
        if current_user.level and current_user.level.insignia_image_url:
            insignia_url = url_for('uploaded_insignia', filename=current_user.level.insignia_image_url)
        
        return dict(user_level_insignia=insignia_url)
    return dict()
# Inicialização do banco de dados e categorias padrão
with app.app_context():
    db.create_all()
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

def format_faq_response(faq_id, question, answer, image_url=None, video_url=None, file_name=None):
    formatted_response = f"<strong>Pergunta:</strong> {question}<br><br>"

    has_sections = any(section in answer for section in ["Pré-requisitos:", "Etapa", "Atenção:", "Finalizar:", "Pós-instalação:"])
    
    if has_sections:
        sections = re.split(r'(Pré-requisitos:|Etapa \d+:|Atenção:|Finalizar:|Pós-instalação:)', answer)
        current_section = None
        for i in range(0, len(sections), 2):
            header = sections[i].strip() if i + 1 < len(sections) else ""
            content = sections[i + 1].strip() if i + 1 < len(sections) else ""

            if header:
                if header.startswith("Pré-requisitos:"):
                    current_section = "Pré-requisitos"
                    formatted_response += "<strong>✅ Pré-requisitos</strong><br>"
                elif header.startswith("Etapa"):
                    current_section = "Etapa"
                    formatted_response += f"<strong>🔧 {header}</strong><br>"
                elif header.startswith("Atenção:"):
                    current_section = "Atenção"
                    formatted_response += "<strong>⚠️ Atenção</strong><br>"
                elif header.startswith("Finalizar:"):
                    current_section = "Finalizar"
                    formatted_response += "<strong>⏳ Finalizar</strong><br>"
                elif header.startswith("Pós-instalação:"):
                    current_section = "Pós-instalação"
                    formatted_response += "<strong>✅ Pós-instalação</strong><br>"
            
            if content and current_section:
                items = re.split(r'(?<=[.!?])\s+(?=[A-Z])', content)
                for item in items:
                    item = item.strip()
                    if item:
                        formatted_response += f"{item}<br>"
                formatted_response += "<br>" if i + 2 < len(sections) else ""
    else:
        lines = [line.strip() for line in answer.split('\n') if line.strip()]
        for line in lines:
            formatted_response += f"{line}<br>"
    
    if image_url and is_image_url(image_url):
        formatted_response += f'<img src="{image_url}" alt="Imagem da FAQ" style="max-width: 100%; height: auto; margin-top: 10px;"><br>'
    
    if video_url and is_video_url(video_url):
        if 'youtube.com' in video_url or 'youtu.be' in video_url:
            video_id = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', video_url)
            if video_id:
                video_id = video_id.group(1)
                formatted_response += f'<iframe width="560" height="315" src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen style="margin-top: 10px;"></iframe><br>'
            else:
                formatted_response += f'<p>URL do YouTube inválida: {video_url}</p><br>'
        else:
            formatted_response += f'<video width="560" height="315" controls style="margin-top: 10px;"><source src="{video_url}" type="video/mp4">Seu navegador não suporta o vídeo.</video><br>'
    
    # Adicionar link de download do arquivo, se disponível
    if file_name:
        formatted_response += f'<br><a href="/download/{faq_id}" class="text-blue-600 dark:text-blue-400 hover:underline" target="_blank">📎 Baixar arquivo: {file_name}</a>'

    if formatted_response.endswith("<br>") and (image_url or video_url or file_name):
        formatted_response = formatted_response[:-4]
    
    return formatted_response

def is_image_url(url):
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
    return url and url.lower().endswith(image_extensions)

def is_video_url(url):
    video_extensions = ('.mp4', '.webm', '.ogg')
    return url and (any(url.lower().endswith(ext) for ext in video_extensions) or 'youtube.com' in url.lower() or 'youtu.be' in url.lower())

def find_faqs_by_keywords(message):
    search_words = set(message.lower().split())
    if not search_words:
        return []

    faqs = FAQ.query.all()
    matches = []

    for faq in faqs:
        question_words = set(faq.question.lower().split())
        answer_words = set(faq.answer.lower().split())

        # Conta quantas palavras da busca aparecem na FAQ
        score = len(search_words.intersection(question_words)) * 2
        score += len(search_words.intersection(answer_words))

        if score > 0:
            matches.append((faq, score))

    # Ordena os resultados pelo score (mais relevante primeiro)
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches]

@cache.cached(timeout=600, key_prefix='faq_search')
def find_faq_by_nlp(message):
    """Usa o spaCy para extrair palavras-chave e encontrar FAQs relevantes."""
    doc = nlp(message.lower())

    # Extrai substantivos, verbos e nomes próprios como palavras-chave
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
    """Verifica os pontos do utilizador e atualiza o seu nível se necessário."""
    current_level_id = user.level_id

    # Encontra o nível mais alto que o utilizador alcançou
    new_level = Level.query.filter(Level.min_points <= user.points).order_by(Level.min_points.desc()).first()

    if new_level and new_level.id != current_level_id:
        user.level_id = new_level.id
        flash(f'Subiu de nível! Você agora é {new_level.name}!', 'success')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem ver esta página.', 'error')
        return redirect(url_for('index'))

    all_users = User.query.order_by(User.name).all()
    return render_template('admin_users.html', users=all_users)

@app.context_processor
def inject_user_gamification_data():
    if current_user.is_authenticated:
        return dict(user_level_insignia=current_user.level.insignia)
    return dict()

@app.route('/uploads/insignias/<filename>')
def uploaded_insignia(filename):
    return send_from_directory(app.config['INSIGNIA_FOLDER'], filename)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    # Recolher estatísticas
    stats = {
        'total_users': User.query.count(),
        'total_faqs': FAQ.query.count(),
        'total_teams': Team.query.count(),
        'total_challenges_completed': UserChallenge.query.count(),
        'top_users': User.query.order_by(User.points.desc()).limit(5).all()
    }

    return render_template('admin_dashboard.html', stats=stats)

@app.route('/ranking')
@login_required
def ranking():
    # Busca todos os utilizadores, ordenados por pontos (do maior para o menor)
    ranked_users = User.query.order_by(User.points.desc()).all()
    
    # Ranking de times
    all_teams = Team.query.all()
    # Ordena os times pela pontuação total (calculada na propriedade do modelo)
    ranked_teams = sorted(all_teams, key=lambda t: t.total_points, reverse=True)
    
    return render_template(
        'ranking.html', 
        ranked_users=ranked_users, 
        ranked_teams=ranked_teams,
        LEVELS=LEVELS  # <-- ESTA É A CORREÇÃO
    )
# Rotas
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    user_to_modify = User.query.get_or_404(user_id)

    # Proteção para não remover a sua própria permissão de admin
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
        cache.clear()
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
    cache.clear()
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
        cache.clear()
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
        phone = request.form.get('phone')
        initial_level = Level.query.filter_by(name='Iniciante').first()
        if User.query.filter_by(email=email).first():
            flash('Email já registrado.', 'error')
        else:
            user = User(name=name, email=email, password=password, phone=phone, is_admin=False)
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
                    resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches][:5] # Limita a 5 opções
            else:
                resposta['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta."

    return jsonify(resposta)

@app.route('/setup-first-admin-a1b2c3d4e5')
def setup_first_admin():
    # --- PERSONALIZE ESTES DADOS ---
    ADMIN_EMAIL = "admin@d3vb4.com"
    ADMIN_PASSWORD = "d3vb4_admin!"
    ADMIN_NAME = "Administrador"
    # -----------------------------

    # Verifica se o administrador já existe
    if User.query.filter_by(email=ADMIN_EMAIL).first():
        return f"<h1>Erro</h1><p>O administrador com o email {ADMIN_EMAIL} já existe.</p>"

    # Cria o novo administrador
    hashed_password = generate_password_hash(ADMIN_PASSWORD)
    admin_user = User(
        name=ADMIN_NAME,
        email=ADMIN_EMAIL,
        password=hashed_password,
        is_admin=True
    )
    db.session.add(admin_user)
    db.session.commit()
    
    return f"<h1>Sucesso</h1><p>Administrador criado com o email {ADMIN_EMAIL}. Por favor, exclua ou proteja esta rota imediatamente.</p>"

@app.route('/chat/feedback', methods=['POST'])
@login_required
def chat_feedback():
    data = request.get_json()
    message_id = data.get('message_id')
    feedback_type = data.get('feedback') # 'helpful' or 'unhelpful'

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
                cache.clear()
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

@app.route('/admin/challenges', methods=['GET', 'POST'])
@login_required
def admin_challenges():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem gerir desafios.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Lógica para adicionar um novo desafio
        title = request.form.get('title')
        description = request.form.get('description')
        level_required = request.form.get('level_required')
        points_reward = request.form.get('points_reward', type=int)
        expected_answer = request.form.get('expected_answer')
        unlocks_faq_id = request.form.get('unlocks_faq_id')
        
        # Converte o ID da FAQ para int ou None
        if unlocks_faq_id and unlocks_faq_id.isdigit():
            unlocks_faq_id = int(unlocks_faq_id)
        else:
            unlocks_faq_id = None

        new_challenge = Challenge(
            title=title,
            description=description,
            level_required=level_required,
            points_reward=points_reward,
            expected_answer=expected_answer,
            unlocks_faq_id=unlocks_faq_id
        )
        db.session.add(new_challenge)
        db.session.commit()
        flash('Novo desafio adicionado com sucesso!', 'success')
        return redirect(url_for('admin_challenges'))

    all_challenges = Challenge.query.order_by(Challenge.id).all()
    all_faqs = FAQ.query.order_by(FAQ.question).all()
    return render_template('admin_challenges.html', challenges=all_challenges, faqs=all_faqs, levels=LEVELS)


@app.route('/admin/challenges/delete/<int:challenge_id>', methods=['POST'])
@login_required
def delete_challenge(challenge_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    challenge_to_delete = Challenge.query.get_or_404(challenge_id)
    # Apaga também o progresso dos utilizadores neste desafio para evitar erros
    UserChallenge.query.filter_by(challenge_id=challenge_id).delete()
    db.session.delete(challenge_to_delete)
    db.session.commit()
    flash('Desafio apagado com sucesso.', 'success')
    return redirect(url_for('admin_challenges'))

@app.route('/challenges')
@login_required
def list_challenges():
    # Encontra os IDs dos desafios que o utilizador já completou
    completed_challenges_ids = [uc.challenge_id for uc in current_user.completed_challenges]

    # Encontra o nível atual e os pontos mínimos para esse nível
    user_current_level_name = current_user.level
    user_level_min_points = LEVELS.get(user_current_level_name, {}).get('min_points', 0)

    # Busca desafios que o utilizador ainda não completou
    available_challenges_query = Challenge.query.filter(Challenge.id.notin_(completed_challenges_ids))

    # Filtra os desafios por nível
    unlocked_challenges = []
    locked_challenges = []

    for challenge in available_challenges_query.all():
        challenge_level_min_points = LEVELS.get(challenge.level_required, {}).get('min_points', float('inf'))
        if user_level_min_points >= challenge_level_min_points:
            unlocked_challenges.append(challenge)
        else:
            locked_challenges.append(challenge)

    return render_template('challenges.html', 
                            unlocked_challenges=unlocked_challenges, 
                            locked_challenges=locked_challenges)

@app.route('/challenges/submit/<int:challenge_id>', methods=['POST'])
@login_required
def submit_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    submitted_answer = request.form.get('answer').strip()

    # Verificação simples (compara a resposta enviada com a resposta esperada)
    if submitted_answer == challenge.expected_answer:
        # Verifica se o utilizador já não completou este desafio antes
        existing_completion = UserChallenge.query.filter_by(user_id=current_user.id, challenge_id=challenge_id).first()
        if not existing_completion:
            # Dá os pontos ao utilizador
            current_user.points += challenge.points_reward

            # Chama a função para verificar se o utilizador subiu de nível
            update_user_level(current_user)

            # Regista que o desafio foi completo
            completion = UserChallenge(user_id=current_user.id, challenge_id=challenge_id)
            db.session.add(completion)
            db.session.commit()# Dá os pontos ao utilizador
            current_user.points += challenge.points_reward
            
            # Regista que o desafio foi completo
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
        # Lógica para criar um novo time
        if current_user.team_id:
            flash('Você já pertence a um time. Saia do seu time atual para criar um novo.', 'error')
            return redirect(url_for('teams_list'))

        team_name = request.form.get('team_name')
        if Team.query.filter_by(name=team_name).first():
            flash('Já existe um time com este nome.', 'error')
        else:
            new_team = Team(name=team_name, owner_id=current_user.id)
            db.session.add(new_team)
            # Adiciona o criador como o primeiro membro
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
    # Lógica adicional: se o dono sair, o que acontece?
    # Versão simples: o time continua a existir.
    # Versão complexa: transferir posse ou apagar o time se for o último membro.
    if team.owner_id == current_user.id:
        flash('Você é o dono do time e não pode sair. (Implementar lógica de transferência de posse ou apagar o time).', 'warning')
        return redirect(url_for('teams_list'))

    current_user.team_id = None
    db.session.commit()
    flash(f'Você saiu do time "{team.name}".', 'success')
    return redirect(url_for('teams_list'))


# --- ROTAS DE ADMINISTRAÇÃO ---

@app.route('/admin/levels', methods=['GET', 'POST'])
@login_required
def admin_levels():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        min_points = request.form.get('min_points', type=int)
        insignia_file = request.files.get('insignia_image')
        
        filename = 'default.png'
        if insignia_file and insignia_file.filename != '':
            filename = secure_filename(insignia_file.filename)
            insignia_file.save(os.path.join(app.config['INSIGNIA_FOLDER'], filename))

        new_level = Level(name=name, min_points=min_points, insignia_image_url=filename)
        db.session.add(new_level)
        db.session.commit()
        flash('Novo nível criado com sucesso!', 'success')
        return redirect(url_for('admin_levels'))

    levels = Level.query.order_by(Level.min_points.asc()).all()
    return render_template('admin_levels.html', levels=levels)

@app.route('/admin/teams')
@login_required
def admin_teams():
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    all_teams = Team.query.all()
    return render_template('admin_teams.html', teams=all_teams)

@app.route('/admin/teams/delete/<int:team_id>', methods=['POST'])
@login_required
def admin_delete_team(team_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    team_to_delete = Team.query.get_or_404(team_id)
    # Remove todos os membros do time antes de o apagar
    for member in team_to_delete.members:
        member.team_id = None
    db.session.delete(team_to_delete)
    db.session.commit()
    flash(f'O time "{team_to_delete.name}" foi dissolvido.', 'success')
    return redirect(url_for('admin_teams'))

# --- ROTAS DE GESTÃO DE TIME (PARA O DONO) ---

@app.route('/team/manage')
@login_required
def manage_team():
    if not current_user.team:
        flash('Você não pertence a um time.', 'error')
        return redirect(url_for('teams_list'))
    
    team = current_user.team
    if team.owner_id != current_user.id:
        flash('Apenas o dono do time pode gerir os membros.', 'error')
        return redirect(url_for('teams_list'))

    return render_template('manage_team.html', team=team)

@app.route('/team/kick/<int:user_id>', methods=['POST'])
@login_required
def kick_from_team(user_id):
    if not current_user.team or current_user.team.owner_id != current_user.id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('teams_list'))

    user_to_kick = User.query.get_or_404(user_id)
    if user_to_kick.team_id != current_user.team_id:
        flash('Este utilizador não pertence ao seu time.', 'error')
        return redirect(url_for('manage_team'))
    
    if user_to_kick.id == current_user.id:
        flash('Você não pode expulsar a si mesmo.', 'error')
        return redirect(url_for('manage_team'))

    user_to_kick.team_id = None
    db.session.commit()
    flash(f'O utilizador {user_to_kick.name} foi removido do time.', 'success')
    return redirect(url_for('manage_team'))


if __name__ == '__main__':
    app.run(debug=True)
    
with app.app_context():
    db.create_all() # Garante que todas as tabelas existem
    if Level.query.count() == 0:
        print("A semear os níveis iniciais na base de dados...")
        levels_to_seed = [
            Level(name='Iniciante', min_points=0, insignia='🌱'),
            Level(name='Dados de Prata', min_points=50, insignia='🥈'),
            Level(name='Dados de Ouro', min_points=150, insignia='🥇'),
            Level(name='Mestre dos Dados', min_points=300, insignia='🏆')
        ]
        db.session.bulk_save_objects(levels_to_seed)
        db.session.commit()


@click.command(name='create-admin')
@with_appcontext
@click.option('--name', required=True, help='O nome do administrador.')
@click.option('--email', required=True, help='O email do administrador.')
@click.option('--password', required=True, help='A senha do administrador.')
def create_admin(name, email, password):
    """Cria um novo utilizador administrador."""
    if User.query.filter_by(email=email).first():
        print(f"Erro: O email '{email}' já existe.")
        return

    hashed_password = generate_password_hash(password)
    admin_user = User(
        name=name,
        email=email,
        password=hashed_password,
        is_admin=True
    )
    db.session.add(admin_user)
    db.session.commit()
    print(f"Administrador '{name}' criado com sucesso!")
    



app.cli.add_command(create_admin)    