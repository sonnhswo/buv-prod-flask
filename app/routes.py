from flask import Blueprint, request, jsonify
from app.chatbot import generate_response

chatbot_blueprint = Blueprint('chatbot', __name__)

@chatbot_blueprint.route('/buv', methods=['POST'])
def buv_chat():
    data = request.json
    user_input: str = data.get('message')
    session_id: str = data.get('session_id')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    ask_relevant_question = True
    keywords = ["Stirling", "University of London", "UoL", "IFP", "Foundation", "Arts University Bournemouth", "Bournemouth", "AUB", "Staffordshire", "SU"]
    for keyword in keywords:
        if keyword.lower() in user_input.lower():
            response = "Thank you for your question. Unfortunately, I can only provide answers related to British University Vietnam. Please reach out to our Student Information Office at studentservice@buv.edu.vn for further assistance."
            ask_relevant_question = False
            break
    
    if ask_relevant_question:
        response = generate_response(user_input, str(session_id), "British University Vietnam")
        
    return jsonify({"response": response})


@chatbot_blueprint.route('/su', methods=['POST'])
def su_chat():
    data = request.json
    user_input: str = data.get('message')
    session_id: str = data.get('session_id')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    ask_relevant_question = True
    keywords = ["Stirling", "University of London", "UoL", "IFP", "Foundation", "Arts University Bournemouth", "Bournemouth", "AUB", "Staffordshire"]
    for keyword in keywords:
        if keyword.lower() in user_input.lower():
            response = "Thank you for your question. Unfortunately, I can only provide answers related to Staffordshire University. Please reach out to our Student Information Office at studentservice@buv.edu.vn for further assistance."
            ask_relevant_question = False
            break
    
    if ask_relevant_question:
        response = generate_response(user_input, str(session_id), "Staffordshire University")
        
    return jsonify({"response": response})
