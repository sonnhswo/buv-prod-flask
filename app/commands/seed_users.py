from flask import current_app
from flask.cli import with_appcontext
from app.db_models.raw_db import db, User  # Adjust the import based on your project structure
import click

@click.command("seed-users")
@with_appcontext
def seed_users():
    """Seed the roles table with default data."""
    names = ["ndz"]

    for name in names:
        if not User.query.filter_by(name=name).first():
            user = User(id="0", name=name)
            db.session.add(user)

    db.session.commit()
    current_app.logger.info("Users seeded successfully.")
    click.echo("Users seeded successfully.")
