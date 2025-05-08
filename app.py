from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
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

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///service_desk.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
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
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class FAQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(200), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)  # Novo campo para URL da imagem
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
            faqs.append({"question": question, "answer": answer, "image_url": None})  # PDF não suporta imagens diretamente
        return faqs
    except Exception as e:
        flash(f"Erro ao processar o PDF: {str(e)}", 'error')
        return []

def format_faq_response(question, answer, image_url=None):
    sections = re.split(r'(Pré-requisitos:|Etapa \d+:|Atenção:|Finalizar:|Pós-instalação:)', answer)
    formatted_response = f"<strong>Pergunta:</strong> {question}<br><br>"

    current_section = None
    for part in sections:
        part = part.strip()
        if not part:
            continue
        if part.startswith("Pré-requisitos:"):
            current_section = "Pré-requisitos"
            formatted_response += "<strong>✅ Pré-requisitos</strong><br>"
        elif part.startswith("Etapa"):
            current_section = "Etapa"
            formatted_response += f"<strong>🔧 {part}</strong><br>"
        elif part.startswith("Atenção:"):
            current_section = "Atenção"
            formatted_response += "<strong>⚠️ Atenção</strong><br>"
        elif part.startswith("Finalizar:"):
            current_section = "Finalizar"
            formatted_response += "<strong>⏳ Finalizar</strong><br>"
        elif part.startswith("Pós-instalação:"):
            current_section = "Pós-instalação"
            formatted_response += "<strong>✅ Pós-instalação</strong><br>"
        else:
            if current_section:
                items = re.split(r'[,.]\s*(?=[A-Z])', part)
                for item in items:
                    item = item.strip()
                    if item:
                        formatted_response += f"{item}<br>"
            formatted_response += "<br>"

    # Adicionar a imagem, se existir
    if image_url:
        formatted_response += f'<img src="{image_url}" alt="Imagem da FAQ" style="max-width: 100%; height: auto; margin-top: 10px;"><br>'

    return formatted_response

def find_faq_by_keywords(message):
    words = re.findall(r'\w+', message.lower())
    faqs = FAQ.query.all()
    matches = []

    for faq in faqs:
        score = 0
        question_text = faq.question.lower()
        answer_text = faq.answer.lower()
        combined_text = question_text + " " + answer_text

        for word in words:
            if word in combined_text:
                score += 1

        if score > 0:
            matches.append((faq, score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches] if matches else []

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

    # Verificar se o usuário está selecionando uma FAQ
    if 'faq_selection' in session and mensagem.startswith('faq_'):
        faq_id = mensagem.replace('faq_', '')
        faq_ids = session.get('faq_selection', [])
        if int(faq_id) in faq_ids:
            selected_faq = FAQ.query.get(int(faq_id))
            if selected_faq:
                resposta['text'] = format_faq_response(selected_faq.question, selected_faq.answer, selected_faq.image_url)
                resposta['html'] = True
                # Reenviar as opções para o frontend
                faq_matches = FAQ.query.filter(FAQ.id.in_(faq_ids)).all()
                resposta['state'] = 'faq_selection'
                resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches]
                return jsonify(resposta)
        resposta['text'] = "Opção inválida. Por favor, escolha uma FAQ ou faça uma nova pergunta."
        return jsonify(resposta)

    # Processar comandos
    ticket_response = process_ticket_command(mensagem)
    if ticket_response:
        resposta['text'] = ticket_response
    else:
        solution_response = suggest_solution(mensagem)
        if solution_response:
            resposta['text'] = solution_response
        else:
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
                resposta['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta ou consulte a página de FAQs."
                resposta['html'] = False

    return jsonify(resposta)

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
            image_url = request.form.get('image_url')  # Novo campo no formulário
            if category_id and question and answer:
                faq = FAQ(category_id=category_id, question=question, answer=answer, image_url=image_url)
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
                                image_url = item.get('image_url')  # Novo campo no JSON
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
                                    image_url=row.get('image_url')  # Novo campo no CSV
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
                    flash('FAQs importadas com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                finally:
                    os.remove(file_path)
            else:
                flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
    return render_template('admin_faq.html', categories=categories)

if __name__ == '__main__':
    app.run(debug=True)