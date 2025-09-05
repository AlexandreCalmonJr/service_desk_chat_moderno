from flask import session
from models import FAQ, UserChallenge, Level, db
from utils import nlp
from config import LEVELS
from flask_login import current_user
from sqlalchemy import or_

def find_faqs_by_keywords(message):
    """Busca FAQs com base em palavras-chave."""
    search_words = set(message.lower().split())
    if not search_words:
        return []

    faqs = FAQ.query.all()
    matches = []
    for faq in faqs:
        question_words = set(faq.question.lower().split())
        answer_words = set(faq.answer.lower().split())
        score = len(search_words.intersection(question_words)) * 2 + len(search_words.intersection(answer_words))
        if score > 0:
            matches.append((faq, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches]

def find_faq_by_nlp(message):
    """Busca FAQs usando processamento de linguagem natural com spaCy."""
    doc = nlp(message.lower())
    keywords = {token.lemma_ for token in doc if not token.is_stop and not token.is_punct and token.pos_ in ['NOUN', 'PROPN', 'VERB']}
    
    if not keywords:
        return []

    query = FAQ.query.filter(or_(
        FAQ.question.ilike(f'%{keyword}%'),
        FAQ.answer.ilike(f'%{keyword}%')
    ) for keyword in keywords)
    
    matches = []
    for faq in query.all():
        question_doc = nlp(faq.question.lower())
        answer_doc = nlp(faq.answer.lower())
        faq_keywords = {token.lemma_ for token in question_doc if not token.is_stop and not token.is_punct}
        faq_keywords.update({token.lemma_ for token in answer_doc if not token.is_stop and not token.is_punct})
        score = len(keywords.intersection(faq_keywords))
        if score > 0:
            matches.append((faq, score))
    
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches]

def update_user_level(user):
    """Atualiza o nível do usuário com base nos pontos."""
    current_level_id = user.level_id
    new_level = Level.query.filter(Level.min_points <= user.points).order_by(Level.min_points.desc()).first()
    
    if new_level and new_level.id != current_level_id:
        user.level_id = new_level.id
        return f'Subiu de nível! Você agora é {new_level.name}!'
    return None