from flask import Flask, request, jsonify, render_template, flash, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from werkzeug.utils import secure_filename
from google.cloud import dialogflow
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sua-chave-secreta-aqui')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Modelos
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    faqs = db.relationship('FAQ', backref='category', lazy=True)

class FAQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    question = db.Column(db.String(200), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    file_path = db.Column(db.String(500))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Função para formatar a resposta da FAQ (ajustada anteriormente)
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

# Rota para o chat com NLP
@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_message = request.form['message']
    project_id = "servicedeskbot-anki"  # Substitua pelo seu Project ID do Dialogflow
    session_id = str(current_user.id)  # Use o ID do usuário como session_id para manter contexto

    intent, params = detect_intent(project_id, session_id, user_message)
    
    if intent == "consult_faq":
        keyword = params.get("keyword", user_message.lower())
        faq = FAQ.query.filter(FAQ.question.ilike(f"%{keyword}%")).first()
        if faq:
            response = format_faq_response(faq.question, faq.answer, faq.image_url)
        else:
            response = "Desculpe, não encontrei uma FAQ para isso. Tente reformular sua pergunta!"
    elif intent == "saudacao":
        response = "Olá! Como posso ajudar você hoje?"
    elif intent == "ajuda":
        response = "Eu posso ajudar com perguntas sobre hardware, software, rede e mais! Por exemplo, você pode perguntar: 'Como configurar uma impressora?' ou 'O que fazer se o computador não liga?'."
    else:
        response = "Desculpe, não entendi. Pode reformular ou tentar algo como 'Como configurar uma impressora?'"

    return jsonify({"response": response})

# Rota Webhook para o Dialogflow (caso queira expandir para interações mais complexas)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    intent = data['queryResult']['intent']['displayName']
    params = data['queryResult']['parameters']

    if intent == "consult_faq":
        keyword = params.get("keyword", data['queryResult']['queryText'].lower())
        faq = FAQ.query.filter(FAQ.question.ilike(f"%{keyword}%")).first()
        if faq:
            response_text = format_faq_response(faq.question, faq.answer, faq.image_url)
        else:
            response_text = "Desculpe, não encontrei uma FAQ para isso. Tente reformular sua pergunta!"
    else:
        response_text = "Desculpe, não entendi. Pode reformular?"

    return jsonify({
        "fulfillmentText": response_text
    })

# Outras rotas (mantidas como estão, para referência)
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Usuário ou senha inválidos.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/faqs', methods=['GET'])
@login_required
def faqs():
    faqs = FAQ.query.all()
    return render_template('faqs.html', faqs=faqs)

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
            image_url = request.form['image_url'] if request.form['image_url'] else None
            file_path = None
            if 'file' in request.files:
                file = request.files['file']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            faq = FAQ(category_id=category_id, question=question, answer=answer, image_url=image_url, file_path=file_path)
            db.session.add(faq)
            db.session.commit()
            flash('FAQ adicionada com sucesso!', 'success')
        elif 'import_faqs' in request.form:
            file = request.files['faq_file']
            if file and file.filename.endswith('.json'):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for item in data:
                            category_name = item.get('category')
                            question = item.get('question')
                            answer = item.get('answer', '')
                            image_url = item.get('image_url')
                            if category_name and question:
                                category = Category.query.filter_by(name=category_name).first()
                                if not category:
                                    category = Category(name=category_name)
                                    db.session.add(category)
                                    db.session.commit()
                                faq = FAQ(category_id=category.id, question=question, answer=answer, image_url=image_url)
                                db.session.add(faq)
                        db.session.commit()
                        flash('FAQs importadas com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                finally:
                    os.remove(file_path)
            else:
                flash('Formato de arquivo inválido. Use apenas JSON.', 'error')
        return redirect(url_for('admin_faq'))
    return render_template('admin_faq.html', categories=categories)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)