#!/usr/bin/env python3
"""
Script para inicializar o banco de dados com dados necessários
"""

from app import app, db, Level, User, Category
from werkzeug.security import generate_password_hash

def init_database():
    """Inicializa o banco de dados com dados padrão"""
    
    with app.app_context():
        # Criar todas as tabelas
        db.create_all()
        
        # Criar níveis se não existirem
        levels_data = [
            {'name': 'Iniciante', 'min_points': 0, 'insignia': '🌱'},
            {'name': 'Aprendiz', 'min_points': 100, 'insignia': '📚'},
            {'name': 'Praticante', 'min_points': 250, 'insignia': '⚡'},
            {'name': 'Especialista', 'min_points': 500, 'insignia': '🔧'},
            {'name': 'Veterano', 'min_points': 1000, 'insignia': '🏆'},
            {'name': 'Mestre', 'min_points': 2000, 'insignia': '👑'},
            {'name': 'Lenda', 'min_points': 5000, 'insignia': '⭐'}
        ]
        
        for level_data in levels_data:
            existing_level = Level.query.filter_by(name=level_data['name']).first()
            if not existing_level:
                level = Level(**level_data)
                db.session.add(level)
                print(f"Nível criado: {level_data['name']}")
        
        # Criar categorias se não existirem
        categories = ['Hardware', 'Software', 'Rede', 'Outros', 'Mobile', 'Automation']
        for category_name in categories:
            existing_category = Category.query.filter_by(name=category_name).first()
            if not existing_category:
                category = Category(name=category_name)
                db.session.add(category)
                print(f"Categoria criada: {category_name}")
        
        # Criar usuário admin se não existir
        admin_email = 'admin@servicedesk.com'
        existing_admin = User.query.filter_by(email=admin_email).first()
        if not existing_admin:
            # Pegar o primeiro nível (Iniciante)
            iniciante_level = Level.query.filter_by(name='Iniciante').first()
            if iniciante_level:
                admin_user = User(
                    name='Administrador',
                    email=admin_email,
                    password=generate_password_hash('admin123'),
                    is_admin=True,
                    points=0,
                    level_id=iniciante_level.id
                )
                db.session.add(admin_user)
                print(f"Usuário admin criado: {admin_email}")
        
        # Salvar todas as mudanças
        db.session.commit()
        print("Banco de dados inicializado com sucesso!")

if __name__ == '__main__':
    init_database()

