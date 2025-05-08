from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
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
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('faqs', lazy=True))

    @property
    def formatted_answer(self):
        return format_faq_response(self.question, self.answer)

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
            faqs.append({"question": question, "answer": answer})
        return faqs
    except Exception as e:
        flash(f"Erro ao processar o PDF: {str(e)}", 'error')
        return []

def format_faq_response(question, answer):
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

    return formatted_response

def find_faq_by_keywords(message):
    words = re.findall(r'\w+', message.lower())
    faqs = FAQ.query.all()
    best_match = None
    best_score = 0

    for faq in faqs:
        score = 0
        question_text = faq.question.lower()
        answer_text = faq.answer.lower()
        combined_text = question_text + " " + answer_text

        for word in words:
            if word in combined_text:
                score += 1

        if score > best_score:
            best_score = score
            best_match = (faq.question, faq.answer)

    return best_match if best_score > 0 else (None, None)

# Rotas
@app.route('/')
@login_required
def index():
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
        'html': False
    }

    ticket_response = process_ticket_command(mensagem)
    if ticket_response:
        resposta['text'] = ticket_response
    else:
        solution_response = suggest_solution(mensagem)
        if solution_response:
            resposta['text'] = solution_response
        else:
            question, answer = find_faq_by_keywords(mensagem)
            if question and answer:
                formatted_response = format_faq_response(question, answer)
                resposta['text'] = formatted_response
                resposta['html'] = True
            else:
                faqs = FAQ.query.limit(3).all()
                if faqs:
                    options = [format_faq_response(faq.question, faq.answer) for faq in faqs]
                    resposta['text'] = "Aqui estão algumas FAQs que podem ajudar:<br>" + "<br><br>".join(options)
                    resposta['html'] = True

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
            if category_id and question and answer:
                faq = FAQ(category_id=category_id, question=question, answer=answer)
                db.session.add(faq)
                db.session.commit()
                flash('FAQ adicionada com sucesso!', 'success')
            else:
                flash('Preencha todos os campos.', 'error')
        elif 'import_faqs' in request.form:
            file = request.files['faq_file']
            if file and file.filename.endswith(('.json', '.csv', '.pdf')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                if file.filename.endswith('.json'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for item in data:
                            category_name = item.get('category')
                            category = Category.query.filter_by(name=category_name).first()
                            if not category:
                                category = Category(name=category_name)
                                db.session.add(category)
                                db.session.commit()
                            faq = FAQ(category_id=category.id, question=item.get('question'), answer=item.get('answer', ''))
                            db.session.add(faq)
                elif file.filename.endswith('.csv'):
                    category_id = request.form['category_import']
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            faq = FAQ(category_id=category_id, question=row.get('question'), answer=row.get('answer', ''))
                            db.session.add(faq)
                elif file.filename.endswith('.pdf'):
                    category_id = request.form['category_import']
                    faqs_extracted = extract_faqs_from_pdf(file_path)
                    for faq in faqs_extracted:
                        if faq['question'] and faq['answer']:
                            new_faq = FAQ(category_id=category_id, question=faq['question'], answer=faq['answer'])
                            db.session.add(new_faq)
                db.session.commit()
                flash('FAQs importadas com sucesso!', 'success')
                os.remove(file_path)
            else:
                flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
    return render_template('admin_faq.html', categories=categories)

if __name__ == '__main__':
    app.run(debug=True)