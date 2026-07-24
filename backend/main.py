import os
import hmac
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from .database import engine, get_db, Base, SessionLocal
from .models import Server, MetricHistory, Alert, User, Website, SystemSettings
from .schemas import (
    ServerCreate,
    ServerResponse,
    AgentMetricReport,
    AlertResponse,
    MetricHistoryResponse,
    PublicServerResponse,
    WebsiteCreate,
    WebsiteResponse,
    PublicWebsiteResponse,
    SystemSettingsResponse,
    SystemSettingsUpdate
)
from .scheduler import start_scheduler

# Create the SQLite tables
Base.metadata.create_all(bind=engine)

# Add missing columns dynamically for SQLite if they don't exist
db = SessionLocal()
try:
    from sqlalchemy import text
    from .models import SystemSettings
    # Fetch column names
    res = db.execute(text("PRAGMA table_info(servers)")).fetchall()
    columns = [row[1] for row in res]
    if "ram_total" not in columns:
        db.execute(text("ALTER TABLE servers ADD COLUMN ram_total FLOAT"))
        print("Migration: Added ram_total column to servers table.")
    if "disk_total" not in columns:
        db.execute(text("ALTER TABLE servers ADD COLUMN disk_total FLOAT"))
        print("Migration: Added disk_total column to servers table.")
        
    res_alerts = db.execute(text("PRAGMA table_info(alerts)")).fetchall()
    alerts_cols = [row[1] for row in res_alerts]
    if "website_id" not in alerts_cols:
        db.execute(text("ALTER TABLE alerts ADD COLUMN website_id INTEGER"))
        print("Migration: Added website_id column to alerts table.")
    if "resolved_at" not in alerts_cols:
        db.execute(text("ALTER TABLE alerts ADD COLUMN resolved_at DATETIME"))
        print("Migration: Added resolved_at column to alerts table.")
        
    res_settings = db.execute(text("PRAGMA table_info(system_settings)")).fetchall()
    settings_cols = [row[1] for row in res_settings]
    if "whatsapp_session_id" not in settings_cols:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN whatsapp_session_id VARCHAR"))
        print("Migration: Added whatsapp_session_id column to system_settings.")
    if "whatsapp_recipients" not in settings_cols:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN whatsapp_recipients VARCHAR"))
        print("Migration: Added whatsapp_recipients column to system_settings.")

    # Seed default system settings
    settings = db.query(SystemSettings).first()
    if not settings:
        settings = SystemSettings()
        db.add(settings)
        print("Initial System Settings seeded.")
    db.commit()
except Exception as e:
    print(f"Migration error: {e}")
finally:
    db.close()

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

# ==========================================
# PASSWORD HASHING UTILITIES
# ==========================================
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}:{key.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt_hex, key_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return hmac.compare_digest(key, new_key)
    except Exception:
        return False

# ==========================================
# AUTHENTICATION DEPENDENCIES
# ==========================================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        if request.url.path.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        request.session.clear()
        if request.url.path.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    return user

def require_role(allowed_roles: List[str]):
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: insufficient permissions"
            )
        return current_user
    return dependency

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the background task scheduler
    start_scheduler()
    
    # Seed default users
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin_user = User(
                username="admin",
                password_hash=hash_password("admin123"),
                role="admin"
            )
            view_user = User(
                username="viewer",
                password_hash=hash_password("viewer123"),
                role="view"
            )
            db.add(admin_user)
            db.add(view_user)
            db.commit()
            print("Successfully seeded default Sentinel360 users:")
            print("  Admin : admin / admin123")
            print("  Viewer: viewer / viewer123")
    except Exception as e:
        print(f"Error seeding default users: {e}")
    finally:
        db.close()
    yield

