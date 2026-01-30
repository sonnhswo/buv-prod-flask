from flask import current_app
from flask.cli import with_appcontext
from app.db_models.raw_db import db, User, Chatbot, ChatSession, ChatMessage
from datetime import datetime, timedelta
import click
import random

@click.command("seed-messages")
@with_appcontext
def seed_messages():
    """Seed the database with sample chat sessions and messages for testing logs."""
    
    # 1. Ensure we have a test student user
    student_email = "student_test@buv.edu.vn"
    user = User.query.filter_by(email=student_email).first()
    if not user:
        user = User(
            name="Test Student", 
            email=student_email, 
            division="student",
            is_anonymous=False
        )
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        print(f"Created user: {student_email}")
    
    # 2. Get Chatbots (Assuming seed-chatbots has run)
    bots = Chatbot.query.all()
    if not bots:
        print("No chatbots found. Please run 'flask seed-chatbots' first.")
        return

    # 3. Create Conversations across different dates
    # We create logs for today, 2 days ago, and 1 week ago
    
    scenarios = [
        {
            "bot_name": "buv",
            "offset_days": 0, # Today
            "dialogue": [
                ("Hello, I need help with the library.", True, 0),
                ("Hi! The library is open from 8 AM to 8 PM. How can I help?", False, 0),
                ("Can I borrow books on weekends?", True, 0),
                ("Yes, the library is open on Saturdays from 9 AM to 5 PM.", False, 1) # Thumbs up
            ]
        },
        {
            "bot_name": "su",
            "offset_days": 2, # 2 days ago
            "dialogue": [
                ("When is the deadline for the assignment?", True, 0),
                ("Please specify which module you are referring to.", False, 0),
                ("Business Management.", True, 0),
                ("I cannot find specific deadlines for that module in my documents.", False, -1) # Thumbs down
            ]
        },
        {
            "bot_name": "buv", 
            "offset_days": 7, # 1 week ago
            "dialogue": [
                ("What are the shuttle bus times?", True, 0),
                ("The shuttle bus runs every 30 minutes starting at 7:00 AM.", False, 1)
            ]
        }
    ]

    for scenario in scenarios:
        bot = next((b for b in bots if b.name == scenario['bot_name']), None)
        if not bot:
            continue
            
        base_time = datetime.now() - timedelta(days=scenario['offset_days'])
        
        # Create Session
        session = ChatSession(
            user_id=user.id,
            chatbot_id=bot.id,
            created_at=base_time,
            updated_at=base_time
        )
        db.session.add(session)
        db.session.commit() # Commit to get ID

        # Create Messages
        for idx, (text, is_user, like) in enumerate(scenario['dialogue']):
            msg_time = base_time + timedelta(seconds=idx*30) # Space messages out by 30s
            msg = ChatMessage(
                message=text,
                is_user_message=is_user,
                session_id=session.id,
                like=like,
                created_at=msg_time,
                updated_at=msg_time
            )
            db.session.add(msg)
            
    db.session.commit()
    current_app.logger.info("Sample messages seeded successfully.")
    click.echo("Sample messages seeded successfully.")
