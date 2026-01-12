import click
from flask import current_app
from flask.cli import with_appcontext

from app.db_models.raw_db import db, Chatbot  # Adjust the import based on your project structure
from datetime import datetime


@click.command("seed-chatbots")
@with_appcontext
def seed_chatbots():
    """Seed the roles table with default data."""
    names = ["buv", "su", "uol", "ifp", "aub", "us"]
    base_description = "A chatbot is a sophisticated software application designed to simulate human conversation through text or voice interactions."

    for name in names:
        chatbot = Chatbot.query.filter_by(name=name).first()
        if not chatbot:
            chatbot = Chatbot(
                name=name,
                description=base_description,
                publish_date=datetime.utcnow(),
                status='Active'
            )
            db.session.add(chatbot)

    db.session.commit()
    current_app.logger.info("Chatbots seeded successfully.")
    click.echo("Chatbots seeded successfully.")
