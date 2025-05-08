from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import csv
import json
import re
import uuid
from PyPDF2 import PdfReader
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')
if os.getenv('DATABASE_URL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL').replace("postgres://", "postgresql://")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///service_desk.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PDF_FOLDER'] = os.path.join('uploads', 'pdfs')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['PDF_FOLDER']):
    os.makedirs(app.config['PDF_FOLDER'])

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

chat_messages = []

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
    pdf_path = db.Column(db.String(200))

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.String(20), default='Aberto')
    description = db.Column(db.Text)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

try:
    with app.app_context():
        db.create_all()
        logger.info("Banco de dados inicializado com sucesso.")
except Exception as e:
    logger.error(f"Erro ao inicializar o banco de dados: {str(e)}")

def process_ticket_command(message):
    match = re.match(r"Encerrar chamado (\d+)", message, re.IGNORECASE)
    if match:
        ticket_id = match.group(1)
        ticket = Ticket.query.filter_by(ticket_id=ticket_id).first()
        if ticket:
            if ticket.status == 'Aberto':
                ticket.status = 'Fechado'
                try:
                    db.session.commit()
                    logger.info(f"Chamado {ticket_id} encerrado com sucesso.")
                    return f"Chamado {ticket_id} encerrado com sucesso."
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Erro ao encerrar chamado {ticket_id}: {str(e)}")
                    return "Erro ao encerrar o chamado."
            else:
                return f"Chamado {ticket_id} já está fechado."
        return f"Chamado {ticket_id} não encontrado."
    return None

def suggest_solution(message):
    match = re.match(r"Sugerir solução para (.+)", message, re.IGNORECASE)
    if match:
        problem = match.group(1).lower()
        solutions = {
            "computador não liga": "Verifique a fonte de energia e reinicie o dispositivo.",
            "internet lenta": "Reinicie o roteador e verifique a conexão.",
            "configurar uma vpn": "Acesse as configurações de rede e insira as credenciais da VPN fornecidas pelo TI."
        }
        return solutions.get(problem, "Desculpe, não tenho uma solução para esse problema no momento.")
    return None

def search_faq(query):
    faqs = FAQ.query.all()
    query_words = set(query.lower().split())  # Usar set para remover duplicatas
    best_match = None
    best_score = 0

    logger.debug(f"Buscando FAQ para query: {query}")
    logger.debug(f"Palavras da query: {query_words}")
    logger.debug(f"FAQs disponíveis: {[(faq.question, faq.answer) for faq in faqs]}")

    for faq in faqs:
        faq_question_words = set(faq.question.lower().split())
        # Calcular a interseção entre as palavras da query e da FAQ
        common_words = query_words.intersection(faq_question_words)
        score = len(common_words)
        logger.debug(f"FAQ: {faq.question}, Palavras em comum: {common_words}, Score: {score}")

        # Relaxar a condição para considerar FAQs com pelo menos uma palavra em comum
        if score > 0 and score > best_score:
            best_score = score
            best_match = faq

    if best_match:
        logger.info(f"FAQ encontrada: {best_match.question} (Score: {best_score})")
        if best_match.pdf_path:
            return f"Encontrei uma FAQ relacionada: <a href='/view_pdf/{best_match.id}' target='_blank'>**{best_match.question}**</a>\nResposta: {best_match.answer}"
        return f"Encontrei uma FAQ relacionada: **{best_match.question}**\nResposta: {best_match.answer}"
    else:
        logger.info("Nenhuma FAQ encontrada.")
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

