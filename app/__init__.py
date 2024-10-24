from flask import Flask, request
# from app.database import init_db
from app.routes import chatbot_blueprint
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Register the API blueprint
    app.register_blueprint(chatbot_blueprint)

    return app
