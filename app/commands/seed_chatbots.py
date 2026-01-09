import click
from flask import current_app
from flask.cli import with_appcontext

from app.db_models.raw_db import db, Chatbot  # Adjust the import based on your project structure


@click.command("seed-chatbots")
@with_appcontext
def seed_chatbots():
    """Seed the roles table with default data."""
    # Map chatbot names to their respective database names
    chatbot_configs = [
        {"name": "buv", "database_name": current_app.config.get('PGDATABASE')},
        {"name": "su", "database_name": current_app.config.get('DEMO_SU')},
        {"name": "uol", "database_name": current_app.config.get('PROD_UOL')},
        {"name": "ifp", "database_name": current_app.config.get('PROD_IFP')},
        {"name": "aub", "database_name": current_app.config.get('PROD_AUB')},
        {"name": "us", "database_name": current_app.config.get('PROD_US')},
    ]

    for config in chatbot_configs:
        existing_chatbot = Chatbot.query.filter_by(name=config["name"]).first()
        if not existing_chatbot:
            chatbot = Chatbot(name=config["name"], database_name=config["database_name"])
            db.session.add(chatbot)
        else:
            # Update database_name if chatbot already exists
            existing_chatbot.database_name = config["database_name"]

    db.session.commit()
    current_app.logger.info("Chatbots seeded successfully.")
    click.echo("Chatbots seeded successfully.")
