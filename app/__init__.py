from flask import Flask

from app.routes import chatbot_blueprint, question_suggest_blueprint, user_portal_blueprint
from app.extensions import db, migrate, cors
from app.commands import seed_chatbots, seed_users
from config import Config



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Configure CORS with environment-specific settings
    cors.init_app(
        app,
        origins=app.config.get('CORS_ORIGINS'),
        allow_headers=app.config.get('CORS_ALLOW_HEADERS'),
        methods=app.config.get('CORS_METHODS'),
        supports_credentials=app.config.get('CORS_SUPPORTS_CREDENTIALS')
    )
    
    app.cli.add_command(seed_users)
    app.cli.add_command(seed_chatbots)
    
    # Register the API blueprint
    app.register_blueprint(chatbot_blueprint)
    app.register_blueprint(question_suggest_blueprint, url_prefix="/question_suggest")
    app.register_blueprint(user_portal_blueprint, url_prefix="/user")

    from .db_models import raw_db
    return app
