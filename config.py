import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'c0ddba11f7bf54608a96059d558c479d')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///service_desk.db').replace('postgres://', 'postgresql://')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'Uploads'
    INSIGNIA_FOLDER = 'Insignias'
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

LEVELS = {
    'Iniciante': {'min_points': 0, 'insignia': '🌱'},
    'Dados de Prata': {'min_points': 50, 'insignia': '🥈'},
    'Dados de Ouro': {'min_points': 150, 'insignia': '🥇'},
    'Mestre dos Dados': {'min_points': 300, 'insignia': '🏆'}
}