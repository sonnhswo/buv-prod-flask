import click
from flask import current_app
from flask.cli import with_appcontext

from app.db_models.raw_db import db, Chatbot  # Adjust the import based on your project structure


@click.command("seed-chatbots")
@with_appcontext
def seed_chatbots():
    """Seed the roles table with default data."""
    names = ["buv", "su", "uol", "ifp", "aub", "us"]

    for name in names:
        if not Chatbot.query.filter_by(name=name).first():
            chatbot = Chatbot(name=name)
            db.session.add(chatbot)

    db.session.commit()
    current_app.logger.info("Chatbots seeded successfully.")
    click.echo("Chatbots seeded successfully.")
