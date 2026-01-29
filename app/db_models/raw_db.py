from sqlalchemy import Column, Integer, Text, String, ForeignKey, Boolean, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from ..extensions import db


class Admin(db.Model):
    __tablename__ = 'admin'

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    division = Column(String(50), nullable=True)
    admin_role = Column(String(50), nullable=True)
    two_factor_enabled = Column(Boolean, default=False, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    chatbots = db.relationship('Chatbot', backref='owner', lazy=True, foreign_keys='Chatbot.owner_id')
    documents = db.relationship('Document', backref='owner', lazy=True, foreign_keys='Document.owner_id')


class User(db.Model):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=True)
    name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    is_anonymous = Column(Boolean, default=False, nullable=True)
    anonymous_identifier = Column(String(255), nullable=True)
    division = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    sessions = db.relationship('ChatSession', backref='user', lazy=True)


class Chatbot(db.Model):
    __tablename__ = 'chatbot'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    database_name = Column(String(255), nullable=True)
    attachments = Column(JSONB, nullable=True)
    publish_date = Column(DateTime(timezone=True), nullable=True)
    division = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=True)
    owner_id = Column(Integer, ForeignKey('admin.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    sessions = db.relationship('ChatSession', backref='chatbot', lazy=True)
    documents = db.relationship('Document', backref='chatbot', lazy=True)


class Document(db.Model):
    __tablename__ = 'document'

    id = Column(Integer, primary_key=True)
    chatbot_id = Column(Integer, ForeignKey('chatbot.id'), nullable=False)
    document_type = Column(String(50), nullable=True)  # 'QNA' or 'KNOWLEDGE_BASE'
    name = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    file_type = Column(String(50), nullable=True)  # 'pdf', 'docx', 'txt'
    file_size = Column(Integer, nullable=True)
    tags = Column(String(500), nullable=True)
    owner_id = Column(Integer, ForeignKey('admin.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # Unique constraint: name must be unique per chatbot
    __table_args__ = (
        UniqueConstraint('chatbot_id', 'name', name='uq_document_chatbot_name'),
    )

    # Relationships
    referenced_messages = db.relationship('ChatMessage', backref='referenced_document', lazy=True)


class ChatSession(db.Model):
    __tablename__ = 'chat_session'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
    chatbot_id = Column(Integer, ForeignKey('chatbot.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    messages = db.relationship('ChatMessage', backref='chat_session', lazy=True)


class ChatMessage(db.Model):
    __tablename__ = 'chat_message'

    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False)
    like = Column(Integer, default=0, nullable=True)
    is_user_message = Column(Boolean, nullable=False)
    session_id = Column(Integer, ForeignKey('chat_session.id'), nullable=False)
    referenced_document_id = Column(Integer, ForeignKey('document.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)