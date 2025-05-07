from flask import Flask, request, render_template, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql+psycopg://sdeskdb_user:urrIL42GcKewOyEQDey6KKNcas8NLH2x@dpg-d0dsicndiees73a8op40-a/sdeskdb')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configurar Flask-Migrate
migrate = Migrate(app, db)

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
    return User.query.get(int(user_id))

# Rotas de Autenticação
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        flash('Email ou senha incorretos.', 'error')
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
        if User.query.filter_by(email=email).first():
            flash('Email já cadastrado.', 'error')
            return render_template('register.html')
        new_user = User(name=name, email=email, password=generate_password_hash(password), is_admin=is_admin)
        db.session.add(new_user)
        db.session.commit()
        flash('Cadastro realizado com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))
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
                new_faq = FAQ(question=question, answer=answer)
                db.session.add(new_faq)
                db.session.commit()
                flash('FAQ adicionada com sucesso!', 'success')
            else:
                flash('Preencha todos os campos.', 'error')
    faqs = FAQ.query.all()
    return render_template('admin_faq.html', faqs=faqs)

def init_db():
    """Inicializa o banco de dados com dados padrão."""
    with app.app_context():
        if not FAQ.query.first():
            faq_data = [
                FAQ(question="computador não liga", answer="Verifique a energia e a fonte."),
                FAQ(question="erro ao acessar sistema", answer="Reinicie e verifique as credenciais.")
            ]
            db.session.bulk_save_objects(faq_data)
            db.session.commit()
        logger.info("Banco de dados inicializado com sucesso!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas localmente
        init_db()
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))