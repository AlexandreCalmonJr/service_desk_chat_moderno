import re
import os
import json
import csv
import io
from PyPDF2 import PdfReader
from werkzeug.security import generate_password_hash
from flask import url_for
from models import FAQ, User, db
from spacy.cli import download
import spacy

try:
    nlp = spacy.load('pt_core_news_sm')
except OSError:
    print("Modelo pt_core_news_sm não encontrado. A fazer o download...")
    try:
        download('pt_core_news_sm')
        nlp = spacy.load('pt_core_news_sm')
    except Exception as e:
        print(f"Erro ao carregar ou baixar o modelo spacy: {str(e)}")
        nlp = None  # Fallback para evitar falhas

def process_ticket_command(message):
    """Processa comandos relacionados a tickets, como 'Encerrar chamado'."""
    match = re.match(r"Encerrar chamado (\d+)", message)
    if match:
        from models import Ticket
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
    """Sugere soluções pré-definidas para problemas comuns."""
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
    """Extrai FAQs de um arquivo PDF."""
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
        return [], f"Erro ao processar o PDF: {str(e)}"

def is_image_url(url):
    """Verifica se a URL é de uma imagem válida."""
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
    return url and url.lower().endswith(image_extensions)

def is_video_url(url):
    """Verifica se a URL é de um vídeo válido."""
    video_extensions = ('.mp4', '.webm', '.ogg')
    return url and (any(url.lower().endswith(ext) for ext in video_extensions) or 'youtube.com' in url.lower() or 'youtu.be' in url.lower())

def create_admin_user(name, email, password, is_admin=True):
    """Cria um novo usuário administrador."""
    if User.query.filter_by(email=email).first():
        return None, f"Erro: O email '{email}' já existe."
    
    hashed_password = generate_password_hash(password)
    admin_user = User(
        name=name,
        email=email,
        password=hashed_password,
        is_admin=is_admin,
        level_id=Level.query.filter_by(name='Iniciante').first().id
    )
    db.session.add(admin_user)
    db.session.commit()
    return admin_user, f"Administrador '{name}' criado com sucesso!"