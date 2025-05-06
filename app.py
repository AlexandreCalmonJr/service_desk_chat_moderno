import os
from flask import Flask, request, jsonify, render_template
from transformers import T5Tokenizer, T5ForConditionalGeneration
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import spacy
import re
import requests

# Baixar recursos do NLTK
nltk.download('punkt')
nltk.download('stopwords')

app = Flask(__name__)

# Carregar modelo e tokenizer local (FLAN-T5-base)
model_name = "google/flan-t5-base"
tokenizer = T5Tokenizer.from_pretrained(model_name)
model = T5ForConditionalGeneration.from_pretrained(model_name)

# Carregar spaCy para português
nlp = spacy.load("pt_core_news_sm")

# --- Integração com Sistema de Tickets (Simulada) ---

def obter_informacoes_chamado(chamado_id):
    """Simula chamada à API de um sistema de tickets."""
    # Simulação de API (substitua por chamada real, ex.: ServiceNow)
    chamados_db = {
        "12345": {"descricao": "Computador não liga", "status": "Em andamento", "categoria": "Hardware"},
        "67890": {"descricao": "Erro ao acessar sistema ERP", "status": "Em andamento", "categoria": "Software"}
    }
    # Exemplo de chamada real (descomente e ajuste):
    # try:
    #     response = requests.get(f"https://api.servicenow.com/v1/tickets/{chamado_id}", headers={"Authorization": "Bearer SEU_TOKEN"})
    #     return response.json()
    # except requests.RequestException:
    #     return {"descricao": "", "status": "", "categoria": ""}
    return chamados_db.get(chamado_id, {"descricao": "", "status": "", "categoria": ""})

def encerrar_chamado(chamado_id, resumo):
    """Simula encerramento via API de tickets."""
    # Simulação (substitua por chamada real)
    # Exemplo de chamada real:
    # try:
    #     response = requests.post(f"https://api.servicenow.com/v1/tickets/{chamado_id}/close", 
    #                             json={"resumo": resumo}, 
    #                             headers={"Authorization": "Bearer SEU_TOKEN"})
    #     return response.json()
    # except requests.RequestException:
    #     return {"error": "Erro ao encerrar chamado."}
    return {"status": "Encerrado", "chamado_id": chamado_id, "resumo": resumo}

# --- Processamento com FLAN-T5 ---

def gerar_resumo_encerramento(descricao, categoria):
    """Usa FLAN-T5-base para gerar um resumo de encerramento."""
    prompt = f"""
    Você é um assistente de TI Service Desk. Gere um resumo profissional para o encerramento de um chamado com base na descrição e categoria fornecidas. O resumo deve ser claro, conciso e refletir uma solução típica para o problema.

    Descrição: {descricao}
    Categoria: {categoria}

    Exemplo de resumo para Hardware: "Problema de hardware resolvido após substituição de componente. Testes realizados com sucesso."
    Exemplo de resumo para Software: "Erro de software corrigido com atualização do sistema. Sistema funcionando normalmente."
    """
    inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
    outputs = model.generate(
        inputs["input_ids"],
        max_length=100,
        num_beams=5,
        early_stopping=True
    )
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def sugerir_solucao(descricao):
    """Usa FLAN-T5-base para sugerir uma solução."""
    prompt = f"""
    Você é um especialista em TI Service Desk. Com base na descrição do problema fornecida, sugira uma solução prática e detalhada para resolver o problema. A solução deve ser clara, passo a passo, e adequada para um técnico de TI.

    Descrição do problema: {descricao}

    Exemplo:
    Descrição: "Computador não liga após queda de energia"
    Solução: "1. Verificar cabo de energia e conexões. 2. Testar fonte de alimentação com multímetro. 3. Substituir fonte se defeituosa. 4. Testar inicialização."
    """
    inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
    outputs = model.generate(
        inputs["input_ids"],
        max_length=150,
        num_beams=5,
        early_stopping=True
    )
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def responder_pergunta_geral(pergunta):
    """Usa FLAN-T5-base para responder perguntas gerais de TI."""
    prompt = f"""
    Você é um especialista em TI Service Desk. Responda à seguinte pergunta de forma clara, concisa e profissional, fornecendo instruções práticas se aplicável.

    Pergunta: {pergunta}

    Exemplo:
    Pergunta: "Como configurar uma VPN?"
    Resposta: "1. Abra as configurações de rede do sistema operacional. 2. Adicione uma nova conexão VPN. 3. Insira o endereço do servidor VPN, usuário e senha fornecidos pelo administrador. 4. Conecte-se e teste a conexão."
    """
    inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
    outputs = model.generate(
        inputs["input_ids"],
        max_length=200,
        num_beams=5,
        early_stopping=True
    )
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

# --- Processamento de Mensagens do Chat ---

stop_words = set(stopwords.words('portuguese'))
def preprocessar_texto(texto):
    texto = texto.lower()
    texto = re.sub(r'[^\w\s]', '', texto)
    tokens = word_tokenize(texto)
    tokens = [word for word in tokens if word not in stop_words]
    return ' '.join(tokens)

def processar_mensagem(mensagem):
    """Interpreta a mensagem do usuário usando spaCy e executa a ação correspondente."""
    mensagem = mensagem.lower().strip()
    doc = nlp(mensagem)

    # Verificar comando de encerramento
    if "encerrar chamado" in mensagem:
        match = re.search(r'encerrar chamado\s*(\d+)', mensagem)
        if match:
            chamado_id = match.group(1)
            resultado = assistente_encerramento(chamado_id)
            if "error" in resultado:
                return resultado["error"]
            return f"Chamado {resultado['chamado_id']} encerrado: {resultado['resumo']}"
        return "Por favor, forneça o ID do chamado (ex.: 'Encerrar chamado 12345')."

    # Verificar comando de solução
    if any(token.lemma_ in ["sugerir", "solucionar", "solução"] for token in doc):
        descricao = preprocessar_texto(mensagem.replace("sugerir solução", "").replace("solucionar", "").replace("solução", "").strip())
        if not descricao:
            return "Por favor, descreva o problema (ex.: 'Sugerir solução para computador não liga')."
        solucao = sugerir_solucao(descricao)
        return f"Solução sugerida: {solucao}"

    # Verificar perguntas gerais (ex.: "como fazer algo")
    if any(token.lemma_ in ["como", "fazer", "configurar", "instalar"] for token in doc):
        pergunta = mensagem.strip()
        resposta = responder_pergunta_geral(pergunta)
        return resposta

    # Resposta padrão
    return "Desculpe, não entendi. Tente 'Encerrar chamado <ID>', 'Sugerir solução para <problema>', ou perguntas como 'Como configurar uma VPN?'."

def assistente_encerramento(chamado_id):
    """Função principal do assistente de encerramento."""
    chamado = obter_informacoes_chamado(chamado_id)
    if not chamado["descricao"]:
        return {"error": "Chamado não encontrado."}
    resumo = gerar_resumo_encerramento(chamado["descricao"], chamado["categoria"])
    resultado = encerrar_chamado(chamado_id, resumo)
    return resultado

# --- Rotas Flask ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    mensagem = data.get('mensagem')
    if not mensagem:
        return jsonify({"resposta": "Por favor, envie uma mensagem."})
    resposta = processar_mensagem(mensagem)
    return jsonify({"resposta": resposta})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))