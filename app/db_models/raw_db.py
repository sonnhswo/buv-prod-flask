from sqlalchemy import Column, Integer, Text, String, ForeignKey, Boolean, UniqueConstraint, UUID
from ..extensions import db

class Chatbot(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True)
    sessions = db.relationship('ChatSession', backref='chatbot', lazy=True)

class User(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    sessions = db.relationship('ChatSession', backref='user', lazy=True)

class ChatSession(db.Model):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    chatbot_id = Column(Integer, ForeignKey('chatbot.id'), nullable=False)
    messages = db.relationship('ChatMessage', backref='chat_session', lazy=True)

class ChatMessage(db.Model):
    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False)
    like = Column(Integer, default=0)
    is_user_message = Column(Boolean, nullable=False)
    session_id = Column(Integer, ForeignKey('chat_session.id'), nullable=False)