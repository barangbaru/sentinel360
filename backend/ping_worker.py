import subprocess
import platform
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Server, MetricHistory, Alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PingWorker")

def system_ping(ip_address: str, timeout_sec: int = 2) -> float | None:
    """
    Fallback ping using system CLI ping command, which doesn't require administrator/root privileges.
    Returns latency in milliseconds, or None if failed.
    """
    system_name = platform.system().lower()
    
    if system_name == "windows":
        # Windows: ping -n 1 -w timeout_ms ip_address
        cmd = ["ping", "-n", "1", "-w", str(timeout_sec * 1000), ip_address]
    else:
        # Linux / MacOS: ping -c 1 -W timeout_sec ip_address
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec), ip_address]
        
    try:
        start_time = datetime.utcnow()
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec + 1)
        end_time = datetime.utcnow()
        
        if result.returncode == 0:
            # Successfully pinged
            latency = (end_time - start_time).total_seconds() * 1000.0  # convert to ms
            
            # Let's try parsing the latency from stdout for better accuracy if possible
            # Windows: "Minimum = 4ms, Maximum = 4ms, Average = 4ms" or "time=4ms"
            # Linux: "time=4.12 ms"
            stdout_lower = result.stdout.lower()
            if "time=" in stdout_lower:
                try:
                    parts = stdout_lower.split("time=")
                    if len(parts) > 1:
                        time_part = parts[1].split()[0]
                        # Remove "ms" or other text
                        time_str = "".join(c for c in time_part if c.isdigit() or c == ".")
                        return float(time_str)
                except Exception as ex:
                    logger.debug(f"Failed parsing ping output: {ex}")
            
            return latency
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"System ping failed for {ip_address}: {e}")
        
    return None

def ping3_ping(ip_address: str, timeout_sec: int = 2) -> float | None:
    """
    Tries to ping using the ping3 library.
    Returns latency in milliseconds, or None if failed.
    """
    try:
        import ping3
        # ping3.ping returns time in seconds, or None/False on failure
        res = ping3.ping(ip_address, timeout=timeout_sec)
        if res is not None and res is not False:
            return float(res) * 1000.0  # to ms
    except PermissionError:
        # Raw socket permission error (e.g. non-admin on Windows/Linux)
        logger.debug(f"ping3 requires root/admin privilege. Falling back to system CLI ping.")
    except Exception as e:
        logger.error(f"ping3 error: {e}")
    return None

def perform_ping(ip_address: str, timeout_sec: int = 2) -> float | None:
    """
    Pings a host, trying ping3 library first, and falling back to system ping if needed.
    """
    # 1. Try ping3
    latency = ping3_ping(ip_address, timeout_sec)
    if latency is not None:
        return latency
        
    # 2. Try system CLI ping
    return system_ping(ip_address, timeout_sec)

def ping_server(db: Session, server: Server):
    """
    Perform ping check on a single server, update status and store metrics.
    """
    latency = perform_ping(server.ip_address)
    
    was_online = server.status == "online"
    is_online = latency is not None
    
    server.status = "online" if is_online else "offline"
    server.last_seen = datetime.utcnow()
    
    # Save to history
    metric = MetricHistory(
        server_id=server.id,
        timestamp=datetime.utcnow(),
        latency=latency if is_online else None
    )
    db.add(metric)
    
    # Handle Alerts
    if was_online and not is_online:
        # Server went offline, create alert
        alert_msg = f"Server {server.name} ({server.ip_address}) is OFFLINE (Ping failed)"
        alert = Alert(
            server_id=server.id,
            timestamp=datetime.utcnow(),
            message=alert_msg,
            resolved=False
        )
        db.add(alert)
        logger.warning(f"ALERT: Server {server.name} ({server.ip_address}) went offline!")
        
        # Send alert
        from .notifications import send_alert_notification
        send_alert_notification(db, alert_msg)
        
    elif not was_online and is_online and server.status != "unknown":
        # Server came back online, resolve active alerts
        active_alerts = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False
        ).all()
        for alert in active_alerts:
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
        logger.info(f"Server {server.name} ({server.ip_address}) came back online. Resolved active alerts.")
        
        # Send resolution alert
        from .notifications import send_alert_notification
        send_alert_notification(db, f"Server {server.name} ({server.ip_address}) is back ONLINE")

    db.commit()
    db.refresh(server)
    return latency
