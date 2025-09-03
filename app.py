from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_file
import io
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sentence_transformers import SentenceTransformer, util
import os
import csv
import json
import re
from PyPDF2 import PdfReader
from datetime import datetime
import torch


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')

# Configuração do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

try:
    semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
except Exception as e:
    print(f"Erro ao carregar o modelo de sentence-transformer: {e}")
    semantic_model = None

faq_embeddings = {}

# Configuração do spaCy


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
    faq = db.relationship('FAQ', backref=db.backref('chat_suggestions', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

def find_faq_by_semantic_similarity(user_message, threshold=0.6):
    """Encontra a FAQ mais relevante usando similaridade de cosseno."""
    if not semantic_model or not faq_embeddings:
        return []

    # Converte a mensagem do usuário em um vetor
    user_embedding = semantic_model.encode(user_message, convert_to_tensor=True)

    # Prepara os vetores das FAQs
    faq_ids = list(faq_embeddings.keys())
    corpus_embeddings = torch.stack(list(faq_embeddings.values()))

    # Calcula a similaridade de cosseno entre a pergunta do usuário e todas as FAQs
    cos_scores = util.pytorch_cos_sim(user_embedding, corpus_embeddings)[0]
    
    # Encontra os melhores resultados
    top_results = torch.topk(cos_scores, k=min(5, len(faq_ids)))

    matches = []
    for score, idx in zip(top_results[0], top_results[1]):
        if score >= threshold:
            faq_id = faq_ids[idx]
            faq = FAQ.query.get(faq_id)
            if faq:
                matches.append(faq)
    
    return matches

# Não se esqueça de atualizar a chamada na rota /chat:
# faq_matches = find_faq_by_semantic_similarity(mensagem)
def update_faq_embeddings():
    """Converte todas as FAQs do banco em vetores e armazena em memória."""
    global faq_embeddings
    if not semantic_model:
        print("Modelo semântico não carregado. Abortando a criação de embeddings.")
        return

    with app.app_context():
        faqs = FAQ.query.all()
        if faqs:
            # Converte as perguntas das FAQs em vetores
            questions = [faq.question for faq in faqs]
            embeddings = semantic_model.encode(questions, convert_to_tensor=True)
            
            # Mapeia o ID da FAQ para seu respectivo vetor
            faq_embeddings = {faqs[i].id: embeddings[i] for i in range(len(faqs))}
            print(f"{len(faq_embeddings)} embeddings de FAQs carregados.")

# Chame a função na inicialização do app
with app.app_context():
    update_faq_embeddings()

# Rotas
@app.route('/')
@login_required
def index():
    return render_template('index.html')

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
        phone = request.form.get('phone')
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
        'options': [],
        'message_id': None
    }
    
    chat_message = ChatMessage(user_id=current_user.id, user_message=mensagem)

    if 'faq_selection' in session and mensagem.startswith('faq_'):
        faq_id = mensagem.replace('faq_', '')
        faq_ids = session.get('faq_selection', [])
        if int(faq_id) in faq_ids:
            selected_faq = FAQ.query.get(int(faq_id))
            if selected_faq:
                resposta['text'] = format_faq_response(selected_faq.id, selected_faq.question, selected_faq.answer, selected_faq.image_url, selected_faq.video_url, selected_faq.file_name)
                resposta['html'] = True
                faq_matches = FAQ.query.filter(FAQ.id.in_(faq_ids)).all()
                resposta['state'] = 'faq_selection'
                resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches]
                return jsonify(resposta)
        resposta['text'] = "Opção inválida. Por favor, escolha uma FAQ ou faça uma nova mensagem."
        return jsonify(resposta)

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
                    resposta['text'] = format_faq_response(faq.id, faq.question, faq.answer, faq.image_url, faq.video_url, faq.file_name)
                    resposta['html'] = True
                else:
                    faq_ids = [faq.id for faq in faq_matches]
                    session['faq_selection'] = faq_ids
                    resposta['state'] = 'faq_selection'
                    resposta['text'] = "Encontrei várias FAQs relacionadas. Clique na que você deseja:"
                    resposta['html'] = True
                    resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches]
            else:
                if "windows" in mensagem.lower():
                    resposta['text'] = format_faq_response(
                        None,  # FAQ sem ID, pois é estática
                        "O que é o modo de segurança no Windows?",
                        "O Modo de Segurança no Windows é uma opção de inicialização que carrega apenas os drivers e serviços essenciais, útil para solucionar problemas. Para acessá-lo, reinicie o computador e pressione F8 antes do carregamento do sistema, ou configure nas Configurações de Inicialização Avançadas.",
                        None,
                        None,
                        None  # Sem arquivo associado
                    )
                    resposta['html'] = True
                else:
                    resposta['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta ou consulte a página de FAQs."
                    resposta['html'] = False
                    
        faq_matches = find_faq_by_keywords(mensagem) # Vamos substituir isso na próxima etapa
    
    if faq_matches:
        if len(faq_matches) == 1:
            faq = faq_matches[0]
            resposta['text'] = format_faq_response(faq.id, faq.question, faq.answer, faq.image_url, faq.video_url, faq.file_name)
            resposta['html'] = True
            chat_message.bot_response = faq.answer
            chat_message.faq_id_suggestion = faq.id
        else:
            # Lógica para múltiplas FAQs
            faq_ids = [faq.id for faq in faq_matches]
            session['faq_selection'] = faq_ids
            resposta['state'] = 'faq_selection'
            resposta['text'] = "Encontrei várias FAQs relacionadas. Clique na que você deseja:"
            resposta['html'] = True
            resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches]
            chat_message.bot_response = "Múltiplas FAQs encontradas."
    else:
        resposta['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta."
        chat_message.bot_response = resposta['text']

    
    resposta['message_id'] = chat_message.id               
    db.session.add(chat_message)
    db.session.commit()
    return jsonify(resposta)


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


if __name__ == '__main__':
    app.run(debug=True)