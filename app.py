from flask import Flask, request, jsonify, render_template, flash, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_caching import Cache
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import re
import unicodedata
from PyPDF2 import PdfReader
from datetime import datetime
import difflib
import nltk
from nltk.corpus import stopwords
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Baixar stop words do NLTK
try:
    nltk.download('stopwords', quiet=True)
    stop_words = set(stopwords.words('portuguese'))
except Exception as e:
    logger.warning(f"Erro ao baixar stop words do NLTK: {str(e)}. Usando conjunto vazio.")
    stop_words = set()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_timeout': 30,
    'pool_recycle': 1800,
    'pool_pre_ping': True
}
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['CACHE_TYPE'] = 'SimpleCache'  # Cache em memória
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutos

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

db = SQLAlchemy(app)
cache = Cache(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Modelos
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(20))
    registered_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    last_login = db.Column(db.DateTime)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class FAQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(200), nullable=False, index=True)
    answer = db.Column(db.Text, nullable=False, index=True)
    image_url = db.Column(db.String(500), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('faqs', lazy=True))

    @property
    def formatted_answer(self):
        return format_faq_response(self.question, self.answer, self.image_url)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.String(20), default='Aberto')
    description = db.Column(db.Text)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Inicialização do banco de dados e categorias padrão
with app.app_context():
    db.create_all()
    categories = ['Hardware', 'Software', 'Rede', 'Outros']
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
            faqs.append({"question": question, "answer": answer, "image_url": None})
        return faqs
    except Exception as e:
        flash(f"Erro ao processar o PDF: {str(e)}", 'error')
        return []

def format_faq_response(question, answer, image_url=None):
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
    
    if image_url:
        formatted_response += f'<img src="{image_url}" alt="Imagem da FAQ" style="max-width: 100%; height: auto; margin-top: 10px;"><br>'
    if formatted_response.endswith("<br>") and image_url:
        formatted_response = formatted_response[:-4]
    
    return formatted_response

def normalize_text(text):
    # Normalizar texto: remover acentos, converter para minúsculas
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text.lower()

@cache.memoize(timeout=300)
def find_faq_by_keywords(message):
    try:
        # Normalizar a mensagem do usuário
        normalized_message = normalize_text(message)
        # Pré-processar a mensagem: remover stop words e converter para minúsculas
        words = re.findall(r'\w+', normalized_message)
        filtered_words = [word for word in words if word not in stop_words and len(word) > 2]  # Ignorar palavras muito curtas

        if not filtered_words:
            return []

        # Construir uma consulta SQL para buscar FAQs que contenham pelo menos uma palavra-chave
        query = db.session.query(FAQ)
        for word in filtered_words:
            like_pattern = f"%{word}%"
            query = query.filter(db.or_(
                FAQ.question.ilike(like_pattern),
                FAQ.answer.ilike(like_pattern)
            ))

        # Executar a consulta com retry em caso de falha
        max_retries = 3
        for attempt in range(max_retries):
            try:
                faqs = query.all()
                break
            except Exception as e:
                logger.error(f"Tentativa {attempt + 1} falhou: {str(e)}")
                if attempt == max_retries - 1:
                    raise Exception("Falha ao acessar o banco de dados após várias tentativas.")
                continue

        if not faqs:
            return []

        # Calcular similaridade entre a mensagem e as perguntas das FAQs
        matches = []
        for faq in faqs:
            normalized_question = normalize_text(faq.question)
            normalized_answer = normalize_text(faq.answer)
            question_similarity = difflib.SequenceMatcher(None, normalized_message, normalized_question).ratio()
            answer_similarity = difflib.SequenceMatcher(None, normalized_message, normalized_answer).ratio()
            # Ponderar mais a similaridade da pergunta
            score = (question_similarity * 0.7) + (answer_similarity * 0.3)
            matches.append((faq, score))

        # Ordenar por pontuação de similaridade
        matches.sort(key=lambda x: x[1], reverse=True)

        # Retornar as FAQs (limitando a 10 resultados para evitar sobrecarga)
        return [match[0] for match in matches[:10]]

    except Exception as e:
        logger.error(f"Erro ao buscar FAQs: {str(e)}")
        return []

