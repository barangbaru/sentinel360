import logging
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Server, MetricHistory, Alert

# High-level synchronous SNMP API
from pysnmp.hlapi import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
    nextCmd
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SNMPWorker")

# Standard OIDs
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_HR_SYSTEM_UPTIME = "1.3.6.1.2.1.25.1.1.0"
OID_HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"
OID_HR_STORAGE_ENTRY = "1.3.6.1.2.1.25.2.3.1"

# hrStorageTypes
OID_RAM_TYPE = "1.3.6.1.2.1.25.2.1.2"  # hrStorageRam
OID_DISK_TYPE = "1.3.6.1.2.1.25.2.1.4" # hrStorageFixedDisk

def snmp_get_single(ip: str, port: int, community: str, oid: str, timeout: int = 2) -> str | None:
    """
    Perform an SNMP Get for a single OID.
    """
    try:
        iterator = getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1), # mpModel=1 -> SNMPv2c
            UdpTransportTarget((ip, port), timeout=timeout, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
        
        if errorIndication:
            logger.debug(f"SNMP get error indication for {ip}:{oid}: {errorIndication}")
            return None
        elif errorStatus:
            logger.debug(f"SNMP get error status for {ip}:{oid}: {errorStatus.prettyPrint()}")
            return None
        else:
            for varBind in varBinds:
                val = varBind[1]
                # Check for SNMP null/exceptions
                if val is not None and not val.isSameTypeWith(ObjectType):
                    return str(val)
    except Exception as e:
        logger.error(f"SNMP get exception for {ip}:{oid}: {e}")
    return None

def snmp_walk(ip: str, port: int, community: str, oid_prefix: str, timeout: int = 2) -> list:
    """
    Perform an SNMP Walk (NextCmd) for a prefix.
    Returns a list of tuples (oid_str, value_str)
    """
    results = []
    try:
        iterator = nextCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((ip, port), timeout=timeout, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid_prefix)),
            lexicographicMode=False
        )
        
        for errorIndication, errorStatus, errorIndex, varBinds in iterator:
            if errorIndication or errorStatus:
                break
            for varBind in varBinds:
                curr_oid = str(varBind[0])
                if not curr_oid.startswith(oid_prefix):
                    break
                results.append((curr_oid, varBind[1]))
    except Exception as e:
        logger.error(f"SNMP walk exception for {ip}:{oid_prefix}: {e}")
    return results

def format_uptime(ticks_str: str) -> str:
    """
    Formats SNMP timeticks uptime (1/100 of a second) to a readable format (e.g. 5 days, 04:32:11)
    """
    try:
        ticks = int(ticks_str)
        seconds = ticks // 100
        days = seconds // (24 * 3600)
        seconds %= (24 * 3600)
        hours = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        
        uptime_str = ""
        if days > 0:
            uptime_str += f"{days} day(s), "
        uptime_str += f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return uptime_str
    except ValueError:
        return ticks_str

