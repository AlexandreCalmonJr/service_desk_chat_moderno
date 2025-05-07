from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_file, Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate, upgrade
from flask_sqlalchemy import SQLAlchemy
from flask_script import Manager
import psycopg2
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import spacy
import re
import logging
from werkzeug.security import generate_password_hash, check_password_hash
import os
import csv
from io import StringIO, BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Baixar recursos do NLTK
try:
    nltk.download('punkt')
    nltk.download('stopwords')
except Exception as e:
    logger.error(f"Erro ao baixar recursos do NLTK: {e}")

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Substitua por uma chave segura

# Configurar banco de dados com SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configurar Flask-Migrate
migrate = Migrate(app, db)

# Configurar Flask-Script
manager = Manager(app)

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Carregar spaCy para português
try:
    nlp = spacy.load("pt_core_news_sm")
except Exception as e:
    logger.error(f"Erro ao carregar spaCy: {e}")
    raise

# --- Modelos do Banco de Dados ---

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

# --- Rotas de Autenticação ---

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
        try:
            new_user = User(name=name, email=email, password=generate_password_hash(password), is_admin=is_admin)
            db.session.add(new_user)
            db.session.commit()
            flash('Cadastro realizado com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Email já cadastrado.', 'error')
            logger.error(f"Erro ao cadastrar usuário: {e}")
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'success')
    return redirect(url_for('login'))

# --- Lógica do Chat com Banco de Dados ---

def buscar_resposta_faq(pergunta):
    faq = FAQ.query.filter(FAQ.question.ilike(f'%{pergunta}%')).first()
    return faq.answer if faq else None

def fallback_resumo_encerramento(categoria):
    if categoria.lower() == "hardware":
        return "Problema de hardware resolvido após substituição de componente. Testes realizados com sucesso."
    elif categoria.lower() == "software":
        return "Erro de software corrigido com atualização do sistema. Sistema funcionando normalmente."
    return "Problema resolvido após análise e correção. Sistema funcionando normalmente."

def obter_informacoes_chamado(chamado_id):
    chamados_db = {
        "12345": {"descricao": "Computador não liga", "status": "Em andamento", "categoria": "Hardware"},
        "67890": {"descricao": "Erro ao acessar sistema ERP", "status": "Em andamento", "categoria": "Software"}
    }
    return chamados_db.get(chamado_id, {"descricao": "", "status": "", "categoria": ""})

def encerrar_chamado(chamado_id, resumo):
    return {"status": "Encerrado", "chamado_id": chamado_id, "resumo": resumo}

def gerar_resumo_encerramento(descricao, categoria):
    return fallback_resumo_encerramento(categoria)

def sugerir_solucao(descricao):
    resposta = buscar_resposta_faq(descricao)
    if resposta:
        return resposta
    return "1. Identifique o erro específico. 2. Consulte a documentação do sistema. 3. Tente reiniciar o dispositivo ou software. 4. Contate o suporte se o problema persistir."

def responder_pergunta_geral(pergunta):
    resposta = buscar_resposta_faq(pergunta)
    if resposta:
        return resposta
    return "Por favor, reformule sua pergunta ou consulte a documentação do sistema para mais detalhes."

stop_words = set(stopwords.words('portuguese'))
def preprocessar_texto(texto):
    try:
        texto = texto.lower()
        texto = re.sub(r'[^\w\s]', '', texto)
        tokens = word_tokenize(texto)
        tokens = [word for word in tokens if word not in stop_words]
        return ' '.join(tokens)
    except Exception as e:
        logger.error(f"Erro ao preprocessar texto: {e}")
        return texto

def processar_mensagem(mensagem):
    try:
        mensagem = mensagem.lower().strip()
        doc = nlp(mensagem)

        if "encerrar chamado" in mensagem:
            match = re.search(r'encerrar chamado\s*(\d+)', mensagem)
            if match:
                chamado_id = match.group(1)
                resultado = assistente_encerramento(chamado_id)
                if "error" in resultado:
                    return resultado["error"]
                return f"Chamado {resultado['chamado_id']} encerrado: {resultado['resumo']}"
            return "Por favor, forneça o ID do chamado (ex.: 'Encerrar chamado 12345')."

        if any(token.lemma_ in ["sugerir", "solucionar", "solução"] for token in doc):
            descricao = preprocessar_texto(mensagem.replace("sugerir solução", "").replace("solucionar", "").replace("solução", "").strip())
            if not descricao:
                return "Por favor, descreva o problema (ex.: 'Sugerir solução para computador não liga')."
            solucao = sugerir_solucao(descricao)
            return f"Solução sugerida: {solucao}"

        if any(token.lemma_ in ["como", "fazer", "configurar", "instalar"] for token in doc):
            pergunta = mensagem.strip()
            resposta = responder_pergunta_geral(pergunta)
            return resposta

        return "Desculpe, não entendi. Tente 'Encerrar chamado <ID>', 'Sugerir solução para <problema>', ou perguntas como 'Como configurar uma VPN?'."
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        return "Erro ao processar a solicitação."

