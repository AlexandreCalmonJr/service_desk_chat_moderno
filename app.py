import os
import logging
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_file, send_from_directory
import io
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
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
from PIL import Image

# Configurar logging
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise RuntimeError("A variável de ambiente SECRET_KEY deve ser definida.")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'Uploads'
app.config['INSIGNIA_FOLDER'] = 'static/insignias'
app.config['CACHE_TYPE'] = 'RedisCache'
app.config['CACHE_REDIS_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Criar diretórios
for folder in [app.config['UPLOAD_FOLDER'], app.config['INSIGNIA_FOLDER']]:
    try:
        if not os.path.exists(folder):
            os.makedirs(folder)
            try:
                os.chmod(folder, 0o755)  # Tenta alterar permissões apenas se necessário
            except OSError as e:
                logging.warning(f"Não foi possível alterar permissões do diretório {folder}: {str(e)}")
    except OSError as e:
        logging.error(f"Erro ao criar diretório {folder}: {str(e)}")
        raise

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
cache = Cache(app)

# Configuração do spaCy
try:
    nlp = spacy.load('pt_core_news_sm')
except OSError:
    logging.info("Modelo pt_core_news_sm não encontrado. Tentando fazer o download...")
    try:
        spacy.cli.download('pt_core_news_sm')
        nlp = spacy.load('pt_core_news_sm')
        logging.info("Modelo pt_core_news_sm carregado com sucesso após download.")
    except Exception as e:
        logging.error(f"Erro ao carregar ou baixar o modelo spaCy: {str(e)}")
        nlp = None
        # Opcional: Levante uma exceção se o spaCy for crítico
        # raise RuntimeError("Modelo spaCy não pôde ser carregado. A aplicação não pode continuar.")

# Modelos
class Level(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    min_points = db.Column(db.Integer, unique=True, nullable=False, index=True)
    insignia_image_url = db.Column(db.String(255), nullable=False, default='beginner.svg')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(20))
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    points = db.Column(db.Integer, default=0)
    level_id = db.Column(db.Integer, db.ForeignKey('level.id'), nullable=True)
    level = db.relationship('Level', backref='users')
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)

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
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False, index=True)
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
    feedback = db.Column(db.String(10), nullable=True)
    user = db.relationship('User', backref=db.backref('chat_messages', lazy=True))

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    members = db.relationship('User', foreign_keys='User.team_id', backref='team', lazy='dynamic')

    @property
    def total_points(self):
        return sum(member.points for member in self.members)