@app.route('/')
@login_required
def index():
    if not chat_messages:
        chat_messages.append({"texto": "Sou seu assistente de Service Desk. Como posso ajudar hoje? Tente 'Encerrar chamado <ID>', 'Sugerir solução para <problema>', ou faça uma pergunta qualquer para buscar uma FAQ, como 'Manual do Totem'.", "tipo": "bot"})
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
            try:
                db.session.commit()
                logger.info(f"Usuário {email} registrado com sucesso.")
                flash('Registro concluído! Faça login.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Erro ao registrar usuário {email}: {str(e)}")
                flash('Erro ao registrar usuário.', 'error')
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
    global chat_messages
    data = request.get_json()
    mensagem = data.get('mensagem', '').strip()
    resposta = "Desculpe, não entendi o comando. Tente 'Encerrar chamado <ID>', 'Sugerir solução para <problema>', ou faça uma pergunta qualquer para buscar uma FAQ, como 'Manual do Totem'."

    chat_messages.append({"texto": mensagem, "tipo": "user"})

    ticket_response = process_ticket_command(mensagem)
    if ticket_response:
        resposta = ticket_response
    else:
        solution_response = suggest_solution(mensagem)
        if solution_response:
            resposta = solution_response
        else:
            faq_response = search_faq(mensagem)
            if faq_response:
                resposta = faq_response

    chat_messages.append({"texto": resposta, "tipo": "bot"})

    return jsonify({'resposta': resposta, 'mensagens': chat_messages})

@app.route('/admin/faq', methods=['GET', 'POST'])
@login_required
def admin_faq():
    global chat_messages
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
                try:
                    db.session.commit()
                    logger.info(f"FAQ adicionada: {question}")
                    flash('FAQ adicionada com sucesso!', 'success')
                    chat_messages.append({"texto": f"Nova FAQ adicionada: **{question}**\n{answer}", "tipo": "bot"})
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Erro ao adicionar FAQ: {str(e)}")
                    flash('Erro ao adicionar FAQ.', 'error')
            else:
                flash('Preencha todos os campos.', 'error')
        elif 'import_faqs' in request.form:
            file = request.files['faq_file']
            if file and file.filename.endswith(('.json', '.csv', '.pdf')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                pdf_path = None
                if file.filename.endswith('.pdf'):
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    pdf_path = os.path.join(app.config['PDF_FOLDER'], unique_filename)
                    file.save(pdf_path)
                else:
                    file.save(file_path)
                try:
                    if file.filename.endswith('.json'):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            for item in data:
                                faq = FAQ(question=item.get('question'), answer=item.get('answer', ''), pdf_path=pdf_path if file.filename.endswith('.pdf') else None)
                                db.session.add(faq)
                                chat_messages.append({"texto": f"FAQ importada: **{item.get('question')}**\n{item.get('answer', '')}", "tipo": "bot"})
                    elif file.filename.endswith('.csv'):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                faq = FAQ(question=row.get('question'), answer=row.get('answer', ''), pdf_path=pdf_path if file.filename.endswith('.pdf') else None)
                                db.session.add(faq)
                                chat_messages.append({"texto": f"FAQ importada: **{row.get('question')}**\n{row.get('answer', '')}", "tipo": "bot"})
                    elif file.filename.endswith('.pdf'):
                        faqs_extracted = extract_faqs_from_pdf(file_path)
                        for faq in faqs_extracted:
                            if faq['question'] and faq['answer']:
                                new_faq = FAQ(question=faq['question'], answer=faq['answer'], pdf_path=pdf_path)
                                db.session.add(new_faq)
                                chat_messages.append({"texto": f"FAQ importada do PDF '{filename}': <a href='/view_pdf/{new_faq.id}' target='_blank'>**{faq['question']}**</a>\n{faq['answer']}", "tipo": "bot"})
                    db.session.commit()
                    logger.info(f"FAQs importadas do arquivo {filename}")
                    flash('FAQs importadas com sucesso!', 'success')
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Erro ao importar FAQs do arquivo {filename}: {str(e)}")
                    flash('Erro ao importar FAQs.', 'error')
                finally:
                    if not file.filename.endswith('.pdf'):
                        os.remove(file_path)
            else:
                flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
    return render_template('admin_faq.html', faqs=faqs)

@app.route('/admin/faq/delete/<int:faq_id>', methods=['POST'])
@login_required
def delete_faq(faq_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir FAQs.', 'error')
        return redirect(url_for('admin_faq'))
    
    faq = FAQ.query.get_or_404(faq_id)
    try:
        if faq.pdf_path and os.path.exists(faq.pdf_path):
            os.remove(faq.pdf_path)
        db.session.delete(faq)
        db.session.commit()
        logger.info(f"FAQ ID {faq_id} excluída com sucesso.")
        flash('FAQ excluída com sucesso!', 'success')
        chat_messages.append({"texto": f"FAQ '{faq.question}' foi excluída.", "tipo": "bot"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir FAQ ID {faq_id}: {str(e)}")
        flash('Erro ao excluir FAQ.', 'error')
    return redirect(url_for('admin_faq'))

@app.route('/view_pdf/<int:faq_id>')
@login_required
def view_pdf(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    if faq.pdf_path and os.path.exists(faq.pdf_path):
        return send_from_directory(app.config['PDF_FOLDER'], os.path.basename(faq.pdf_path))
    flash('Arquivo PDF não encontrado.', 'error')
    return redirect(url_for('admin_faq'))

if __name__ == '__main__':
    app.run(debug=True)