def get_app_version() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_version_path = os.path.join(base_dir, "version.txt")
    if os.path.exists(backend_version_path):
        try:
            with open(backend_version_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
            
    root_version_path = os.path.join(base_dir, "..", "version.txt")
    if os.path.exists(root_version_path):
        try:
            with open(root_version_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
            
    try:
        import subprocess
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        pass
        
    return "v1.0.0"

app = FastAPI(
    title="Sentinel360 Server Monitoring",
    description="Sentinel360 monitoring server for Linux and Windows",
    version=get_app_version(),
    lifespan=lifespan
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "sentinel360-very-secret-session-key"),
    max_age=3600 * 24
)

# Setup directories for static files and Jinja2 templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
templates_dir = os.path.join(BASE_DIR, "templates")

# Ensure static and template directories exist
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html", {"error": None})

@app.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    
    if not username or not password:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Username dan password wajib diisi"}
        )
        
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Username atau password salah"}
        )
        
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/user/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password lama salah"
        )
    current_user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"detail": "Password berhasil diubah"}

# ==========================================
# WEB PAGE ROUTES (UI)
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "index.html", {
        "username": current_user.username,
        "role": current_user.role,
        "version": app.version
    })

@app.get("/server/{server_id}", response_class=HTMLResponse)
async def read_server_details(request: Request, server_id: int, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "server_detail.html", {
        "server_id": server_id,
        "username": current_user.username,
        "role": current_user.role,
        "version": app.version
    })

@app.get("/tv", response_class=HTMLResponse)
async def read_tv_dashboard(request: Request):
    return templates.TemplateResponse(request, "tv.html", {})

# ==========================================
# REST API ENDPOINTS
# ==========================================

@app.post("/api/servers", response_model=ServerResponse, status_code=status.HTTP_201_CREATED)
def create_server(
    server_in: ServerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Register a new server to monitor.
    """
    # Check if IP address is unique
    existing = db.query(Server).filter(Server.ip_address == server_in.ip_address).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Server with IP address '{server_in.ip_address}' is already registered."
        )
        
    db_server = Server(
        name=server_in.name,
        ip_address=server_in.ip_address,
        monitor_type=server_in.monitor_type,
        snmp_community=server_in.snmp_community,
        snmp_port=server_in.snmp_port,
        snmp_version=server_in.snmp_version,
        status="unknown"
    )
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    return db_server

@app.get("/api/servers", response_model=List[ServerResponse])
def list_servers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "view"]))
):
    """
    Get all registered servers and their current status/latest metrics.
    """
    return db.query(Server).all()

@app.get("/api/public/servers", response_model=List[PublicServerResponse])
def list_public_servers(
    db: Session = Depends(get_db)
):
    """
    Get all registered servers for the public TV display (no login required, strips sensitive API keys).
    """
    return db.query(Server).all()

@app.get("/api/servers/{server_id}", response_model=ServerResponse)
def get_server(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "view"]))
):
    """
    Get detailed information for a single server.
    """
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server

@app.delete("/api/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_server(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Delete a registered server from Sentinel360.
    """
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    db.delete(server)
    db.commit()
    return

@app.get("/api/websites", response_model=List[WebsiteResponse])
def list_websites(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "view"]))
):
    """
    Get all registered website monitors.
    """
    return db.query(Website).all()

@app.post("/api/websites", response_model=WebsiteResponse)
def create_website(
    website: WebsiteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Add a new website monitor.
    """
    existing = db.query(Website).filter(Website.url == website.url).first()
    if existing:
        raise HTTPException(status_code=400, detail="Website URL already registered")
        
    db_website = Website(
        name=website.name,
        url=website.url,
        status="unknown"
    )
    db.add(db_website)
    db.commit()
    db.refresh(db_website)
    return db_website

@app.delete("/api/websites/{website_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_website(
    website_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Delete a website monitor from database.
    """
    website = db.query(Website).filter(Website.id == website_id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    db.delete(website)
    db.commit()
    return

@app.get("/api/public/websites", response_model=List[PublicWebsiteResponse])
def list_public_websites(
    db: Session = Depends(get_db)
):
    """
    Get all registered websites for the public TV display (no login required).
    """
    return db.query(Website).all()


@app.get("/api/servers/{server_id}/metrics", response_model=List[MetricHistoryResponse])
def get_server_metrics(
    server_id: int,
    hours: int = 12,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "view"]))
):
    """
    Get historical metric data for a specific server (default past 12 hours).
    """
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
        
    since = datetime.utcnow() - timedelta(hours=hours)
    metrics = (
        db.query(MetricHistory)
        .filter(MetricHistory.server_id == server_id, MetricHistory.timestamp >= since)
        .order_by(MetricHistory.timestamp.asc())
        .all()
    )
    return metrics

