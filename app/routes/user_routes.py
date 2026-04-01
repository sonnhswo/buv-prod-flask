from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, redirect
from app.storage import get_sas_url
from app.db_models.raw_db import Chatbot, Document
from app.azure_clients.kb_clients import get_ai_search
from app.utils import normalize_starter_questions_chain
import random

user_portal_blueprint = Blueprint('user_portal', __name__)


def _format_numbered_questions(questions: list[str]) -> str:
    return "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))


def _sample_then_english_starters(pool: list[str], k: int) -> list[str]:
    """Random sample k from pool, then ensure each line is English (translate if needed)."""
    if not pool:
        return []
    sampled = random.sample(pool, min(k, len(pool)))
    try:
        out = normalize_starter_questions_chain.invoke(
            {"questions": _format_numbered_questions(sampled)}
        )
        if len(out.questions) == len(sampled):
            return out.questions
    except Exception as e:
        print(f"normalize_starter_questions failed, returning raw sample: {e}")
    return sampled


@user_portal_blueprint.route('/chatbots/<string:division>', methods=['GET'])
def get_chatbots_by_division(division):
    """Get list of all active chatbots for a specific division"""
    try:
        chatbots = Chatbot.query.filter_by(division=division, is_active=True).all()
        
        chatbot_list = []
        for chatbot in chatbots:
            chatbot_list.append({
                'id': chatbot.id,
                'name': chatbot.name,
                'description': chatbot.description,
                'division': chatbot.division,
                'configuration': chatbot.configuration,
                'publish_date': chatbot.publish_date.isoformat() if chatbot.publish_date else None,
                'created_at': chatbot.created_at.isoformat() if chatbot.created_at else None,
                'updated_at': chatbot.updated_at.isoformat() if chatbot.updated_at else None
            })
        
        return jsonify({
            'data': chatbot_list,
            'count': len(chatbot_list)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@user_portal_blueprint.route('/chatbots/<int:chatbot_id>', methods=['GET'])
def get_chatbot_detail(chatbot_id):
    """Get detailed information about a specific chatbot"""
    try:
        chatbot = Chatbot.query.get(chatbot_id)
        
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        if not chatbot.is_active:
            return jsonify({'error': 'Chatbot is not active'}), 403
        
        chatbot_detail = {
            'id': chatbot.id,
            'name': chatbot.name,
            'description': chatbot.description,
            'database_name': chatbot.database_name,
            'attachments': chatbot.attachments,
            'configuration': chatbot.configuration,
            'division': chatbot.division,
            'is_active': chatbot.is_active,
            'publish_date': chatbot.publish_date.isoformat() if chatbot.publish_date else None,
            'created_at': chatbot.created_at.isoformat() if chatbot.created_at else None,
            'updated_at': chatbot.updated_at.isoformat() if chatbot.updated_at else None
        }
        
        return jsonify({
            'data': chatbot_detail
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@user_portal_blueprint.route('/chatbots/<int:chatbot_id>/files/<string:filename>/download', methods=['GET'])
def download_chatbot_file_by_name(chatbot_id, filename):
    file = Document.query.filter_by(name=filename, chatbot_id=chatbot_id).first()
    if not file:
        file = Document.query.filter_by(name=secure_filename(filename), chatbot_id=chatbot_id).first()
    if file and file.file_path:
        url = get_sas_url(file.file_path, filename=file.name)
        if url:
            return redirect(url)
    return jsonify({"error": "File not found"}), 404


@user_portal_blueprint.route('/chatbots/<int:chatbot_id>/starter_questions', methods=['GET'])
def get_random_starter_questions(chatbot_id):
    """Get random starter questions for a chatbot from its knowledge base."""
    chatbot = Chatbot.query.get(chatbot_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    if not chatbot.is_active:
        return jsonify({"error": "Chatbot is not active"}), 403

    try:
        k = request.args.get("k", default=3, type=int)
        knowledge_base = get_ai_search()
        results = knowledge_base.client.search(
            "*",
            select=["content"],
            filter=f"chatbot eq '{chatbot.id}'",
            top=50
        )
        pool = list({doc["content"] for doc in results if doc.get("content")})
        questions = _sample_then_english_starters(pool, k)
        return jsonify({"relevant_questions": questions}), 200
    except Exception as e:
        print(f"Error fetching suggested questions for chatbot {chatbot_id}: {e}")
        return jsonify({"relevant_questions": []}), 200


