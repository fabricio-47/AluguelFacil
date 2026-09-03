import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def enviar_email(destinatario, assunto, corpo_html):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not all([smtp_host, smtp_user, smtp_password]):
        raise RuntimeError("Configuracao SMTP incompleta. Defina SMTP_HOST, SMTP_USER e SMTP_PASSWORD no .env")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = smtp_from
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html"))

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, destinatario, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, destinatario, msg.as_string())
