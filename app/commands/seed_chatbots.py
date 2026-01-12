import click
from flask import current_app
from flask.cli import with_appcontext

from app.db_models.raw_db import db, Chatbot  # Adjust the import based on your project structure
from datetime import datetime, timedelta


@click.command("seed-chatbots")
@with_appcontext
def seed_chatbots():
    """Seed the roles table with default data."""
    names = [
        "buv", "su", "uol", "ifp", "aub", "us",
        "library", "it-support", "admissions", "finance",
        "student-council", "careers"
    ]
    base_description = "A chatbot is a sophisticated software application designed to simulate human conversation through text or voice interactions."

    for i, name in enumerate(names):
        chatbot = Chatbot.query.filter_by(name=name).first()
        if not chatbot:
            created_at = datetime.utcnow() - timedelta(days=30 - i)
            publish_date = created_at + timedelta(days=2)
            last_modified = publish_date + timedelta(hours=i * 5)

            chatbot = Chatbot(
                name=name,
                description=base_description,
                publish_date=publish_date,
                created_at=created_at,
                last_modified=last_modified,
                status='Active'
            )
            db.session.add(chatbot)

    db.session.commit()
    current_app.logger.info("Chatbots seeded successfully.")
    click.echo("Chatbots seeded successfully.")
