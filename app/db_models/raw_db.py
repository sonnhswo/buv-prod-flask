from flask_sqlalchemy.model import Model

from ..extensions import db

class Chatbot(db.Model):
    id = db.Column(db.String(128), primary_key=True)
    name = db.Column(db.String(128))
    sessions = db.relationship('Session', backref='chatbot', lazy=True)

class User(db.Model):
    id = db.Column(db.String(128), primary_key=True)
    name = db.Column(db.String(128))
    sessions = db.relationship('Session', backref='user', lazy=True)
    messages = db.relationship('Message', backref='user', lazy=True)

class Session(db.Model):
    id = db.Column(db.String(128), primary_key=True)
    user_id = db.Column(db.String(128), db.ForeignKey('user.id'), nullable=False)
    chatbot_id = db.Column(db.String(128), db.ForeignKey('chatbot.id'), nullable=False)
    messages = db.relationship('Message', backref='session', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text)
    like = db.Column(db.Integer)
    is_user_message = db.Column(db.Boolean)
    session_id = db.Column(db.String(128), db.ForeignKey('session.id'), nullable=False)
    user_id = db.Column(db.String(128), db.ForeignKey('user.id'), nullable=False)
