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

# --------------------------------------------------
# Email Configuration
# --------------------------------------------------
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 465))
app.config["MAIL_USE_SSL"] = os.environ.get("MAIL_USE_SSL", "true").lower() == "true"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@invoicepro.ai")

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
    """
    Send invoice via email using SMTP credentials from environment variables.
    
    Required environment variables:
    - MAIL_USERNAME: Email address for authentication
    - MAIL_PASSWORD: Email password or app-specific password
    - MAIL_SERVER: SMTP server (default: smtp.gmail.com)
    - MAIL_PORT: SMTP port (default: 465)
    """
    # Get email credentials from config
    mail_username = app.config.get("MAIL_USERNAME")
    mail_password = app.config.get("MAIL_PASSWORD")
    mail_server = app.config.get("MAIL_SERVER", "smtp.gmail.com")
    mail_port = app.config.get("MAIL_PORT", 465)
    
    # Validate credentials are set
    if not mail_username or not mail_password:
        error_msg = (
            "Email credentials not configured. "
            "Please set MAIL_USERNAME and MAIL_PASSWORD environment variables."
        )
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    msg = EmailMessage()
    msg['Subject'] = f"Invoice #{invoice.invoice_number}"
    msg['From'] = mail_username
    msg['To'] = recipient_email

    msg.set_content(
        f"Dear {invoice.client.name},\n\n"
        f"Please find attached Invoice #{invoice.invoice_number}.\n\n"
        f"Thank you for your business!\n\n"
        f"Best regards,\nRevolutionary Invoice Systems"
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
        logging.info(f"PDF attachment added: {pdf_path}")
    except FileNotFoundError:
        logging.warning(f"Invoice PDF not found at {pdf_path}, sending without attachment")

    try:
        logging.info(f"Attempting to send email via {mail_server}:{mail_port}")
        
        # Try with SSL first (port 465)
        if mail_port == 465:
            try:
                with smtplib.SMTP_SSL(mail_server, mail_port, timeout=10) as smtp:
                    smtp.login(mail_username, mail_password)
                    smtp.send_message(msg)
                logging.info(f"Invoice email sent successfully to {recipient_email}")
                return True
            except Exception as ssl_error:
                logging.warning(f"SSL connection failed: {ssl_error}. Trying TLS...")
                # Fallback to TLS on port 587
                with smtplib.SMTP(mail_server, 587, timeout=10) as smtp:
                    smtp.starttls()
                    smtp.login(mail_username, mail_password)
                    smtp.send_message(msg)
                logging.info(f"Invoice email sent successfully to {recipient_email} (via TLS)")
                return True
        else:
            # Use standard SMTP with TLS
            with smtplib.SMTP(mail_server, mail_port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(mail_username, mail_password)
                smtp.send_message(msg)
            logging.info(f"Invoice email sent successfully to {recipient_email}")
            return True
            
    except smtplib.SMTPAuthenticationError as e:
        error_msg = (
            f"SMTP Authentication failed: {e}\n"
            "For Gmail:\n"
            "1. Enable 2-Factor Authentication: https://myaccount.google.com/security\n"
            "2. Generate app password: https://myaccount.google.com/apppasswords\n"
            "3. Use the 16-character password in MAIL_PASSWORD (not your regular password)\n"
            "4. Restart the application after updating .env"
        )
        logging.error(error_msg)
        raise Exception(error_msg)
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error: {e}. Check MAIL_SERVER and MAIL_PORT settings."
        logging.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Failed to send email: {e}"
        logging.error(error_msg)
        raise Exception(error_msg)

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
