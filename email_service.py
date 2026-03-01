import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


def send_email(sender_email,
               sender_password,
               to_email,
               subject,
               body,
               attachment_bytes=None,
               attachment_filename=None):

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_email

        msg.attach(MIMEText(body, "html"))

        if attachment_bytes and attachment_filename:
            pdf_part = MIMEApplication(attachment_bytes, _subtype="pdf")
            pdf_part.add_header(
                "Content-Disposition",
                "attachment",
                filename=attachment_filename
            )
            msg.attach(pdf_part)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        return True

    except Exception as e:
        print("Email failed:", e)
        return False