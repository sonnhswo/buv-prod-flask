from sqlalchemy import Column, Integer, Text, String, ForeignKey, Boolean, UniqueConstraint, UUID
from sqlalchemy.dialects.postgresql import ARRAY as Array
from ..extensions import db

# Add enum for user division
class DivisionEnum(db.Enum):
    STAFF = "staff"
    FACULTY = "faculty"
    ADMIN = "admin"


class Chatbot(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True)
    description = Column(Text)
    database_name = Column(String(128), nullable=False)
    attachments = Column(Array(String(256)))
    sessions = db.relationship('ChatSession', backref='chatbot', lazy=True)
    publish_date = Column(db.DateTime, default=db.func.now())
    is_active = Column(Boolean, default=False)
    created_at = Column(db.DateTime, server_default=db.func.now())
    updated_at = Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

class User(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    password_hash = Column(String(256))
    division = Column(DivisionEnum)
    sessions = db.relationship('ChatSession', backref='user', lazy=True)
    created_at = Column(db.DateTime, server_default=db.func.now())
    updated_at = Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

class ChatSession(db.Model):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    chatbot_id = Column(Integer, ForeignKey('chatbot.id'), nullable=False)
    messages = db.relationship('ChatMessage', backref='chat_session', lazy=True)
    created_at = Column(db.DateTime, server_default=db.func.now())
    updated_at = Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

class ChatMessage(db.Model):
    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False)
    like = Column(Integer, default=0)
    is_user_message = Column(Boolean, nullable=False)
    session_id = Column(Integer, ForeignKey('chat_session.id'), nullable=False)
    created_at = Column(db.DateTime, server_default=db.func.now())
    updated_at = Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
