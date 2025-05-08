from flask import Flask, request, render_template, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import logging
import json
import csv
from io import StringIO
from sqlalchemy.exc import OperationalError

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://sdeskdb_user:urrIL42GcKewOyEQDey6KKNcas8NLH2x@dpg-d0dsicndiees73a8op40-a/sdeskdb')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
db = SQLAlchemy(app)

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modelos do Banco de Dados
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class FAQ(db.Model):
    __tablename__ = 'faq'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.Text, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except OperationalError as e:
        logger.error(f"Erro ao carregar usuário: {e}")
        return None

# Manipulador de erros 500
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erro interno: {error}")
    return "Erro interno do servidor. Por favor, tente novamente mais tarde.", 500

# Rotas de Autenticação
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                flash('Login realizado com sucesso!', 'success')
                return redirect(url_for('index'))
            flash('Email ou senha incorretos.', 'error')
        except OperationalError as e:
            logger.error(f"Erro ao fazer login: {e}")
            flash('Erro ao acessar o banco de dados. Tente novamente mais tarde.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        try:
            if User.query.filter_by(email=email).first():
                flash('Email já cadastrado.', 'error')
                return render_template('register.html')
            new_user = User(name=name, email=email, password=generate_password_hash(password), is_admin=is_admin)
            db.session.add(new_user)
            db.session.commit()
            flash('Cadastro realizado com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
        except OperationalError as e:
            logger.error(f"Erro ao registrar usuário: {e}")
            flash('Erro ao acessar o banco de dados. Tente novamente mais tarde.', 'error')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user)

@app.route('/admin/faq', methods=['GET', 'POST'])
@login_required
def admin_faq():
    if not current_user.is_admin:
        flash('Você não tem permissão para acessar esta página.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        if 'add_question' in request.form:
            question = request.form.get('question')
            answer = request.form.get('answer')
            if question and answer:
                try:
                    new_faq = FAQ(question=question, answer=answer)
                    db.session.add(new_faq)
                    db.session.commit()
                    flash('FAQ adicionada com sucesso!', 'success')
                except OperationalError as e:
                    logger.error(f"Erro ao adicionar FAQ: {e}")
                    flash('Erro ao acessar o banco de dados. Tente novamente mais tarde.', 'error')
            else:
                flash('Preencha todos os campos.', 'error')
        elif 'import_faqs' in request.form and 'faq_file' in request.files:
            file = request.files['faq_file']
            if file.filename == '':
                flash('Nenhum arquivo selecionado.', 'error')
            elif file and (file.filename.endswith('.json') or file.filename.endswith('.csv')):
                try:
                    if file.filename.endswith('.json'):
                        faqs = json.load(file)
                        for faq in faqs:
                            if 'question' in faq and 'answer' in faq:
                                new_faq = FAQ(question=faq['question'], answer=faq['answer'])
                                db.session.add(new_faq)
                    elif file.filename.endswith('.csv'):
                        csv_data = file.read().decode('utf-8')
                        csv_reader = csv.DictReader(StringIO(csv_data))
                        for row in csv_reader:
                            if 'question' in row and 'answer' in row:
                                new_faq = FAQ(question=row['question'], answer=row['answer'])
                                db.session.add(new_faq)
                    db.session.commit()
                    flash('FAQs importadas com sucesso!', 'success')
                except Exception as e:
                    logger.error(f"Erro ao importar FAQs: {e}")
                    flash('Erro ao importar FAQs. Verifique o formato do arquivo.', 'error')
            else:
                flash('Formato de arquivo não suportado. Use JSON ou CSV.', 'error')
    try:
        faqs = FAQ.query.all()
    except OperationalError as e:
        logger.error(f"Erro ao listar FAQs: {e}")
        flash('Erro ao acessar o banco de dados. Tente novamente mais tarde.', 'error')
        faqs = []
    return render_template('admin_faq.html', faqs=faqs)

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    mensagem = data.get('mensagem', '').lower()
    # Simulação de comportamento de IA
    try:
        # Procurar resposta em FAQs
        faqs = FAQ.query.all()
        for faq in faqs:
            if faq.question.lower() in mensagem:
                return jsonify({'resposta': faq.answer})
        
        # Comandos específicos
        if 'encerrar chamado' in mensagem:
            try:
                numero_chamado = mensagem.split('encerrar chamado ')[1].strip()
                return jsonify({'resposta': f'Chamado {numero_chamado} encerrado com sucesso!'})
            except IndexError:
                return jsonify({'resposta': 'Por favor, forneça o número do chamado. Exemplo: "Encerrar chamado 12345"'})
        elif 'sugerir solução para' in mensagem:
            try:
                problema = mensagem.split('sugerir solução para ')[1].strip()
                faq_match = FAQ.query.filter(FAQ.question.ilike(f'%{problema}%')).first()
                if faq_match:
                    return jsonify({'resposta': faq_match.answer})
                return jsonify({'resposta': f'Sugestão para "{problema}": Verifique os cabos e a energia ou consulte o administrador.'})
            except IndexError:
                return jsonify({'resposta': 'Por favor, especifique o problema. Exemplo: "Sugerir solução para computador não liga"'})
        elif 'como configurar uma vpn' in mensagem:
            return jsonify({'resposta': 'Para configurar uma VPN, acesse as configurações de rede, selecione "Adicionar VPN", e insira as credenciais fornecidas pelo seu departamento de TI.'})
        return jsonify({'resposta': 'Desculpe, não entendi. Tente "Encerrar chamado <ID>", "Sugerir solução para <problema>", ou consulte as FAQs disponíveis.'})
    except Exception as e:
        logger.error(f"Erro ao processar mensagem de chat: {e}")
        return jsonify({'resposta': 'Erro ao processar sua solicitação. Tente novamente.'})

def init_db():
    """Inicializa o banco de dados com dados padrão."""
    with app.app_context():
        try:
            if not FAQ.query.first():
                faq_data = [
                    FAQ(question="computador não liga", answer="Verifique a energia e a fonte. Certifique-se de que o cabo de energia está conectado e tente reiniciar."),
                    FAQ(question="erro ao acessar sistema", answer="Reinicie o sistema e verifique suas credenciais. Se o problema persistir, contate o suporte de TI.")
                ]
                db.session.bulk_save_objects(faq_data)
                db.session.commit()
            logger.info("Banco de dados inicializado com sucesso!")
        except OperationalError as e:
            logger.error(f"Erro ao inicializar o banco de dados: {e}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas se não existirem
        init_db()
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))