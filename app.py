from flask import Flask, request, jsonify, render_template, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import re
from google.cloud import dialogflow

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sua-chave-secreta-aqui')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

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
    image_url = db.Column(db.String(500), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('faqs', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Função para formatar a resposta da FAQ
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

# Função para interagir com o Dialogflow
def detect_intent(project_id, session_id, text, language_code="pt-BR"):
    session_client = dialogflow.SessionsClient()
    session = session_client.session_path(project_id, session_id)
    text_input = dialogflow.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.QueryInput(text=text_input)
    response = session_client.detect_intent(request={"session": session, "query_input": query_input})
    return response.query_result.intent.display_name, dict(response.query_result.parameters)

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
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            next_page = request.args.get('next')
            flash('Login realizado com sucesso!', 'success')
            return redirect(next_page or url_for('index'))
        flash('Email ou senha inválidos.', 'error')
    return render_template('login.html')

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_message = request.form['message']
    project_id = "servicedeskbot-anki"  # Substitua pelo seu Project ID do Dialogflow
    session_id = str(current_user.id)  # Use o ID do usuário como session_id

    intent, params = detect_intent(project_id, session_id, user_message)
    
    response = {
        'text': "Desculpe, não entendi o comando. Tente 'Encerrar chamado <ID>', 'Sugerir solução para <problema>', ou faça uma pergunta!",
        'html': False,
        'state': 'normal',
        'options': []
    }

    if intent == "consult_faq":
        keyword = params.get("keyword", user_message.lower())
        faq = FAQ.query.filter(FAQ.question.ilike(f"%{keyword}%")).first()
        if faq:
            response['text'] = format_faq_response(faq.question, faq.answer, faq.image_url)
            response['html'] = True
        else:
            response['text'] = "Desculpe, não encontrei uma FAQ para isso. Tente reformular sua pergunta!"
    elif intent == "saudacao":
        response['text'] = "Olá! Como posso ajudar você hoje?"
    elif intent == "ajuda":
        response['text'] = "Eu posso ajudar com perguntas sobre hardware, software, rede e mais! Por exemplo, você pode perguntar: 'Como configurar uma impressora?' ou 'O que fazer se o computador não liga?'."
    else:
        ticket_response = process_ticket_command(user_message)
        if ticket_response:
            response['text'] = ticket_response
        else:
            solution_response = suggest_solution(user_message)
            if solution_response:
                response['text'] = solution_response
            else:
                faq_matches = find_faq_by_keywords(user_message)
                if faq_matches:
                    if len(faq_matches) == 1:
                        faq = faq_matches[0]
                        response['text'] = format_faq_response(faq.question, faq.answer, faq.image_url)
                        response['html'] = True
                    else:
                        faq_ids = [faq.id for faq in faq_matches]
                        session['faq_selection'] = faq_ids
                        response['state'] = 'faq_selection'
                        response['text'] = "Encontrei várias FAQs relacionadas. Clique na que você deseja:"
                        response['html'] = True
                        response['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches]
                else:
                    response['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta ou consulte a página de FAQs."

    return jsonify(response)

# Outras rotas (mantidas como no código original)
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
        flash('FAQ excluída com sucesso!', 'success')
    else:
        flash('Acesso negado. Apenas administradores podem excluir FAQs.', 'error')
    return redirect(url_for('faqs'))

with app.app_context():
    db.create_all()
    categories = ['Hardware', 'Software', 'Rede', 'Outros']
    for category_name in categories:
        if not Category.query.filter_by(name=category_name).first():
            category = Category(name=category_name)
            db.session.add(category)
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)