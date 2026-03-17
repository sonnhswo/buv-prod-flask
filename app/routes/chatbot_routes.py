import json
from flask import Blueprint, request, jsonify, Response, stream_with_context
from app.chatbot import clear_history, generate_response
from app.db_models.raw_db import ChatSession, Chatbot, ChatMessage
from app.extensions import db
from app.database import uni_dbs
from config import Config

config = Config()
session = db.session

chatbot_blueprint = Blueprint('chatbot', __name__)
question_suggest_blueprint = Blueprint('question_suggest', __name__)


@chatbot_blueprint.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


@chatbot_blueprint.route('/<string:chatbot_id>/new_session_id', methods=['GET'])
def get_new_session_id(chatbot_id: str):
    # Check if chatbot exists
    chatbot = Chatbot.query.get(chatbot_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404
    new_record = ChatSession(user_id="0", chatbot_id=chatbot_id)
    session.add(new_record)
    session.commit()
    session_id = new_record.id
    session.close()
    return jsonify({"message": "New chat session created successfully", "data": {"session_id": session_id}}), 200


@chatbot_blueprint.route('/clear_conversation', methods=['POST'])
def clear_conversation():
    data: dict = request.json
    session_id: int = data.get('session_id')
    clear_history(str(session_id))
    return jsonify({"response": "Conversation cleared!"})


@chatbot_blueprint.route('/<int:chatbot_id>', methods=['POST'])
def chat(chatbot_id: int):
    data: dict = request.json
    user_input: str = data.get('message')
    session_id: int = data.get('session_id')

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    if not session_id:
        return jsonify({"error": "No session_id provided"}), 400
    
    chatbot = Chatbot.query.get(chatbot_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    ab_configs = None
    if chatbot.configuration:
        ab_configs = config.AB_CONFIGS.get(chatbot.configuration['endpoint'])
    
    # phase 1 bots
    if ab_configs:
        except_keywords = ab_configs['except_keywords']
        full_name = ab_configs['full_name']
    # phase 2 bots
    else:
        except_keywords = []
        full_name = chatbot.name

    if chatbot.division == 'student':
        fallback_message = "You may reach out to Campus Central at campuscentral@buv.edu.vn and the team will gladly assist you."
        error_message = "For further assistance, please contact Campus Central via email at campuscentral@buv.edu.vn or by phone at 0936 376 136."
    else:
        fallback_message = "You may reach out to Academic Quality Office at qa@buv.edu.vn and the team will gladly assist you."
        error_message = "For further assistance, please contact Academic Quality Office via email at qa@buv.edu.vn."

    ask_relevant_question = True
    for keyword in except_keywords:
        if keyword.lower() in user_input.lower():
            answer = f"Thank you for your question. Unfortunately, I can only provide answers related to {full_name}. {error_message}"
            response = {
                "answer": answer,
                "source": None,
                "page_number": None,
                "relevant_questions": [] 
            }
            ask_relevant_question = False
            break

    if ask_relevant_question:
        print(f"Executing langchain for chatbot {full_name=}.")
        response = generate_response(user_input, str(session_id), str(chatbot.id), full_name, fallback_message, error_message)

    new_human_message = ChatMessage(message=user_input, is_user_message=True, session_id=session_id)
    new_ai_message = ChatMessage(message=response["answer"], is_user_message=False, session_id=session_id)
    session.add(new_human_message)
    session.add(new_ai_message)
    session.commit()
    response["ai_message_id"] = new_ai_message.id
    session.close()
    return jsonify(response)


@chatbot_blueprint.route('/<int:chatbot_id>/stream', methods=['POST'])
def chat_stream(chatbot_id: int):
    data: dict = request.json
    user_input: str = data.get('message')
    session_id: int = data.get('session_id')

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    if not session_id:
        return jsonify({"error": "No session_id provided"}), 400
    
    chatbot = Chatbot.query.get(chatbot_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    ab_configs = None
    if chatbot.configuration:
        ab_configs = config.AB_CONFIGS.get(chatbot.configuration['endpoint'])
    
    # phase 1 bots
    if ab_configs:
        except_keywords = ab_configs['except_keywords']
        full_name = ab_configs['full_name']
    # phase 2 bots
    else:
        except_keywords = []
        full_name = chatbot.name

    if chatbot.division == 'student':
        fallback_message = "You may reach out to Campus Central at campuscentral@buv.edu.vn and the team will gladly assist you."
        error_message = "For further assistance, please contact Campus Central via email at campuscentral@buv.edu.vn or by phone at 0936 376 136."
    else:
        fallback_message = "You may reach out to Academic Quality Office at qa@buv.edu.vn and the team will gladly assist you."
        error_message = "For further assistance, please contact Academic Quality Office via email at qa@buv.edu.vn."

    def generate():
        ask_relevant_question = True
        for keyword in except_keywords:
            if keyword.lower() in user_input.lower():
                answer = f"Thank you for your question. Unfortunately, I can only provide answers related to {full_name}. {error_message}"

                # Stream the static response
                yield f"data: {json.dumps({'type': 'content', 'content': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'metadata', 'source': None, 'page_number': None})}\n\n"
                yield f"data: {json.dumps({'type': 'questions', 'relevant_questions': []})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                # Save to database
                new_human_message = ChatMessage(message=user_input, is_user_message=True, session_id=session_id)
                new_ai_message = ChatMessage(message=answer, is_user_message=False, session_id=session_id)
                session.add(new_human_message)
                session.add(new_ai_message)
                session.commit()
                
                yield f"data: {json.dumps({'type': 'message_id', 'ai_message_id': new_ai_message.id})}\n\n"
                
                ask_relevant_question = False
                return
        
        if ask_relevant_question:
            from app.chatbot import generate_response_stream
            full_answer = ""

            try:
                for chunk in generate_response_stream(user_input, str(session_id), str(chatbot.id), full_name, fallback_message, error_message):
                    if chunk['type'] == 'content':
                        full_answer += chunk['content']
                    yield f"data: {json.dumps(chunk)}\n\n"
                
                # Save to database after streaming completes
                new_human_message = ChatMessage(message=user_input, is_user_message=True, session_id=session_id)
                new_ai_message = ChatMessage(message=full_answer, is_user_message=False, session_id=session_id)
                session.add(new_human_message)
                session.add(new_ai_message)
                session.commit()
                
                # Send message ID
                yield f"data: {json.dumps({'type': 'message_id', 'ai_message_id': new_ai_message.id})}\n\n"
                
            except Exception as e:
                print(f"Error during streaming: {e}")
                error_msg = "An error occurred while processing your request."
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@chatbot_blueprint.route('/like/<int:message_id>', methods=['GET'])
def thumb_up(message_id: int):
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.THUMB_UP_VALUE
        session.commit()
        return jsonify({"message": "message liked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404

@chatbot_blueprint.route('/dislike/<int:message_id>', methods=['GET'])
def thumb_down(message_id: int):
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.THUMB_DOWN_VALUE
        session.commit()
        return jsonify({"message": "message disliked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404 

@chatbot_blueprint.route('/unlike/<int:message_id>', methods=['GET'])
def no_thumb(message_id: int):
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.NO_THUMB_VALUE
        session.commit()
        return jsonify({"message": "message unliked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404 


@question_suggest_blueprint.route('/start', methods=['GET'])
def start_questions():
    awarding_body = request.args.get("awarding_body")
    if awarding_body == "buv":
        connection_string = uni_dbs['British University Vietnam']
    elif awarding_body == "su":
        connection_string = uni_dbs['Staffordshire University']

    results = [
        "How can I book an appointment with a tutor for academic support?",
        "What steps should I take if I am unable to attend an exam due to unforeseen circumstances?",
        "How can I access career counselling or job placement services at BUV?",
    ]
    
    return jsonify({'relevant_questions': results})
