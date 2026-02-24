import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

SENDER_EMAIL = "dharanimenaga229@gmail.com"
SENDER_PASSWORD = "wvpncmfqgvtflxqf"   # Use App Password

def send_email(to_email, subject, body, attachment_bytes=None, attachment_filename=None):
    """
    Send an HTML email with an optional PDF attachment.

    Parameters
    ----------
    to_email            : str  – recipient e-mail address
    subject             : str  – e-mail subject
    body                : str  – HTML body content
    attachment_bytes    : bytes | None  – raw PDF bytes to attach
    attachment_filename : str  | None  – filename shown in the e-mail (e.g. 'Invoice_001.pdf')
    """
    try:
        print("Preparing email...")
        print("Sender:", SENDER_EMAIL)
        print("Receiver:", to_email)

        # Use multipart so we can attach a file when needed
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email

        # Attach HTML body
        msg.attach(MIMEText(body, "html"))

        # Attach PDF if provided
        if attachment_bytes and attachment_filename:
            pdf_part = MIMEApplication(attachment_bytes, _subtype="pdf")
            pdf_part.add_header(
                "Content-Disposition",
                "attachment",
                filename=attachment_filename
            )
            msg.attach(pdf_part)
            print(f"Attached PDF: {attachment_filename} ({len(attachment_bytes)} bytes)")

        print("Connecting to Gmail SMTP...")

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            print("Login successful")
            server.send_message(msg)

        print("Email sent successfully ")
        return True   # ✅ IMPORTANT

    except Exception as e:
        print("Email failed ❌:", e)
        return False  # ❌ IMPORTANT