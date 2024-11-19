from flask import Flask, request
from flask_cors import CORS
from app.routes import chatbot_blueprint, question_suggest_blueprint
from config import Config



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    CORS(app) # Allow connections from all origins
    
    # Register the API blueprint
    app.register_blueprint(chatbot_blueprint)
    app.register_blueprint(question_suggest_blueprint, url_prefix="/question_suggest")

    return app
