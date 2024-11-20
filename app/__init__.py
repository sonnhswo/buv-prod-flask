from flask import Flask

from app.routes import chatbot_blueprint, question_suggest_blueprint
from app.extensions import db, migrate, cors
from config import Config



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    # CORS(app) # Allow connections from all origins
    
    # Register the API blueprint
    app.register_blueprint(chatbot_blueprint)
    app.register_blueprint(question_suggest_blueprint, url_prefix="/question_suggest")

    from .db_models import raw_db
    return app