def assistente_encerramento(chamado_id):
    try:
        chamado = obter_informacoes_chamado(chamado_id)
        if not chamado["descricao"]:
            return {"error": "Chamado não encontrado."}
        resumo = gerar_resumo_encerramento(chamado["descricao"], chamado["categoria"])
        resultado = encerrar_chamado(chamado_id, resumo)
        return resultado
    except Exception as e:
        logger.error(f"Erro no assistente de encerramento: {e}")
        return {"error": "Erro ao encerrar o chamado."}

# --- Rotas Flask ---

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user)

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    try:
        data = request.json
        mensagem = data.get('mensagem')
        if not mensagem:
            return jsonify({"resposta": "Por favor, envie uma mensagem."})
        resposta = processar_mensagem(mensagem)
        return jsonify({"resposta": resposta})
    except Exception as e:
        logger.error(f"Erro na rota /chat: {e}")
        return jsonify({"resposta": "Erro ao processar a solicitação."})

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
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Erro ao adicionar FAQ: {e}")
                    flash('Erro ao adicionar FAQ.', 'error')
            else:
                flash('Preencha todos os campos.', 'error')
        elif 'edit_id' in request.form:
            faq_id = request.form.get('edit_id')
            new_question = request.form.get('edit_question')
            new_answer = request.form.get('edit_answer')
            if faq_id and new_question and new_answer:
                try:
                    faq = FAQ.query.get(faq_id)
                    faq.question = new_question
                    faq.answer = new_answer
                    db.session.commit()
                    flash('FAQ atualizada com sucesso!', 'success')
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Erro ao atualizar FAQ: {e}")
                    flash('Erro ao atualizar FAQ.', 'error')
        elif 'delete_id' in request.form:
            faq_id = request.form.get('delete_id')
            if faq_id:
                try:
                    faq = FAQ.query.get(faq_id)
                    db.session.delete(faq)
                    db.session.commit()
                    flash('FAQ excluída com sucesso!', 'success')
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Erro ao excluir FAQ: {e}")
                    flash('Erro ao excluir FAQ.', 'error')
    faqs = FAQ.query.all()
    return render_template('admin_faq.html', faqs=faqs)

@app.route('/admin/faq/export/csv')
@login_required
def export_faq_csv():
    if not current_user.is_admin:
        flash('Você não tem permissão para acessar esta página.', 'error')
        return redirect(url_for('index'))
    faqs = FAQ.query.all()

    # Gerar o arquivo CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'Pergunta', 'Resposta'])
    for faq in faqs:
        writer.writerow([faq.id, faq.question, faq.answer])
    output = si.getvalue()
    si.close()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=faqs.csv"}
    )

@app.route('/admin/faq/export/pdf')
@login_required
def export_faq_pdf():
    if not current_user.is_admin:
        flash('Você não tem permissão para acessar esta página.', 'error')
        return redirect(url_for('index'))
    faqs = FAQ.query.all()

    # Gerar o arquivo PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Título
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Lista de FAQs", styles['Title']))
    elements.append(Paragraph("<br/><br/>", styles['Normal']))

    # Tabela de FAQs
    data = [['ID', 'Pergunta', 'Resposta']]
    for faq in faqs:
        data.append([str(faq.id), faq.question, faq.answer])
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)

    # Construir o PDF
    doc.build(elements)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="faqs.pdf",
        mimetype="application/pdf"
    )

# --- Comandos para Gerenciar Migrações ---

@manager.command
def init_db():
    """Inicializa o banco de dados com dados padrão."""
    with app.app_context():
        # Criar as tabelas (será gerenciado pelo Flask-Migrate)
        db.create_all()
        # Inserir FAQs padrão se a tabela estiver vazia
        if not FAQ.query.first():
            faq_data = [
                FAQ(question="computador não liga", answer="1. Verificar cabo de energia e conexões. 2. Testar fonte de alimentação com multímetro. 3. Substituir fonte se defeituosa. 4. Testar inicialização."),
                FAQ(question="erro ao acessar sistema", answer="1. Verificar credenciais de login. 2. Reiniciar o sistema. 3. Atualizar o software para a versão mais recente. 4. Testar acesso novamente."),
                FAQ(question="como configurar uma vpn", answer="1. Abra as configurações de rede do sistema operacional. 2. Adicione uma nova conexão VPN. 3. Insira o endereço do servidor VPN, usuário e senha fornecidos pelo administrador. 4. Conecte-se e teste a conexão."),
                FAQ(question="impressora não funciona", answer="1. Verifique se a impressora está ligada e conectada. 2. Confirme que os drivers estão instalados. 3. Teste a impressão de uma página de teste. 4. Reinicie a impressora e o computador.")
            ]
            db.session.bulk_save_objects(faq_data)
            db.session.commit()
        print("Banco de dados inicializado com sucesso!")

@manager.command
def apply_migrations():
    """Aplica todas as migrações pendentes."""
    with app.app_context():
        upgrade()
        print("Migrações aplicadas com sucesso!")

if __name__ == '__main__':
    manager.run()