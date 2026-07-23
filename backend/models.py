import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False, unique=True, index=True)
    monitor_type = Column(String, default="ping")  # "ping", "agent", "snmp"
    status = Column(String, default="unknown")     # "online", "offline", "unknown"
    last_seen = Column(DateTime, nullable=True)
    api_key = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # SNMP Specifics
    snmp_community = Column(String, default="public")
    snmp_port = Column(Integer, default=161)
    snmp_version = Column(String, default="2c")
    
    # OS Information (reported by agent/SNMP)
    os_info = Column(String, nullable=True)
    uptime = Column(String, nullable=True)
    
    # Latest known metrics (for quick retrieval)
    cpu_usage = Column(Float, nullable=True)
    ram_usage = Column(Float, nullable=True)
    disk_usage = Column(Float, nullable=True)
    ram_total = Column(Float, nullable=True)
    disk_total = Column(Float, nullable=True)

    metrics = relationship("MetricHistory", back_populates="server", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="server", cascade="all, delete-orphan")

class MetricHistory(Base):
    __tablename__ = "metric_history"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    latency = Column(Float, nullable=True)       # Ping latency in ms
    cpu_usage = Column(Float, nullable=True)     # CPU usage %
    ram_usage = Column(Float, nullable=True)     # RAM usage %
    ram_total = Column(Float, nullable=True)     # RAM total in GB
    disk_usage = Column(Float, nullable=True)    # Disk usage %
    disk_total = Column(Float, nullable=True)    # Disk total in GB
    network_rx = Column(Float, nullable=True)    # Network received (Kbps)
    network_tx = Column(Float, nullable=True)    # Network sent (Kbps)

    server = relationship("Server", back_populates="metrics")

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(String, nullable=False)
    resolved = Column(Boolean, default=False)
    server = relationship("Server", back_populates="alerts")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="view", nullable=False)  # "admin" or "view"
    is_active = Column(Boolean, default=True, nullable=False)
