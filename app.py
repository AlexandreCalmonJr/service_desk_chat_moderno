from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import psycopg2
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import spacy
import re
import logging
from werkzeug.security import generate_password_hash, check_password_hash
import os

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

# --- Configuração do Banco de Dados PostgreSQL ---

DATABASE_URL = os.environ.get('DATABASE_URL')  # Render injeta essa variável automaticamente

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Tabela de usuários
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )''')
    # Tabela de perguntas e respostas
    c.execute('''CREATE TABLE IF NOT EXISTS faq (
        id SERIAL PRIMARY KEY,
        question TEXT NOT NULL,
        answer TEXT NOT NULL
    )''')
    # Inserir perguntas e respostas padrão (se a tabela estiver vazia)
    c.execute("SELECT COUNT(*) FROM faq")
    if c.fetchone()[0] == 0:
        faq_data = [
            ("computador não liga", "1. Verificar cabo de energia e conexões. 2. Testar fonte de alimentação com multímetro. 3. Substituir fonte se defeituosa. 4. Testar inicialização."),
            ("erro ao acessar sistema", "1. Verificar credenciais de login. 2. Reiniciar o sistema. 3. Atualizar o software para a versão mais recente. 4. Testar acesso novamente."),
            ("como configurar uma vpn", "1. Abra as configurações de rede do sistema operacional. 2. Adicione uma nova conexão VPN. 3. Insira o endereço do servidor VPN, usuário e senha fornecidos pelo administrador. 4. Conecte-se e teste a conexão."),
            ("impressora não funciona", "1. Verifique se a impressora está ligada e conectada. 2. Confirme que os drivers estão instalados. 3. Teste a impressão de uma página de teste. 4. Reinicie a impressora e o computador.")
        ]
        c.executemany("INSERT INTO faq (question, answer) VALUES (%s, %s)", faq_data)
    conn.commit()
    conn.close()

# Inicializar o banco de dados
init_db()

# --- Classe de Usuário para Flask-Login ---

class User(UserMixin):
    def __init__(self, id, name, email, password):
        self.id = id
        self.name = name
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1], user[2], user[3])
    return None

# --- Rotas de Autenticação ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[3], password):
            user_obj = User(user[0], user[1], user[2], user[3])
            login_user(user_obj)
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
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                      (name, email, generate_password_hash(password)))
            conn.commit()
            flash('Cadastro realizado com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            flash('Email já cadastrado.', 'error')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'success')
    return redirect(url_for('login'))

# --- Lógica do Chat com Banco de Dados ---

def buscar_resposta_faq(pergunta):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT answer FROM faq WHERE LOWER(question) LIKE %s", ('%' + pergunta.lower() + '%',))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

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

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))