@app.get("/api/alerts", response_model=List[AlertResponse])
def list_alerts(
    resolved: Optional[bool] = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "view"]))
):
    """
    Get active or resolved alerts list.
    """
    query = db.query(Alert)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    return query.order_by(Alert.timestamp.desc()).all()

@app.post("/api/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Manually resolve an active alert.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert

# ==========================================
# AGENT METRIC INGESTION ENDPOINT
# ==========================================

@app.post("/api/agent/report", status_code=status.HTTP_200_OK)
def agent_report(
    report: AgentMetricReport,
    x_api_key: str = Header(..., description="API Key generated by Sentinel360 for authentication"),
    db: Session = Depends(get_db)
):
    """
    Receives resource usage payload from a running Sentinel360 agent.
    """
    server = db.query(Server).filter(Server.api_key == x_api_key, Server.monitor_type == "agent").first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key or server not configured for agent monitoring."
        )
        
    was_online = server.status == "online"
    
    # Update Server state
    server.status = "online"
    server.last_seen = datetime.utcnow()
    server.os_info = report.os_info
    server.uptime = report.uptime
    server.cpu_usage = report.cpu_usage
    server.ram_usage = report.ram_usage
    server.disk_usage = report.disk_usage
    server.ram_total = report.ram_total
    server.disk_total = report.disk_total
    
    # Store metrics record
    metric = MetricHistory(
        server_id=server.id,
        timestamp=datetime.utcnow(),
        cpu_usage=report.cpu_usage,
        ram_usage=report.ram_usage,
        ram_total=report.ram_total,
        disk_usage=report.disk_usage,
        disk_total=report.disk_total,
        network_rx=report.network_rx,
        network_tx=report.network_tx
    )
    db.add(metric)
    
    # Resolve any previous offline alerts for this server
    if not was_online:
        active_offline_alerts = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False,
            Alert.message.like("%has stopped reporting%") | Alert.message.like("%is OFFLINE%")
        ).all()
        for alert in active_offline_alerts:
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
        from .notifications import send_alert_notification
        send_alert_notification(db, f"Agent on {server.name} ({server.ip_address}) came back ONLINE")
            
    # Check threshold alerts (e.g. CPU > 90%)
    if report.cpu_usage > 90.0:
        existing_cpu = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False,
            Alert.message.like("High CPU usage%")
        ).first()
        if not existing_cpu:
            msg = f"High CPU usage on {server.name}: {report.cpu_usage:.1f}%"
            db.add(Alert(
                server_id=server.id,
                timestamp=datetime.utcnow(),
                message=msg,
                resolved=False
            ))
            from .notifications import send_alert_notification
            send_alert_notification(db, msg)
            
    if report.ram_usage > 90.0:
        existing_ram = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False,
            Alert.message.like("High RAM usage%")
        ).first()
        if not existing_ram:
            msg = f"High RAM usage on {server.name}: {report.ram_usage:.1f}%"
            db.add(Alert(
                server_id=server.id,
                timestamp=datetime.utcnow(),
                message=msg,
                resolved=False
            ))
            from .notifications import send_alert_notification
            send_alert_notification(db, msg)
            
    db.commit()
    return {"status": "ok", "message": "Metrics received successfully."}

@app.get("/api/settings", response_model=SystemSettingsResponse)
def get_system_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Get system alarm/notification settings.
    """
    settings = db.query(SystemSettings).first()
    if not settings:
        settings = SystemSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

@app.put("/api/settings", response_model=SystemSettingsResponse)
def update_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Update system alarm/notification settings.
    """
    settings = db.query(SystemSettings).first()
    if not settings:
        settings = SystemSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
        
    for field, val in payload.model_dump().items():
        setattr(settings, field, val)
        
    db.commit()
    db.refresh(settings)
    return settings

@app.post("/api/settings/test")
def test_system_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Sends a test alarm message to all enabled pathways.
    """
    from .notifications import send_alert_notification
    test_msg = "Ini adalah notifikasi uji coba dari Sentinel360 Monitoring!"
    send_alert_notification(db, test_msg)
    return {"status": "ok", "message": "Test message sent to enabled channels."}
