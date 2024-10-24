from flask import Blueprint, request, jsonify
from app.chatbot import generate_response

chatbot_blueprint = Blueprint('chatbot', __name__)

@chatbot_blueprint.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message')

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # Generate a chatbot response
    response = generate_response(user_input)
    return jsonify({"response": response})