# Configuração de níveis
LEVELS = {
    'Iniciante': {'min_points': 0, 'insignia': 'beginner.svg'},
    'Dados de Prata': {'min_points': 50, 'insignia': 'silver.svg'},
    'Dados de Ouro': {'min_points': 150, 'insignia': 'gold.svg'},
    'Mestre dos Dados': {'min_points': 300, 'insignia': 'master.svg'}
}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
        logging.error(f"Erro ao processar o PDF: {str(e)}", exc_info=True)
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
        score = len(search_words.intersection(question_words)) * 2
        score += len(search_words.intersection(answer_words))
        if score > 0:
            matches.append((faq, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches]

@cache.cached(timeout=3600, key_prefix='faq_search')
def find_faq_by_nlp(message):
    if not nlp:
        return find_faqs_by_keywords(message)
    doc = nlp(message.lower())
    keywords = {token.lemma_ for token in doc if not token.is_stop and not token.is_punct and token.pos_ in ['NOUN', 'PROPN', 'VERB']}
    if not keywords:
        return []
    faqs = FAQ.query.with_entities(FAQ.id, FAQ.question, FAQ.answer).all()
    matches = []
    for faq in faqs:
        question_doc = nlp(faq.question.lower())
        answer_doc = nlp(faq.answer.lower())
        faq_keywords = {token.lemma_ for token in question_doc if not token.is_stop and not token.is_punct}
        faq_keywords.update({token.lemma_ for token in answer_doc if not token.is_stop and not token.is_punct})
        score = len(keywords.intersection(faq_keywords))
        if score > 0:
            matches.append((FAQ.query.get(faq.id), score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches]

def update_user_level(user):
    current_level_id = user.level_id
    new_level = Level.query.filter(Level.min_points <= user.points).order_by(Level.min_points.desc()).first()
    if new_level and new_level.id != current_level_id:
        user.level_id = new_level.id
        db.session.commit()
        flash(f'Subiu de nível! Você agora é {new_level.name}!', 'success')

# Rotas
@app.context_processor
def inject_user_gamification_data():
    if current_user.is_authenticated and current_user.level:
        return dict(user_level_insignia=current_user.level.insignia_image_url)
    return dict(user_level_insignia='beginner.svg')

@app.route('/uploads/insignias/<filename>')
def uploaded_insignia(filename):
    try:
        return send_from_directory(app.config['INSIGNIA_FOLDER'], filename)
    except Exception as e:
        logging.error(f"Erro ao servir insígnia {filename}: {str(e)}", exc_info=True)
        return "Insígnia não encontrada", 404

@app.route('/')
@login_required
def index():
    try:
        logging.debug(f"Acessando rota /index por usuário {current_user.email}")
        return render_template('index.html')
    except Exception as e:
        logging.error(f"Erro na rota /index: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/users')
@login_required
def admin_users():
    try:
        if not current_user.is_admin:
            flash('Acesso negado. Apenas administradores podem ver esta página.', 'error')
            return redirect(url_for('index'))
        all_users = User.query.order_by(User.name).all()
        return render_template('admin_users.html', users=all_users)
    except Exception as e:
        logging.error(f"Erro na rota /admin/users: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    try:
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
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
    except Exception as e:
        logging.error(f"Erro na rota /admin/toggle_admin: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    try:
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        stats = {
            'total_users': User.query.count(),
            'total_faqs': FAQ.query.count(),
            'total_teams': Team.query.count(),
            'total_challenges_completed': UserChallenge.query.count(),
            'top_users': User.query.order_by(User.points.desc()).limit(5).all()
        }
        return render_template('admin_dashboard.html', stats=stats)
    except Exception as e:
        logging.error(f"Erro na rota /admin/dashboard: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/ranking')
@login_required
def ranking():
    try:
        ranked_users = User.query.order_by(User.points.desc()).all()
        all_teams = Team.query.all()
        ranked_teams = sorted(all_teams, key=lambda t: t.total_points, reverse=True)
        return render_template('ranking.html', ranked_users=ranked_users, ranked_teams=ranked_teams, LEVELS=LEVELS)
    except Exception as e:
        logging.error(f"Erro na rota /ranking: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/chat-page')
@login_required
def chat_page():
    try:
        session.pop('faq_selection', None)
        return render_template('chat.html')
    except Exception as e:
        logging.error(f"Erro na rota /chat-page: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    try:
        logging.debug(f"Processando mensagem de chat para usuário {current_user.email}")
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
                        resposta['text'] = faq.formatted_answer
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
    except Exception as e:
        logging.error(f"Erro na rota /chat: {str(e)}", exc_info=True)
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    try:
        if request.method == 'POST':
            current_user.phone = request.form.get('phone')
            db.session.commit()
            flash('Perfil atualizado com sucesso!', 'success')
            return redirect(url_for('profile'))
        return render_template('profile.html')
    except Exception as e:
        logging.error(f"Erro na rota /profile: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/faqs', methods=['GET'])
@login_required
def faqs():
    try:
        categories = Category.query.all()
        faqs_list = FAQ.query.all()
        faq_to_edit = None
        if request.args.get('edit'):
            faq_id = request.args.get('edit')
            faq_to_edit = FAQ.query.get_or_404(faq_id)
        return render_template('faqs.html', faqs=faqs_list, categories=categories, faq_to_edit=faq_to_edit)
    except Exception as e:
        logging.error(f"Erro na rota /faqs: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/faqs/edit/<int:faq_id>', methods=['GET', 'POST'])
@login_required
def edit_faq(faq_id):
    try:
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
    except Exception as e:
        logging.error(f"Erro na rota /faqs/edit/{faq_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/faqs/delete/<int:faq_id>', methods=['POST'])
@login_required
def delete_faq(faq_id):
    try:
        if not current_user.is_admin:
            flash('Acesso negado. Apenas administradores podem gerenciar FAQs.', 'error')
            return redirect(url_for('faqs'))
        faq = FAQ.query.get_or_404(faq_id)
        db.session.delete(faq)
        db.session.commit()
        cache.clear()
        flash('FAQ excluída com sucesso!', 'success')
        return redirect(url_for('faqs'))
    except Exception as e:
        logging.error(f"Erro na rota /faqs/delete/{faq_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/faqs/delete-multiple', methods=['POST'])
@login_required
def delete_multiple_faqs():
    try:
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
    except Exception as e:
        logging.error(f"Erro na rota /faqs/delete-multiple: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/download/<int:faq_id>')
@login_required
def download(faq_id):
    try:
        faq = FAQ.query.get_or_404(faq_id)
        if faq.file_data:
            return send_file(io.BytesIO(faq.file_data), download_name=faq.file_name, as_attachment=True)
        flash('Nenhum arquivo encontrado.', 'error')
        return redirect(url_for('faqs'))
    except Exception as e:
        logging.error(f"Erro na rota /download/{faq_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
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
    except Exception as e:
        logging.error(f"Erro na rota /login: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            password = generate_password_hash(request.form['password'])
            phone = request.form.get('phone')
            initial_level = Level.query.filter_by(name='Iniciante').first()
            if not initial_level:
                flash('Erro de configuração do servidor. Por favor, tente mais tarde.', 'error')
                logging.error("Tentativa de registo falhou: Nível 'Iniciante' não encontrado na base de dados.")
                return redirect(url_for('register'))
            
            if User.query.filter_by(email=email).first():
                flash('Email já registrado.', 'error')
            else:
                user = User(
                    name=name,
                    email=email,
                    password=password,
                    phone=phone,
                    is_admin=False,
                    level_id=initial_level.id
                )
                db.session.add(user)
                db.session.commit()
                flash('Registro concluído! Faça login.', 'success')
                return redirect(url_for('login'))
        return render_template('register.html')
    except Exception as e:
        logging.error(f"Erro na rota /register: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/logout')
@login_required
def logout():
    try:
        logout_user()
        flash('Você saiu com sucesso.', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        logging.error(f"Erro na rota /logout: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/setup-first-admin-a1b2c3d4e5')
def setup_first_admin():
    # ATENÇÃO: Esta rota deve ser desativada ou protegida após a configuração inicial do administrador!
    if not os.getenv('ENABLE_ADMIN_SETUP', 'False').lower() == 'true':
        return "<h1>Erro</h1><p>Rota desativada. Configure ENABLE_ADMIN_SETUP para ativar.</p>", 403
    try:
        ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@d3vb4.com')
        ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
        ADMIN_NAME = os.getenv('ADMIN_NAME', 'Administrador')
        if not ADMIN_PASSWORD:
            return "<h1>Erro</h1><p>A variável de ambiente ADMIN_PASSWORD deve ser definida.</p>", 500
        if User.query.filter_by(email=ADMIN_EMAIL).first():
            return f"<h1>Erro</h1><p>O administrador com o email {ADMIN_EMAIL} já existe.</p>"
        initial_level = Level.query.filter_by(name='Iniciante').first()
        if not initial_level:
            return "<h1>Erro</h1><p>Nível 'Iniciante' não encontrado. Execute 'flask init-db' primeiro.</p>"
        hashed_password = generate_password_hash(ADMIN_PASSWORD)
        admin_user = User(
            name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            password=hashed_password,
            is_admin=True,
            level_id=initial_level.id
        )
        db.session.add(admin_user)
        db.session.commit()
        return f"<h1>Sucesso</h1><p>Administrador criado com o email {ADMIN_EMAIL}. Por favor, desative esta rota imediatamente definindo ENABLE_ADMIN_SETUP=False.</p>"
    except Exception as e:
        logging.error(f"Erro na rota /setup-first-admin-a1b2c3d4e5: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/chat/feedback', methods=['POST'])
@login_required
def chat_feedback():
    try:
        data = request.get_json()
        message_id = data.get('message_id')
        feedback_type = data.get('feedback')
        message = ChatMessage.query.get(message_id)
        if message and message.user_id == current_user.id:
            message.feedback = feedback_type
            db.session.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': 'Message not found or unauthorized'}), 404
    except Exception as e:
        logging.error(f"Erro na rota /chat/feedback: {str(e)}", exc_info=True)
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/admin/faq', methods=['GET', 'POST'])
@login_required
def admin_faq():
    try:
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
                    allowed_mimes = {
                        '.json': 'application/json',
                        '.csv': 'text/csv',
                        '.pdf': 'application/pdf'
                    }
                    max_file_size = 10 * 1024 * 1024  # 10 MB
                    if file.content_type not in allowed_mimes.values():
                        flash(f'Tipo de arquivo inválido. Use apenas {", ".join(allowed_mimes.keys())}.', 'error')
                        return redirect(url_for('admin_faq'))
                    if file.content_length > max_file_size:
                        flash('Arquivo muito grande. O limite é 10 MB.', 'error')
                        return redirect(url_for('admin_faq'))
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
                        logging.error(f"Erro ao importar FAQs: {str(e)}", exc_info=True)
                        flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                    finally:
                        os.remove(file_path)
                else:
                    flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
        return render_template('admin_faq.html', categories=categories)
    except Exception as e:
        logging.error(f"Erro na rota /admin/faq: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/export/faqs')
@login_required
def export_faqs():
    try:
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
    except Exception as e:
        logging.error(f"Erro na rota /admin/export/faqs: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/challenges', methods=['GET', 'POST'])
@login_required
def admin_challenges():
    try:
        if not current_user.is_admin:
            flash('Acesso negado. Apenas administradores podem gerir desafios.', 'error')
            return redirect(url_for('index'))
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            level_required = request.form.get('level_required')
            points_reward = request.form.get('points_reward', type=int)
            expected_answer = request.form.get('expected_answer')
            unlocks_faq_id = request.form.get('unlocks_faq_id')
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
    except Exception as e:
        logging.error(f"Erro na rota /admin/challenges: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/challenges/delete/<int:challenge_id>', methods=['POST'])
@login_required
def delete_challenge(challenge_id):
    try:
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        challenge_to_delete = Challenge.query.get_or_404(challenge_id)
        UserChallenge.query.filter_by(challenge_id=challenge_id).delete()
        db.session.delete(challenge_to_delete)
        db.session.commit()
        flash('Desafio apagado com sucesso.', 'success')
        return redirect(url_for('admin_challenges'))
    except Exception as e:
        logging.error(f"Erro na rota /admin/challenges/delete/{challenge_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/challenges')
@login_required
def list_challenges():
    try:
        completed_challenges_ids = [uc.challenge_id for uc in current_user.completed_challenges]
        available_challenges_query = Challenge.query.filter(Challenge.id.notin_(completed_challenges_ids))
        unlocked_challenges = []
        locked_challenges = []
        for challenge in available_challenges_query.all():
            challenge_level_min_points = LEVELS.get(challenge.level_required, {}).get('min_points', float('inf'))
            user_level_min_points = LEVELS.get(current_user.level.name, {}).get('min_points', 0)
            if user_level_min_points >= challenge_level_min_points:
                unlocked_challenges.append(challenge)
            else:
                locked_challenges.append(challenge)
        return render_template('challenges.html', unlocked_challenges=unlocked_challenges, locked_challenges=locked_challenges)
    except Exception as e:
        logging.error(f"Erro na rota /challenges: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/challenges/submit/<int:challenge_id>', methods=['POST'])
@login_required
def submit_challenge(challenge_id):
    try:
        challenge = Challenge.query.get_or_404(challenge_id)
        submitted_answer = request.form.get('answer')
        if not submitted_answer:
            flash('Por favor, envie uma resposta.', 'error')
            return redirect(url_for('list_challenges'))
        submitted_answer = submitted_answer.strip()
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
    except Exception as e:
        logging.error(f"Erro na rota /challenges/submit/{challenge_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/teams', methods=['GET', 'POST'])
@login_required
def teams_list():
    try:
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
    except Exception as e:
        logging.error(f"Erro na rota /teams: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/teams/join/<int:team_id>', methods=['POST'])
@login_required
def join_team(team_id):
    try:
        if current_user.team_id:
            flash('Você já pertence a um time.', 'error')
            return redirect(url_for('teams_list'))
        team_to_join = Team.query.get_or_404(team_id)
        current_user.team = team_to_join
        db.session.commit()
        flash(f'Você entrou no time "{team_to_join.name}"!', 'success')
        return redirect(url_for('teams_list'))
    except Exception as e:
        logging.error(f"Erro na rota /teams/join/{team_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/teams/leave', methods=['POST'])
@login_required
def leave_team():
    try:
        if not current_user.team_id:
            flash('Você não pertence a nenhum time.', 'error')
            return redirect(url_for('teams_list'))
        team = current_user.team
        if team.owner_id == current_user.id:
            flash('Você é o dono do time e não pode sair.', 'warning')
            return redirect(url_for('teams_list'))
        current_user.team_id = None
        db.session.commit()
        flash(f'Você saiu do time "{team.name}".', 'success')
        return redirect(url_for('teams_list'))
    except Exception as e:
        logging.error(f"Erro na rota /teams/leave: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/team/manage')
@login_required
def manage_team():
    try:
        if not current_user.team:
            flash('Você não pertence a um time.', 'error')
            return redirect(url_for('teams_list'))
        team = current_user.team
        if team.owner_id != current_user.id:
            flash('Apenas o dono do time pode gerir os membros.', 'error')
            return redirect(url_for('teams_list'))
        return render_template('manage_team.html', team=team)
    except Exception as e:
        logging.error(f"Erro na rota /team/manage: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/team/kick/<int:user_id>', methods=['POST'])
@login_required
def kick_from_team(user_id):
    try:
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
    except Exception as e:
        logging.error(f"Erro na rota /team/kick/{user_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/levels', methods=['GET', 'POST'])
@login_required
def admin_levels():
    try:
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        if request.method == 'POST':
            name = request.form.get('name')
            min_points = request.form.get('min_points', type=int)
            insignia_file = request.files.get('insignia_image')
            filename = 'beginner.svg'
            if insignia_file and insignia_file.filename:
                filename = secure_filename(insignia_file.filename)
                insignia_file.save(os.path.join(app.config['INSIGNIA_FOLDER'], filename))
            new_level = Level(name=name, min_points=min_points, insignia_image_url=filename)
            db.session.add(new_level)
            db.session.commit()
            flash('Novo nível criado com sucesso!', 'success')
            return redirect(url_for('admin_levels'))
        levels = Level.query.order_by(Level.min_points.asc()).all()
        return render_template('admin_levels.html', levels=levels)
    except Exception as e:
        logging.error(f"Erro na rota /admin/levels: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/teams')
@login_required
def admin_teams():
    try:
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        all_teams = Team.query.all()
        return render_template('admin_teams.html', teams=all_teams)
    except Exception as e:
        logging.error(f"Erro na rota /admin/teams: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@app.route('/admin/teams/delete/<int:team_id>', methods=['POST'])
@login_required
def admin_delete_team(team_id):
    try:
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        team_to_delete = Team.query.get_or_404(team_id)
        for member in team_to_delete.members:
            member.team_id = None
        db.session.delete(team_to_delete)
        db.session.commit()
        flash(f'O time "{team_to_delete.name}" foi dissolvido.', 'success')
        return redirect(url_for('admin_teams'))
    except Exception as e:
        logging.error(f"Erro na rota /admin/teams/delete/{team_id}: {str(e)}", exc_info=True)
        return "Erro interno do servidor", 500

@click.command(name='create-admin')
@with_appcontext
@click.option('--name', required=True, help='O nome do administrador.')
@click.option('--email', required=True, help='O email do administrador.')
@click.option('--password', required=True, help='A senha do administrador.')
def create_admin(name, email, password):
    try:
        if User.query.filter_by(email=email).first():
            print(f"Erro: O email '{email}' já existe.")
            return
        initial_level = Level.query.filter_by(name='Iniciante').first()
        if not initial_level:
            print("Erro: Nível 'Iniciante' não encontrado.")
            return
        hashed_password = generate_password_hash(password)
        admin_user = User(
            name=name,
            email=email,
            password=hashed_password,
            is_admin=True,
            level_id=initial_level.id
        )
        db.session.add(admin_user)
        db.session.commit()
        print(f"Administrador '{name}' criado com sucesso!")
    except Exception as e:
        logging.error(f"Erro ao criar administrador: {str(e)}", exc_info=True)
        print(f"Erro ao criar administrador: {str(e)}")

@app.cli.command("init-db")
@with_appcontext
def init_db_command():
    """Cria as tabelas do banco de dados e semeia os dados iniciais."""
    db.create_all()
    try:
        categories = ['Hardware', 'Software', 'Rede', 'Outros', 'Mobile', 'Automation']
        for category_name in categories:
            if not Category.query.filter_by(name=category_name).first():
                category = Category(name=category_name)
                db.session.add(category)
        
        if Level.query.count() == 0:
            logging.info("A semear os níveis iniciais na base de dados...")
            levels_to_seed = [
                Level(name='Iniciante', min_points=0, insignia_image_url='beginner.svg'),
                Level(name='Dados de Prata', min_points=50, insignia_image_url='silver.svg'),
                Level(name='Dados de Ouro', min_points=150, insignia_image_url='gold.svg'),
                Level(name='Mestre dos Dados', min_points=300, insignia_image_url='master.svg')
            ]
            db.session.bulk_save_objects(levels_to_seed)
        
        db.session.commit()
        print("Banco de dados inicializado e dados semeados com sucesso!")
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao semear dados: {e}")

app.cli.add_command(create_admin)
app.cli.add_command(init_db_command)