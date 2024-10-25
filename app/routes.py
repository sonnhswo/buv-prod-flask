from flask import Blueprint, request, jsonify
from app.chatbot import generate_response

chatbot_blueprint = Blueprint('chatbot', __name__)

@chatbot_blueprint.route('/buv', methods=['POST'])
def buv_chat():
    data = request.json
    user_input = data.get('message')
    session_id = data.get('session_id')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    response = generate_response(user_input, str(session_id), "British University Vietnam")
    return jsonify({"response": response})


@chatbot_blueprint.route('/su', methods=['POST'])
def su_chat():
    data = request.json
    user_input = data.get('message')
    session_id = data.get('session_id')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    response = generate_response(user_input, str(session_id), "Staffordshire University")
    return jsonify({"response": response})
