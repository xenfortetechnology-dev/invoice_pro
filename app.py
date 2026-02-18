import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_mail import Mail
from extensions import db

from ai_client import init_ai
from ai_services import initialize_ai_models

load_dotenv()

# --------------------------------------------------
# 🔧 PyInstaller resource path helper
# --------------------------------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(level=logging.DEBUG)

# --------------------------------------------------
# SQLAlchemy Base
# --------------------------------------------------
class Base(DeclarativeBase):
    pass

# --------------------------------------------------
# Flask App (UPDATED – IMPORTANT)
# --------------------------------------------------
app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static")
)

app.secret_key = os.environ.get(
    "SESSION_SECRET",
    "revolutionary-invoice-ai-system-2025"
)

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# --------------------------------------------------
# Database Configuration
# --------------------------------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///revolutionary_invoice.db"
)

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
}

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# --------------------------------------------------
# Feature Flags & Settings
# --------------------------------------------------
app.config["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY")
app.config["BLOCKCHAIN_ENABLED"] = os.environ.get(
    "BLOCKCHAIN_ENABLED", "true"
).lower() == "true"

app.config["AI_FEATURES_ENABLED"] = os.environ.get(
    "AI_FEATURES_ENABLED", "true"
).lower() == "true"

app.config["UPLOAD_FOLDER"] = resource_path("uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# --------------------------------------------------
# Extensions
# --------------------------------------------------
db.init_app(app)
mail = Mail(app)

# --------------------------------------------------
# Email (unchanged)
# --------------------------------------------------
import smtplib
from email.message import EmailMessage

def send_invoice_email(invoice, recipient_email):
    msg = EmailMessage()
    msg['Subject'] = f"Invoice #{invoice.invoice_number}"
    msg['From'] = "dummail2004@gmail.com"
    msg['To'] = recipient_email

    msg.set_content(
        f"Dear {invoice.client.name},\n\n"
        f"Please find attached Invoice #{invoice.invoice_number}.\n\nThanks!"
    )

    pdf_path = resource_path(f"invoices/invoice_{invoice.id}.pdf")

    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        msg.add_attachment(
            pdf_data,
            maintype='application',
            subtype='pdf',
            filename=f"Invoice_{invoice.invoice_number}.pdf"
        )
    except FileNotFoundError:
        logging.warning("Invoice PDF not found, sending without attachment")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login('your_email@example.com', 'your_app_password')
            smtp.send_message(msg)
    except Exception as e:
        raise Exception(f"SMTP failed: {e}")

# --------------------------------------------------
# Import models & routes AFTER app creation
# --------------------------------------------------
with app.app_context():
    import models
    import routes
    from utils import number_to_words
    from blockchain_service import initialize_blockchain
    from models import Company, User
    from utils import generate_password_hash

    app.jinja_env.filters['number_to_words'] = number_to_words

    db.create_all()

    # ---------------- AI Init ----------------
    if app.config["AI_FEATURES_ENABLED"]:
        try:
            init_ai()
            initialize_ai_models()
            logging.info("AI models initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize AI models: {e}")

    # ---------------- Blockchain Init ----------------
    if app.config["BLOCKCHAIN_ENABLED"]:
        try:
            initialize_blockchain()
            logging.info("Blockchain service initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize blockchain: {e}")

    # ---------------- Default Company ----------------
    if not Company.query.first():
        company = Company(
            name='Revolutionary Invoice Systems',
            address='Innovation Hub, Tech City, Digital District',
            city='Futureville',
            state='Technology State',
            pincode='100001',
            phone='+91-9999999999',
            email='hello@revolutionaryinvoice.ai',
            gstin='33REVAA0000A1Z5',
            pan='REVAA0000A',
            website='https://revolutionaryinvoice.ai',
            logo_path='/static/images/logo.svg'
        )
        db.session.add(company)
        db.session.commit()

    # ---------------- Default Admin ----------------
    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            email='admin@revolutionaryinvoice.ai',
            password_hash=generate_password_hash('RevolutionaryAI2025!'),
            is_admin=True,
            ai_features_enabled=True,
            voice_commands_enabled=True
        )
        db.session.add(admin_user)
        db.session.commit()
        logging.info("Default admin user created")

# --------------------------------------------------
# Context Processor
# --------------------------------------------------
@app.context_processor
def inject_today():
    return {'today': datetime.now()}

__all__ = ["app", "db", "mail"]
 
