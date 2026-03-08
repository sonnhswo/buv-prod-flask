from manage import app
from app.extensions import db
from sqlalchemy import text

with app.app_context():
    db.session.execute(text("DELETE FROM alembic_version;"))
    db.session.commit()
    print("Cleared alembic_version")