# Rotas
@app.route('/')
@login_required
def index():
    session.pop('faq_selection', None)
    return render_template('index.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.phone = request.form.get('phone')
        db.session.commit()
        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html')

@app.route('/faqs')
@login_required
def faqs():
    faqs = FAQ.query.all()
    categories = Category.query.all()
    return render_template('faqs.html', faqs=faqs, categories=categories)

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
        is_admin = 'is_admin' in request.form
        if User.query.filter_by(email=email).first():
            flash('Email já registrado.', 'error')
        else:
            user = User(name=name, email=email, password=password, phone=phone, is_admin=is_admin)
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
        'text': "Desculpe, não entendi o comando. Tente 'Encerrar chamado <ID>', 'Sugerir solução para <problema>', ou faça uma pergunta!",
        'html': False,
        'state': 'normal',
        'options': []
    }

    if 'faq_selection' in session and mensagem.startswith('faq_'):
        faq_id = mensagem.replace('faq_', '')
        faq_ids = session.get('faq_selection', [])
        if int(faq_id) in faq_ids:
            selected_faq = FAQ.query.get(int(faq_id))
            if selected_faq:
                resposta['text'] = format_faq_response(selected_faq.question, selected_faq.answer, selected_faq.image_url)
                resposta['html'] = True
                faq_matches = FAQ.query.filter(FAQ.id.in_(faq_ids)).all()
                resposta['state'] = 'faq_selection'
                resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches]
                return jsonify(resposta)
        resposta['text'] = "Opção inválida. Por favor, escolha uma FAQ ou faça uma nova pergunta."
        return jsonify(resposta)

    ticket_response = process_ticket_command(mensagem)
    if ticket_response:
        resposta['text'] = ticket_response
    else:
        solution_response = suggest_solution(mensagem)
        if solution_response:
            resposta['text'] = solution_response
        else:
            try:
                faq_matches = find_faq_by_keywords(mensagem)
                if faq_matches:
                    if len(faq_matches) == 1:
                        faq = faq_matches[0]
                        resposta['text'] = format_faq_response(faq.question, faq.answer, faq.image_url)
                        resposta['html'] = True
                    else:
                        faq_ids = [faq.id for faq in faq_matches]
                        session['faq_selection'] = faq_ids
                        resposta['state'] = 'faq_selection'
                        resposta['text'] = "Encontrei várias FAQs relacionadas. Clique na que você deseja:"
                        resposta['html'] = True
                        resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches]
                else:
                    resposta['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta ou consulte a página de FAQs!"
            except Exception as e:
                logger.error(f"Erro ao processar busca de FAQs: {str(e)}")
                resposta['text'] = "Desculpe, ocorreu um erro ao buscar FAQs. Tente novamente em alguns instantes."

    return jsonify(resposta)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'fulfillmentText': 'Erro: Dados inválidos'}), 400

    query_text = data['queryResult']['queryText']
    response_text = "Desculpe, não entendi. Tente novamente."

    try:
        faq_matches = find_faq_by_keywords(query_text)
        if faq_matches:
            faq = faq_matches[0]  # Pega o FAQ mais relevante
            response_text = format_faq_response(faq.question, faq.answer, faq.image_url)
        else:
            response_text = "Desculpe, não encontrei uma FAQ para isso. Tente reformular sua pergunta!"
    except Exception as e:
        logger.error(f"Erro no webhook: {str(e)}")
        response_text = "Desculpe, ocorreu um erro ao processar sua solicitação."

    return jsonify({
        'fulfillmentText': response_text
    })

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
            if category_id and question and answer:
                faq = FAQ(category_id=category_id, question=question, answer=answer, image_url=image_url)
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
                                if not category_name or not question:
                                    flash('Cada FAQ no JSON deve ter "category" e "question".', 'error')
                                    continue
                                category = Category.query.filter_by(name=category_name).first()
                                if not category:
                                    category = Category(name=category_name)
                                    db.session.add(category)
                                    db.session.commit()
                                faq = FAQ(category_id=category.id, question=question, answer=answer, image_url=image_url)
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
                                    image_url=row.get('image_url')
                                )
                                db.session.add(faq)
                    elif file.filename.endswith('.pdf'):
                        category_id = request.form['category_import']
                        faqs_extracted = extract_faqs_from_pdf(file_path)
                        for faq in faqs_extracted:
                            if faq['question'] and faq['answer']:
                                new_faq = FAQ(category_id=category_id, question=faq['question'], answer=faq['answer'], image_url=None)
                                db.session.add(new_faq)
                    db.session.commit()
                    cache.clear()
                    flash('FAQs importadas com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                finally:
                    os.remove(file_path)
            else:
                flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
    return render_template('admin_faq.html', categories=categories)

@app.route('/faqs/delete/<int:faq_id>', methods=['POST'])
@login_required
def delete_faq(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    if current_user.is_admin:
        db.session.delete(faq)
        db.session.commit()
        cache.clear()
        flash('FAQ excluída com sucesso!', 'success')
    else:
        flash('Acesso negado. Apenas administradores podem excluir FAQs.', 'error')
    return redirect(url_for('faqs'))

if __name__ == '__main__':
    app.run(debug=True)