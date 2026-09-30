"""SMTP transport, with TLS by default and no sensitive delivery logging."""
from email.message import EmailMessage
import smtplib
import ssl

from app.core.config import settings


class MailDeliveryError(Exception):
    pass


def send_email(recipient: str, subject: str, body: str) -> None:
    if not settings.mail_enabled:
        raise MailDeliveryError("Mail service is not configured")
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        if settings.SMTP_SECURITY == "ssl":
            connection = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                                          timeout=10, context=ssl.create_default_context())
        else:
            connection = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        with connection:
            if settings.SMTP_SECURITY == "starttls":
                connection.starttls(context=ssl.create_default_context())
            if settings.SMTP_USERNAME:
                connection.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD.get_secret_value())
            refused = connection.send_message(message)
            if refused:
                raise MailDeliveryError("Mail recipient refused")
    except (OSError, smtplib.SMTPException):
        raise MailDeliveryError("Mail delivery failed") from None
