from app import app, db
from models import DeletedQuotation

with app.app_context():
    db.create_all()
    print("Database tables created (if they didn't exist).")
