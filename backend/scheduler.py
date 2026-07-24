import time
import threading
import logging
from datetime import datetime, timedelta
from .database import SessionLocal
from .models import Server, Alert, MetricHistory, Website
from .ping_worker import ping_server
from .snmp_worker import poll_snmp_server
from .website_worker import check_website

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Scheduler")

def scheduler_loop():
    logger.info("Background Sentinel360 scheduler loop started.")
    while True:
        db = SessionLocal()
        try:
            servers = db.query(Server).all()
            for server in servers:
                if server.monitor_type == "ping":
                    try:
                        ping_server(db, server)
                    except Exception as e:
                        logger.error(f"Error pinging {server.name} ({server.ip_address}): {e}")
                        
                elif server.monitor_type == "snmp":
                    try:
                        poll_snmp_server(db, server)
                    except Exception as e:
                        logger.error(f"Error SNMP polling {server.name} ({server.ip_address}): {e}")
                        
                elif server.monitor_type == "agent":
                    # If monitor_type is agent, we don't actively poll, we just check
                    # if the agent has reported within the last 60 seconds.
                    was_online = server.status == "online"
                    
                    if server.last_seen:
                        diff = datetime.utcnow() - server.last_seen
                        is_timeout = diff > timedelta(seconds=60)
                    else:
                        is_timeout = True
                        diff = None
                        
                    if is_timeout:
                        server.status = "offline"
                        # Set current performance usage to None since agent is gone
                        server.cpu_usage = None
                        server.ram_usage = None
                        server.disk_usage = None
                        
                        # Store offline metrics history
                        db.add(MetricHistory(
                            server_id=server.id,
                            timestamp=datetime.utcnow()
                        ))
                        
                        if was_online or server.status == "unknown":
                            # Check if alert already exists
                            last_seen_str = f"{diff.total_seconds():.0f}s ago" if diff else "never"
                            alert_msg = f"Agent on {server.name} ({server.ip_address}) has stopped reporting (last seen: {last_seen_str})"
                            
                            existing_alert = db.query(Alert).filter(
                                Alert.server_id == server.id,
                                Alert.resolved == False,
                                Alert.message.like("Agent on % stopped reporting")
                            ).first()
                            
                            if not existing_alert:
                                alert = Alert(
                                    server_id=server.id,
                                    timestamp=datetime.utcnow(),
                                    message=alert_msg,
                                    resolved=False
                                )
                                db.add(alert)
                                logger.warning(f"ALERT: {alert_msg}")
                                
                                # Send alert
                                from .notifications import send_alert_notification
                                send_alert_notification(db, alert_msg, server.notification_group_id)
                                
                        db.commit()

            # Polling website status by URL
            websites = db.query(Website).all()
            for website in websites:
                try:
                    check_website(db, website)
                except Exception as e:
                    logger.error(f"Error checking website {website.name} ({website.url}): {e}")
        except Exception as e:
            logger.error(f"Scheduler exception: {e}")
        finally:
            db.close()
            
        time.sleep(15)  # Run polling cycle every 15 seconds

def start_scheduler():
    t = threading.Thread(target=scheduler_loop, daemon=True, name="Sentinel360Scheduler")
    t.start()
    logger.info("Sentinel360 scheduler thread spawned.")
