from app.routes.chatbot_routes import chatbot_blueprint, question_suggest_blueprint
from app.routes.user_routes import user_portal_blueprint
from app.routes.admin_routes import admin_portal_blueprint

__all__ = [
    "chatbot_blueprint",
    "question_suggest_blueprint",
    "user_portal_blueprint",
    "admin_portal_blueprint",
]
