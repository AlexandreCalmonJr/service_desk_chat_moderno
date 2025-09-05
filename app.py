from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_caching import Cache
from config import Config
from models import db, User
from routes import init_routes

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
cache = Cache(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

init_routes(app)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(app.config['INSIGNIA_FOLDER']):
            os.makedirs(app.config['INSIGNIA_FOLDER'])
    app.run(debug=True)