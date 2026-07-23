import smtplib
import logging
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import Session
from .models import SystemSettings

logger = logging.getLogger("Notifications")

def send_alert_notification(db: Session, message: str):
    """
    Sends downtime alerts via active notification channels (SMTP, Telegram, WhatsApp Webhook).
    """
    settings = db.query(SystemSettings).first()
    if not settings:
        logger.warning("No system settings found to send notifications.")
        return

    # 1. Telegram Notification
    if settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": settings.telegram_chat_id,
                "text": f"⚠️ *Sentinel360 ALERT*\n\n{message}",
                "parse_mode": "Markdown"
            }
            res = requests.post(url, json=payload, timeout=5)
            if res.ok:
                logger.info("Telegram notification sent successfully.")
            else:
                logger.error(f"Failed to send Telegram notification: {res.text}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")

    # 2. WhatsApp Webhook Notification
    if settings.whatsapp_enabled and settings.whatsapp_webhook_url:
        try:
            headers = {}
            if settings.whatsapp_token:
                headers["Authorization"] = f"Bearer {settings.whatsapp_token}"
            
            payload = {
                "message": f"⚠️ Sentinel360 ALERT: {message}",
                "timestamp": str(datetime.utcnow())
            }
            res = requests.post(settings.whatsapp_webhook_url, json=payload, headers=headers, timeout=5)
            if res.ok:
                logger.info("WhatsApp notification sent successfully.")
            else:
                logger.error(f"Failed to send WhatsApp notification: {res.text}")
        except Exception as e:
            logger.error(f"Error sending WhatsApp notification: {e}")

    # 3. SMTP Email Notification
    if settings.smtp_enabled and settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.smtp_recipient:
        try:
            msg = MIMEMultipart()
            msg["From"] = settings.smtp_sender or settings.smtp_username
            msg["To"] = settings.smtp_recipient
            msg["Subject"] = "⚠️ Sentinel360 ALERT"

            body = f"Hello,\n\nSentinel360 has detected a monitoring event:\n\n{message}\n\nRegards,\nSentinel360 Monitoring System"
            msg.attach(MIMEText(body, "plain"))

            port = settings.smtp_port or 587
            if port == 465:
                server = smtplib.SMTP_SSL(settings.smtp_host, port, timeout=10)
            else:
                server = smtplib.SMTP(settings.smtp_host, port, timeout=10)
                server.starttls()

            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(msg["From"], msg["To"], msg.as_string())
            server.quit()
            logger.info("SMTP Email notification sent successfully.")
        except Exception as e:
            logger.error(f"Error sending SMTP Email notification: {e}")
