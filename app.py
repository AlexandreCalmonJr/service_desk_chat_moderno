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

class FAQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(200), nullable=False)
    answer = db.Column(db.Text, nullable=False)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.String(20), default='Aberto')
    description = db.Column(db.Text)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Inicialização do banco de dados
with app.app_context():
     db.create_all()

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

def find_faq_by_keywords(message):
    words = re.findall(r'\w+', message.lower())
    for word in words:
        faq = FAQ.query.filter(FAQ.question.ilike(f'%{word}%')).first()
        if faq:
            return faq.question, faq.answer
    return None, None

# Rotas
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
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
        is_admin = 'is_admin' in request.form
        if User.query.filter_by(email=email).first():
            flash('Email já registrado.', 'error')
        else:
            user = User(name=name, email=email, password=password, is_admin=is_admin)
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
        'options': [
            {'text': 'Encerrar Chamado', 'action': 'prompt', 'value': 'Encerrar chamado '},
            {'text': 'Sugerir Solução', 'action': 'prompt', 'value': 'Sugerir solução para '},
            {'text': 'Ver FAQs', 'action': 'link', 'value': '/admin/faq'}
        ],
        'html': False
    }

    # Processar comandos
    ticket_response = process_ticket_command(mensagem)
    if ticket_response:
        resposta['text'] = ticket_response
        resposta['options'] = [
            {'text': 'Voltar ao Chat', 'action': 'link', 'value': '/'},
            {'text': 'Encerrar Outro Chamado', 'action': 'prompt', 'value': 'Encerrar chamado '}
        ]
    else:
        solution_response = suggest_solution(mensagem)
        if solution_response:
            resposta['text'] = solution_response
            resposta['options'] = [
                {'text': 'Voltar ao Chat', 'action': 'link', 'value': '/'},
                {'text': 'Sugerir Outra Solução', 'action': 'prompt', 'value': 'Sugerir solução para '}
            ]
        else:
            # Buscar FAQ por palavras-chave
            question, answer = find_faq_by_keywords(mensagem)
            if question and answer:
                resposta['text'] = f"<strong>Pergunta:</strong> {question}<br><strong>Resposta:</strong> {answer}"
                resposta['html'] = True
                resposta['options'] = [
                    {'text': 'Voltar ao Chat', 'action': 'link', 'value': '/'},
                    {'text': 'Fazer Outra Pergunta', 'action': 'prompt', 'value': ''}
                ]
            else:
                # Sugestão de FAQs relevantes
                faqs = FAQ.query.limit(3).all()
                if faqs:
                    options = [f'<strong>{faq.question}</strong><br>{faq.answer}<br>' for faq in faqs]
                    resposta['text'] = "Aqui estão algumas FAQs que podem ajudar:<br>" + "<br><br>".join(options)
                    resposta['html'] = True
                    resposta['options'] = [
                        {'text': 'Fazer Pergunta', 'action': 'prompt', 'value': ''},
                        {'text': 'Ver Todas FAQs', 'action': 'link', 'value': '/admin/faq'}
                    ]

    return jsonify(resposta)

@app.route('/admin/faq', methods=['GET', 'POST'])
@login_required
def admin_faq():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem gerenciar FAQs.', 'error')
        return redirect(url_for('index'))
    
    faqs = FAQ.query.all()
    if request.method == 'POST':
        if 'add_question' in request.form:
            question = request.form['question']
            answer = request.form['answer']
            if question and answer:
                faq = FAQ(question=question, answer=answer)
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
                            faq = FAQ(question=item.get('question'), answer=item.get('answer', ''))
                            db.session.add(faq)
                elif file.filename.endswith('.csv'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            faq = FAQ(question=row.get('question'), answer=row.get('answer', ''))
                            db.session.add(faq)
                elif file.filename.endswith('.pdf'):
                    faqs_extracted = extract_faqs_from_pdf(file_path)
                    for faq in faqs_extracted:
                        if faq['question'] and faq['answer']:
                            new_faq = FAQ(question=faq['question'], answer=faq['answer'])
                            db.session.add(new_faq)
                db.session.commit()
                flash('FAQs importadas com sucesso!', 'success')
                os.remove(file_path)
            else:
                flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
    return render_template('admin_faq.html', faqs=faqs)

if __name__ == '__main__':
    app.run(debug=True)