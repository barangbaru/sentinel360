import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from .models import Server, MetricHistory, Alert
from .schemas import (
    ServerCreate,
    ServerResponse,
    AgentMetricReport,
    AlertResponse,
    MetricHistoryResponse
)
from .scheduler import start_scheduler

# Create the SQLite tables
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the background task scheduler
    start_scheduler()
    yield

app = FastAPI(
    title="Sentinel360 Server Monitoring",
    description="Sentinel360 monitoring server for Linux and Windows",
    version="1.0.0",
    lifespan=lifespan
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
# WEB PAGE ROUTES (UI)
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html", {})

@app.get("/server/{server_id}", response_class=HTMLResponse)
async def read_server_details(request: Request, server_id: int):
    return templates.TemplateResponse(request, "server_detail.html", {"server_id": server_id})

# ==========================================
# REST API ENDPOINTS
# ==========================================

@app.post("/api/servers", response_model=ServerResponse, status_code=status.HTTP_201_CREATED)
def create_server(server_in: ServerCreate, db: Session = Depends(get_db)):
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
def list_servers(db: Session = Depends(get_db)):
    """
    Get all registered servers and their current status/latest metrics.
    """
    return db.query(Server).all()

@app.get("/api/servers/{server_id}", response_model=ServerResponse)
def get_server(server_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information for a single server.
    """
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server

@app.delete("/api/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_server(server_id: int, db: Session = Depends(get_db)):
    """
    Delete a registered server from Sentinel360.
    """
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    db.delete(server)
    db.commit()
    return

@app.get("/api/servers/{server_id}/metrics", response_model=List[MetricHistoryResponse])
def get_server_metrics(server_id: int, hours: int = 12, db: Session = Depends(get_db)):
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
def list_alerts(resolved: Optional[bool] = False, db: Session = Depends(get_db)):
    """
    Get active or resolved alerts list.
    """
    query = db.query(Alert)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    return query.order_by(Alert.timestamp.desc()).all()

@app.post("/api/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
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
            
    # Check threshold alerts (e.g. CPU > 90%)
    if report.cpu_usage > 90.0:
        existing_cpu = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False,
            Alert.message.like("High CPU usage%")
        ).first()
        if not existing_cpu:
            db.add(Alert(
                server_id=server.id,
                timestamp=datetime.utcnow(),
                message=f"High CPU usage on {server.name}: {report.cpu_usage:.1f}%",
                resolved=False
            ))
            
    if report.ram_usage > 90.0:
        existing_ram = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False,
            Alert.message.like("High RAM usage%")
        ).first()
        if not existing_ram:
            db.add(Alert(
                server_id=server.id,
                timestamp=datetime.utcnow(),
                message=f"High RAM usage on {server.name}: {report.ram_usage:.1f}%",
                resolved=False
            ))
            
    db.commit()
    return {"status": "ok", "message": "Metrics received successfully."}
