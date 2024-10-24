from flask import Flask
from app.database import init_db
from app.routes import chatbot_blueprint
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize PostgreSQL database
    init_db(app)

    # Register the API blueprint
    app.register_blueprint(chatbot_blueprint, url_prefix='/api')

    return app
