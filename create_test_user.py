"""
Script para criar um usuário de teste e código de convite
"""
from app import app, db, User, InvitationCode, Level
from werkzeug.security import generate_password_hash
import uuid

def create_test_user():
    with app.app_context():
        # Inicializar o banco de dados
        db.create_all()
        
        # Criar níveis se não existirem
        if Level.query.count() == 0:
            print("Criando níveis...")
            from app import LEVELS
            for level_name, level_data in LEVELS.items():
                level = Level(name=level_name, min_points=level_data['min_points'], insignia=level_data['insignia'])
                db.session.add(level)
            db.session.commit()
        
        # Criar código de convite
        invitation_code = str(uuid.uuid4())
        invitation = InvitationCode(code=invitation_code, used=False)
        db.session.add(invitation)
        db.session.commit()
        
        print(f"\n{'='*60}")
        print(f"CÓDIGO DE CONVITE CRIADO: {invitation_code}")
        print(f"{'='*60}\n")
        
        # Verificar se já existe um usuário de teste
        existing_user = User.query.filter_by(email="aluno@teste.com").first()
        if existing_user:
            print("Usuário de teste 'aluno@teste.com' já existe!")
            print(f"Email: aluno@teste.com")
            print(f"Senha: teste123")
        else:
            # Criar usuário de teste
            nivel_iniciante = Level.query.filter_by(name='Iniciante').first()
            test_user = User(
                name="Aluno Teste",
                email="aluno@teste.com",
                password=generate_password_hash("teste123"),
                is_admin=False,
                points=0,
                level_id=nivel_iniciante.id if nivel_iniciante else None
            )
            db.session.add(test_user)
            db.session.commit()
            
            print("Usuário de teste criado com sucesso!")
            print(f"Email: aluno@teste.com")
            print(f"Senha: teste123")
        
        # Criar usuário admin se não existir
        existing_admin = User.query.filter_by(email="admin@exemplo.com").first()
        if not existing_admin:
            nivel_iniciante = Level.query.filter_by(name='Iniciante').first()
            admin_user = User(
                name="Administrador",
                email="admin@exemplo.com",
                password=generate_password_hash("admin123"),
                is_admin=True,
                points=0,
                level_id=nivel_iniciante.id if nivel_iniciante else None
            )
            db.session.add(admin_user)
            db.session.commit()
            print("\nUsuário admin criado!")
            print(f"Email: admin@exemplo.com")
            print(f"Senha: admin123")
        else:
            print("\nUsuário admin já existe!")
            print(f"Email: admin@exemplo.com")
            print(f"Senha: admin123")

if __name__ == "__main__":
    create_test_user()
