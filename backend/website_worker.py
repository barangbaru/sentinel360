import socket
import ssl
import time
import urllib.parse
from datetime import datetime
import requests
from .models import Website

def get_ssl_expiry_date(url: str):
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return None, "Invalid hostname"
    
    port = parsed.port or 443
    if parsed.scheme != "https":
        return None, "HTTP target (no SSL)"

    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expiry_str = cert.get('notAfter')
                if not expiry_str:
                    return None, "No expiry date in certificate"
                
                # Parse format: 'Oct 23 12:00:00 2026 GMT'
                expiry_date = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y %Z")
                return expiry_date, None
    except ssl.SSLCertVerificationError as e:
        return None, f"SSL verification failed: {e.reason}"
    except Exception as e:
        return None, f"SSL check error: {str(e)}"

def check_website(db, website):
    was_online = website.status == "online"
    url = website.url
    start_time = time.time()
    
    try:
        response = requests.get(url, timeout=5, headers={"User-Agent": "Sentinel360 Monitoring Bot"})
        latency_ms = (time.time() - start_time) * 1000
        
        website.status_code = response.status_code
        website.response_time = round(latency_ms, 2)
        
        if 200 <= response.status_code < 400:
            website.status = "online"
            website.error_message = None
        else:
            website.status = "offline"
            website.error_message = f"HTTP Error Status Code: {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        latency_ms = (time.time() - start_time) * 1000
        website.status = "offline"
        website.status_code = None
        website.response_time = round(latency_ms, 2)
        website.error_message = str(e)

    # Perform SSL check if it is https
    if url.startswith("https://"):
        expiry_date, ssl_error = get_ssl_expiry_date(url)
        if expiry_date:
            website.ssl_expiry = expiry_date
            delta = expiry_date - datetime.utcnow()
            days_left = delta.days
            website.ssl_days_left = days_left
            
            if days_left <= 0:
                website.ssl_status = "expired"
            elif days_left <= 14:
                website.ssl_status = "warning"
            else:
                website.ssl_status = "valid"
        else:
            website.ssl_expiry = None
            website.ssl_days_left = None
            website.ssl_status = "invalid"
            if website.error_message:
                website.error_message += f" | SSL: {ssl_error}"
            else:
                website.error_message = f"SSL: {ssl_error}"
    else:
        website.ssl_status = "none"
        website.ssl_expiry = None
        website.ssl_days_left = None

    website.last_checked = datetime.utcnow()
    
    # Handle Alerts
    is_online = website.status == "online"
    from .models import Alert
    
    if was_online and not is_online:
        alert_msg = f"Website {website.name} ({website.url}) is OFFLINE (HTTP: {website.status_code or 'FAIL'})"
        alert = Alert(
            website_id=website.id,
            timestamp=datetime.utcnow(),
            message=alert_msg,
            resolved=False
        )
        db.add(alert)
        from .notifications import send_alert_notification
        send_alert_notification(db, alert_msg)
        
    elif not was_online and is_online and website.status != "unknown":
        active_alerts = db.query(Alert).filter(
            Alert.website_id == website.id,
            Alert.resolved == False
        ).all()
        for alert in active_alerts:
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
        from .notifications import send_alert_notification
        send_alert_notification(db, f"Website {website.name} ({website.url}) is back ONLINE")
        
    db.commit()
