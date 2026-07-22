import os
import sys
import time
import json
import platform
import logging
import requests
import psutil
from datetime import datetime

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Sentinel360Agent")

CONFIG_FILE = "agent_config.json"

def get_default_config():
    return {
        "server_url": "http://localhost:8000",
        "api_key": "YOUR_API_KEY_HERE",
        "interval_seconds": 15
    }

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default = get_default_config()
        with open(CONFIG_FILE, "w") as f:
            json.dump(default, f, indent=4)
        logger.info(f"Created default configuration file: {CONFIG_FILE}")
        logger.info("Please edit this file and provide your correct server_url and api_key.")
        return default
        
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading configuration file: {e}")
        return get_default_config()

def get_os_info():
    system = platform.system()
    release = platform.release()
    version = platform.version()
    arch = platform.machine()
    return f"{system} {release} ({arch})"

def get_uptime():
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    
    days = int(uptime_seconds // (24 * 3600))
    uptime_seconds %= (24 * 3600)
    hours = int(uptime_seconds // 3600)
    uptime_seconds %= 3600
    minutes = int(uptime_seconds // 60)
    seconds = int(uptime_seconds % 60)
    
    uptime_str = ""
    if days > 0:
        uptime_str += f"{days} day(s), "
    uptime_str += f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return uptime_str

def get_disk_partition():
    # Detect main system partition
    if platform.system() == "Windows":
        return "C:\\"
    return "/"

def main():
    logger.info("Starting Sentinel360 Client Agent...")
    config = load_config()
    
    server_url = config.get("server_url", "http://localhost:8000").rstrip("/")
    api_key = config.get("api_key", "YOUR_API_KEY_HERE")
    interval = config.get("interval_seconds", 15)
    
    if api_key == "YOUR_API_KEY_HERE":
        logger.warning("Agent API Key is still default! Please edit agent_config.json with the correct key.")
        
    report_url = f"{server_url}/api/agent/report"
    
    # Initialize network stats for speed calculation
    net_old = psutil.net_io_counters()
    time_old = time.time()
    
    # Give psutil.cpu_percent a warm up
    psutil.cpu_percent(interval=None)
    
    logger.info(f"Sentinel360 Server URL: {server_url}")
    logger.info(f"Report Interval: {interval} seconds")
    
    while True:
        try:
            # 1. CPU Usage
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # 2. RAM Usage
            mem = psutil.virtual_memory()
            ram_usage = mem.percent
            ram_total_gb = mem.total / (1024**3)
            
            # 3. Disk Usage (System Drive)
            part = get_disk_partition()
            try:
                disk = psutil.disk_usage(part)
                disk_usage = disk.percent
                disk_total_gb = disk.total / (1024**3)
            except Exception:
                disk_usage = 0.0
                disk_total_gb = 0.0
                
            # 4. Network I/O Speed
            net_new = psutil.net_io_counters()
            time_new = time.time()
            
            elapsed = time_new - time_old
            if elapsed <= 0:
                elapsed = 1.0
                
            # Convert bytes to Kilobits per second (Kbps)
            rx_speed = ((net_new.bytes_recv - net_old.bytes_recv) * 8) / (elapsed * 1024)
            tx_speed = ((net_new.bytes_sent - net_old.bytes_sent) * 8) / (elapsed * 1024)
            
            # Save stats for next cycle
            net_old = net_new
            time_old = time_new
            
            # 5. OS & Uptime
            os_info = get_os_info()
            uptime = get_uptime()
            
            # Prepare payload
            payload = {
                "cpu_usage": round(cpu_usage, 2),
                "ram_usage": round(ram_usage, 2),
                "ram_total": round(ram_total_gb, 2),
                "disk_usage": round(disk_usage, 2),
                "disk_total": round(disk_total_gb, 2),
                "network_rx": round(rx_speed, 2),
                "network_tx": round(tx_speed, 2),
                "os_info": os_info,
                "uptime": uptime
            }
            
            # Send report
            headers = {
                "Content-Type": "application/json",
                "X-Api-Key": api_key
            }
            
            logger.info(f"Sending metrics: CPU={payload['cpu_usage']}% RAM={payload['ram_usage']}% Disk={payload['disk_usage']}%")
            
            response = requests.post(report_url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info("Metrics reported successfully.")
            else:
                logger.error(f"Failed to report metrics. Server responded with status: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as re:
            logger.error(f"Connection error to Sentinel360 Server: {re}")
        except Exception as e:
            logger.error(f"Unexpected error in agent loop: {e}")
            
        # Sleep for the configured interval minus the 1 second block in cpu_percent
        sleep_time = max(1, interval - 1)
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
