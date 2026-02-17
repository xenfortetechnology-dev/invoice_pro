import smtplib
from email.mime.text import MIMEText

SENDER_EMAIL = "dharanimenaga229@gmail.com"
SENDER_PASSWORD = "wvpncmfqgvtflxqf"   # Use App Password

def send_email(to_email, subject, body):
    try:
        print("Preparing email...")
        print("Sender:", SENDER_EMAIL)
        print("Receiver:", to_email)

        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email

        print("Connecting to Gmail SMTP...")

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            print("Login successful")
            server.send_message(msg)

        print("Email sent successfully ✅")
        return True   # ✅ IMPORTANT

    except Exception as e:
        print("Email failed ❌:", e)
        return False  # ❌ IMPORTANT