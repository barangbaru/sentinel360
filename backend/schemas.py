from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ServerBase(BaseModel):
    name: str
    ip_address: str
    monitor_type: str = "ping"  # "ping", "agent", "snmp"
    snmp_community: Optional[str] = "public"
    snmp_port: Optional[int] = 161
    snmp_version: Optional[str] = "2c"

class ServerCreate(ServerBase):
    pass

class ServerResponse(ServerBase):
    id: int
    status: str
    last_seen: Optional[datetime] = None
    api_key: str
    os_info: Optional[str] = None
    uptime: Optional[str] = None
    cpu_usage: Optional[float] = None
    ram_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    ram_total: Optional[float] = None
    disk_total: Optional[float] = None

    class Config:
        from_attributes = True

class PublicServerResponse(BaseModel):
    id: int
    name: str
    ip_address: str
    monitor_type: str
    status: str
    last_seen: Optional[datetime] = None
    os_info: Optional[str] = None
    uptime: Optional[str] = None
    cpu_usage: Optional[float] = None
    ram_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    ram_total: Optional[float] = None
    disk_total: Optional[float] = None

    class Config:
        from_attributes = True

class MetricHistoryResponse(BaseModel):
    id: int
    server_id: int
    timestamp: datetime
    latency: Optional[float] = None
    cpu_usage: Optional[float] = None
    ram_usage: Optional[float] = None
    ram_total: Optional[float] = None
    disk_usage: Optional[float] = None
    disk_total: Optional[float] = None
    network_rx: Optional[float] = None
    network_tx: Optional[float] = None

    class Config:
        from_attributes = True

class AlertResponse(BaseModel):
    id: int
    server_id: int
    timestamp: datetime
    message: str
    resolved: bool
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AgentMetricReport(BaseModel):
    cpu_usage: float
    ram_usage: float
    ram_total: float
    disk_usage: float
    disk_total: float
    network_rx: Optional[float] = 0.0
    network_tx: Optional[float] = 0.0
    os_info: str
    uptime: str

class WebsiteBase(BaseModel):
    name: str
    url: str

class WebsiteCreate(WebsiteBase):
    pass

class WebsiteResponse(WebsiteBase):
    id: int
    status: str
    response_time: Optional[float] = None
    status_code: Optional[int] = None
    ssl_status: str
    ssl_expiry: Optional[datetime] = None
    ssl_days_left: Optional[int] = None
    last_checked: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

class PublicWebsiteResponse(WebsiteBase):
    id: int
    status: str
    response_time: Optional[float] = None
    status_code: Optional[int] = None
    ssl_status: str
    ssl_expiry: Optional[datetime] = None
    ssl_days_left: Optional[int] = None
    last_checked: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
