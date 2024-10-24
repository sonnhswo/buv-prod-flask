from flask import Blueprint, request, jsonify, current_app
from app.chatbot import generate_response

chatbot_blueprint = Blueprint('chatbot', __name__)

@chatbot_blueprint.route('/buv', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message')
    session_id = data.get('session_id')
    uni_name = data.get('uni_name')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    response = generate_response(user_input, session_id)
    return jsonify({"response": response})


# @chatbot_blueprint.route('/su', methods=['POST'])
# def chat():
#     data = request.json
#     user_input = data.get('message')

#     if not user_input:
#         return jsonify({"error": "No message provided"}), 400

#     # Generate a chatbot response
#     response = generate_response(user_input)
#     return jsonify({"response": response})