def poll_snmp_server(db: Session, server: Server) -> bool:
    """
    Polls target server via SNMP and updates DB.
    Returns True if successfully polled, False if unreachable.
    """
    ip = server.ip_address
    port = server.snmp_port or 161
    comm = server.snmp_community or "public"
    
    # 1. Test connectivity & get basic info (SysDescr & Uptime)
    sys_descr = snmp_get_single(ip, port, comm, OID_SYS_DESCR)
    if sys_descr is None:
        # Device is offline / unreachable via SNMP
        was_online = server.status == "online"
        server.consecutive_failures = (server.consecutive_failures or 0) + 1
        threshold = server.failed_threshold or 1
        
        # Add offline metrics record
        metric = MetricHistory(
            server_id=server.id,
            timestamp=datetime.utcnow()
        )
        db.add(metric)
        
        # Handle alert
        if server.consecutive_failures >= threshold:
            if was_online or server.status == "unknown":
                server.status = "offline"
                server.last_seen = datetime.utcnow()
                
                alert_msg = f"Server {server.name} ({server.ip_address}) is OFFLINE (SNMP query failed {server.consecutive_failures} times)"
                alert = Alert(
                    server_id=server.id,
                    timestamp=datetime.utcnow(),
                    message=alert_msg,
                    resolved=False
                )
                db.add(alert)
                logger.warning(f"ALERT: SNMP Server {server.name} went offline.")
                from .notifications import send_alert_notification
                if server.notification_groups:
                    for group in server.notification_groups:
                        send_alert_notification(db, alert_msg, group.id)
                else:
                    send_alert_notification(db, alert_msg, None)
        else:
            logger.info(f"SNMP Server {server.name} query failed ({server.consecutive_failures}/{threshold} attempts)")
        
        db.commit()
        return False
        
    # Device is online!
    sys_uptime_raw = snmp_get_single(ip, port, comm, OID_SYS_UPTIME) or snmp_get_single(ip, port, comm, OID_HR_SYSTEM_UPTIME)
    uptime = format_uptime(sys_uptime_raw) if sys_uptime_raw else "Unknown"
    
    # 2. Get CPU Load
    cpu_loads = []
    # Walk hrProcessorLoad
    processor_binds = snmp_walk(ip, port, comm, OID_HR_PROCESSOR_LOAD)
    for oid, val in processor_binds:
        try:
            cpu_loads.append(float(val))
        except (ValueError, TypeError):
            pass
            
    avg_cpu = sum(cpu_loads) / len(cpu_loads) if cpu_loads else None
    
    # 3. Get Memory and Disk (Walk hrStorageTable: 1.3.6.1.2.1.25.2.3.1)
    storage_binds = snmp_walk(ip, port, comm, OID_HR_STORAGE_ENTRY)
    
    # We will reconstruct the storage table entries.
    # hrStorageEntry has columns:
    # .1 (index), .2 (type), .3 (descr), .4 (allocation units), .5 (size), .6 (used)
    storage_table = {}
    for oid_str, val in storage_binds:
        parts = oid_str.split(OID_HR_STORAGE_ENTRY + ".")
        if len(parts) > 1:
            col_and_index = parts[1].split(".")
            if len(col_and_index) == 2:
                col, idx = int(col_and_index[0]), int(col_and_index[1])
                if idx not in storage_table:
                    storage_table[idx] = {}
                storage_table[idx][col] = val
                
    ram_usage_pct = None
    ram_total_gb = None
    
    disk_total_units = 0
    disk_used_units = 0
    disk_allocation_units = 0
    
    for idx, cols in storage_table.items():
        st_type = str(cols.get(2, ""))
        descr = str(cols.get(3, ""))
        units = int(cols.get(4, 0))
        size = int(cols.get(5, 0))
        used = int(cols.get(6, 0))
        
        if size == 0 or units == 0:
            continue
            
        # RAM
        if st_type.endswith(OID_RAM_TYPE) or "physical memory" in descr.lower():
            ram_total_gb = (size * units) / (1024**3)
            ram_usage_pct = (used / size) * 100.0
            
        # Hard Disks (Fixed Disk)
        elif st_type.endswith(OID_DISK_TYPE) or "fixed disk" in descr.lower() or "/" in descr or (platform.system().lower() != "windows" and "hrstoragedisk" in st_type.lower()):
            disk_total_units += size
            disk_used_units += used
            # Set allocation units (typically 4096 or similar, take the last one or average)
            disk_allocation_units = units

    disk_usage_pct = None
    disk_total_gb = None
    if disk_total_units > 0:
        disk_total_gb = (disk_total_units * disk_allocation_units) / (1024**3)
        disk_usage_pct = (disk_used_units / disk_total_units) * 100.0

    # 4. Save to Database
    was_online = server.status == "online"
    server.status = "online"
    server.last_seen = datetime.utcnow()
    server.os_info = str(sys_descr)
    server.uptime = uptime
    server.cpu_usage = avg_cpu
    server.ram_usage = ram_usage_pct
    server.disk_usage = disk_usage_pct
    server.ram_total = ram_total_gb
    server.disk_total = disk_total_gb
    
    metric = MetricHistory(
        server_id=server.id,
        timestamp=datetime.utcnow(),
        cpu_usage=avg_cpu,
        ram_usage=ram_usage_pct,
        ram_total=ram_total_gb,
        disk_usage=disk_usage_pct,
        disk_total=disk_total_gb
    )
    db.add(metric)
    
    server.consecutive_failures = 0
    server.status = "online"
    # Resolve any offline alerts
    if not was_online:
        active_alerts = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False
        ).all()
        for alert in active_alerts:
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
        logger.info(f"SNMP Server {server.name} came back online. Resolved active alerts.")
        from .notifications import send_alert_notification
        if server.notification_groups:
            for group in server.notification_groups:
                send_alert_notification(db, f"Server {server.name} ({server.ip_address}) is back ONLINE", group.id)
        else:
            send_alert_notification(db, f"Server {server.name} ({server.ip_address}) is back ONLINE", None)
        
    # Check threshold alerts (e.g. CPU/RAM > 90%)
    if avg_cpu and avg_cpu > 90.0:
        # Check if we already have an active CPU alert
        existing_cpu_alert = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False,
            Alert.message.like("%CPU usage exceeds%") | Alert.message.like("High CPU usage%")
        ).first()
        if not existing_cpu_alert:
            msg = f"High CPU usage on {server.name}: {avg_cpu:.1f}%"
            db.add(Alert(
                server_id=server.id,
                timestamp=datetime.utcnow(),
                message=msg,
                resolved=False
            ))
            from .notifications import send_alert_notification
            if server.notification_groups:
                for group in server.notification_groups:
                    send_alert_notification(db, msg, group.id)
            else:
                send_alert_notification(db, msg, None)
            
    if ram_usage_pct and ram_usage_pct > 90.0:
        existing_ram_alert = db.query(Alert).filter(
            Alert.server_id == server.id,
            Alert.resolved == False,
            Alert.message.like("%RAM usage exceeds%") | Alert.message.like("High RAM usage%")
        ).first()
        if not existing_ram_alert:
            msg = f"High RAM usage on {server.name}: {ram_usage_pct:.1f}%"
            db.add(Alert(
                server_id=server.id,
                timestamp=datetime.utcnow(),
                message=msg,
                resolved=False
            ))
            from .notifications import send_alert_notification
            if server.notification_groups:
                for group in server.notification_groups:
                    send_alert_notification(db, msg, group.id)
            else:
                send_alert_notification(db, msg, None)

    db.commit()
    db.refresh(server)
    return True
