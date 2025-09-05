import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_caching import Cache
from config import Config
from models import db, User
from routes import init_routes

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar extensões
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
cache = Cache(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Criar diretórios e banco de dados
def initialize_app():
    with app.app_context():
        try:
            # Criar diretórios
            for folder in [app.config['UPLOAD_FOLDER'], app.config['INSIGNIA_FOLDER']]:
                if not os.path.exists(folder):
                    os.makedirs(folder)
            # Criar banco de dados
            db.create_all()
            # Verificar nível inicial
            if not Level.query.filter_by(name='Iniciante').first():
                db.session.add(Level(name='Iniciante', min_points=0, insignia='beginner.svg'))
                db.session.commit()
        except Exception as e:
            print(f"Erro na inicialização do banco de dados: {str(e)}")
            raise

init_routes(app)

if __name__ == '__main__':
    initialize_app()
    app.run(debug=True)