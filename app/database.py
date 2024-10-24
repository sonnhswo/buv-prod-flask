from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()

# PGVector setup for embedding storage
def get_pgvector_engine():
    engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
    return engine
