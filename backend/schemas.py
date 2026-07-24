from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class NotificationConfigBase(BaseModel):
    name: str
    type: str  # "telegram", "whatsapp", "smtp"
    is_enabled: bool = True
    
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    whatsapp_webhook_url: Optional[str] = None
    whatsapp_token: Optional[str] = None
    whatsapp_session_id: Optional[str] = None
    whatsapp_recipients: Optional[str] = None
    
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_sender: Optional[str] = None
    smtp_recipient: Optional[str] = None

class NotificationConfigCreate(NotificationConfigBase):
    pass

class NotificationConfigResponse(NotificationConfigBase):
    id: int

    class Config:
        from_attributes = True

class ServerBase(BaseModel):
    name: str
    ip_address: str
    monitor_type: str = "ping"  # "ping", "agent", "snmp"
    snmp_community: Optional[str] = "public"
    snmp_port: Optional[int] = 161
    snmp_version: Optional[str] = "2c"
    notification_ids: List[int] = []
    failed_threshold: int = 1

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
    notifications: List[NotificationConfigResponse] = []

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
    failed_threshold: int = 1
    notifications: List[NotificationConfigResponse] = []

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
    server_id: Optional[int] = None
    website_id: Optional[int] = None
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
    notification_ids: List[int] = []
    failed_threshold: int = 1

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
    notifications: List[NotificationConfigResponse] = []

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
    notifications: List[NotificationConfigResponse] = []

    class Config:
        from_attributes = True

class SystemSettingsBase(BaseModel):
    smtp_enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_sender: Optional[str] = None
    smtp_recipient: Optional[str] = None
    
    telegram_enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    whatsapp_enabled: bool = False
    whatsapp_webhook_url: Optional[str] = None
    whatsapp_token: Optional[str] = None
    whatsapp_session_id: Optional[str] = None
    whatsapp_recipients: Optional[str] = None

class SystemSettingsResponse(SystemSettingsBase):
    id: int

    class Config:
        from_attributes = True

class SystemSettingsUpdate(SystemSettingsBase):
    pass
