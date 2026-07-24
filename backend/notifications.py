import smtplib
import logging
import requests
from typing import Optional
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import Session
from .models import SystemSettings

logger = logging.getLogger("Notifications")

def send_alert_notification(db: Session, message: str, notification_config_id: Optional[int] = None):
    """
    Sends downtime alerts via the specified NotificationConfig (Uptime Kuma style).
    If notification_config_id is None, falls back to legacy global settings (if enabled).
    """
    from typing import Optional
    from .models import NotificationConfig, SystemSettings

    # Initialize empty credentials/settings
    telegram_enabled = False
    telegram_bot_token = None
    telegram_chat_id = None

    whatsapp_enabled = False
    whatsapp_webhook_url = None
    whatsapp_token = None
    whatsapp_session_id = None
    whatsapp_recipients = None

    smtp_enabled = False
    smtp_host = None
    smtp_port = 587
    smtp_username = None
    smtp_password = None
    smtp_sender = None
    smtp_recipient = None

    # Fetch configuration
    if notification_config_id:
        cfg = db.query(NotificationConfig).filter(NotificationConfig.id == notification_config_id).first()
        if not cfg or not cfg.is_enabled:
            logger.warning(f"NotificationConfig with ID {notification_config_id} is missing or disabled.")
            return
        
        if cfg.type == "telegram":
            telegram_enabled = True
            telegram_bot_token = cfg.telegram_bot_token
            telegram_chat_id = cfg.telegram_chat_id
        elif cfg.type == "whatsapp":
            whatsapp_enabled = True
            whatsapp_webhook_url = cfg.whatsapp_webhook_url
            whatsapp_token = cfg.whatsapp_token
            whatsapp_session_id = cfg.whatsapp_session_id
            whatsapp_recipients = cfg.whatsapp_recipients
        elif cfg.type == "smtp":
            smtp_enabled = True
            smtp_host = cfg.smtp_host
            smtp_port = cfg.smtp_port or 587
            smtp_username = cfg.smtp_username
            smtp_password = cfg.smtp_password
            smtp_sender = cfg.smtp_sender
            smtp_recipient = cfg.smtp_recipient
    else:
        # Fallback to legacy SystemSettings
        settings = db.query(SystemSettings).first()
        if not settings:
            logger.warning("No global settings or NotificationConfig specified.")
            return
        telegram_enabled = settings.telegram_enabled
        telegram_bot_token = settings.telegram_bot_token
        telegram_chat_id = settings.telegram_chat_id
        
        whatsapp_enabled = settings.whatsapp_enabled
        whatsapp_webhook_url = settings.whatsapp_webhook_url
        whatsapp_token = settings.whatsapp_token
        whatsapp_session_id = settings.whatsapp_session_id
        whatsapp_recipients = settings.whatsapp_recipients

        smtp_enabled = settings.smtp_enabled
        smtp_host = settings.smtp_host
        smtp_port = settings.smtp_port or 587
        smtp_username = settings.smtp_username
        smtp_password = settings.smtp_password
        smtp_sender = settings.smtp_sender
        smtp_recipient = settings.smtp_recipient

    # 1. Telegram Notification
    if telegram_enabled and telegram_bot_token and telegram_chat_id:
        try:
            import html
            safe_msg = html.escape(message)
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": telegram_chat_id,
                "text": f"⚠️ <b>Sentinel360 ALERT</b>\n\n{safe_msg}",
                "parse_mode": "HTML"
            }
            res = requests.post(url, json=payload, timeout=5)
            if res.ok:
                logger.info("Telegram notification sent successfully.")
            else:
                logger.error(f"Failed to send Telegram notification: {res.text}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")

    # 2. WhatsApp Webhook Notification
    if whatsapp_enabled and whatsapp_webhook_url:
        try:
            import urllib.parse
            headers = {"Content-Type": "application/json"}
            if whatsapp_token:
                headers["key"] = whatsapp_token
                headers["api_key"] = whatsapp_token
                headers["Authorization"] = f"Bearer {whatsapp_token}"
            
            # Format base URL for Open WA if session id is specified
            url = whatsapp_webhook_url
            if whatsapp_session_id:
                parsed_url = urllib.parse.urlparse(url)
                if not parsed_url.path or parsed_url.path == "/":
                    url = f"{url.rstrip('/')}/api/{whatsapp_session_id}/sendText"
            
            # Process multiple recipient phone numbers
            recipients = []
            if whatsapp_recipients:
                recipients = [r.strip() for r in whatsapp_recipients.split(",") if r.strip()]
            
            if not recipients:
                logger.warning("WhatsApp is enabled but no recipients are configured.")
            
            for rc in recipients:
                rc_formatted = rc
                if not rc_formatted.endswith("@c.us") and not rc_formatted.endswith("@g.us"):
                    rc_formatted = f"{rc}@c.us"
                
                payload = {
                    "to": rc_formatted,
                    "chatId": rc_formatted,
                    "phone": rc,
                    "message": f"⚠️ Sentinel360 ALERT: {message}",
                    "content": f"⚠️ Sentinel360 ALERT: {message}",
                    "text": f"⚠️ Sentinel360 ALERT: {message}",
                    "session": whatsapp_session_id,
                    "sessionId": whatsapp_session_id,
                    "session_id": whatsapp_session_id
                }
                
                res = requests.post(url, json=payload, headers=headers, timeout=5)
                if res.ok:
                    logger.info(f"WhatsApp notification sent successfully to {rc}.")
                else:
                    logger.error(f"Failed to send WhatsApp notification to {rc}: {res.text}")
        except Exception as e:
            logger.error(f"Error sending WhatsApp notification: {e}")

    # 3. SMTP Email Notification
    if smtp_enabled and smtp_host and smtp_username and smtp_password and smtp_recipient:
        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_sender or smtp_username
            msg["To"] = smtp_recipient
            msg["Subject"] = "⚠️ Sentinel360 ALERT"

            body = f"Hello,\n\nSentinel360 has detected a monitoring event:\n\n{message}\n\nRegards,\nSentinel360 Monitoring System"
            msg.attach(MIMEText(body, "plain"))

            port = smtp_port or 587
            if port == 465:
                server = smtplib.SMTP_SSL(smtp_host, port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, port, timeout=10)
                server.starttls()

            server.login(smtp_username, smtp_password)
            server.sendmail(msg["From"], msg["To"], msg.as_string())
            server.quit()
            logger.info("SMTP Email notification sent successfully.")
        except Exception as e:
            logger.error(f"Error sending SMTP Email notification: {e}")
