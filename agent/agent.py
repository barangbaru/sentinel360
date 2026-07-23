import os
import sys
import time
import json
import platform
import logging
import requests
import psutil
import threading
from datetime import datetime

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

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
        # Try to look in the directory of the executable if running as compiled exe
        exe_dir = os.path.dirname(sys.executable)
        config_path = os.path.join(exe_dir, CONFIG_FILE)
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        
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
    if platform.system() == "Windows":
        return "C:\\"
    return "/"

def create_battery_icon(percent, plugged):
    # Create a 64x64 transparent image
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Battery body
    draw.rounded_rectangle([10, 18, 48, 46], radius=5, outline=(255, 255, 255, 255), width=3)
    # Battery tip
    draw.rectangle([48, 27, 53, 37], fill=(255, 255, 255, 255))
    
    # Fill based on percentage
    fill_width = int(32 * (percent / 100))
    if fill_width > 0:
        if percent <= 20:
            color = (239, 68, 68, 255) # Red
        elif percent <= 50:
            color = (245, 158, 11, 255) # Orange/Yellow
        else:
            color = (16, 185, 129, 255) # Green
            
        draw.rounded_rectangle([13, 21, 13 + fill_width, 43], radius=2, fill=color)
        
    if plugged:
        # Charging lightning bolt
        draw.polygon([(26, 20), (32, 29), (27, 29), (30, 42), (22, 32), (27, 32)], fill=(255, 255, 0, 255))
        
    return img

def report_loop(server_url, api_key, interval):
    report_url = f"{server_url}/api/agent/report"
    net_old = psutil.net_io_counters()
    time_old = time.time()
    psutil.cpu_percent(interval=None)
    
    while True:
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            ram_usage = mem.percent
            ram_total_gb = mem.total / (1024**3)
            
            part = get_disk_partition()
            try:
                disk = psutil.disk_usage(part)
                disk_usage = disk.percent
                disk_total_gb = disk.total / (1024**3)
            except Exception:
                disk_usage = 0.0
                disk_total_gb = 0.0
                
            net_new = psutil.net_io_counters()
            time_new = time.time()
            elapsed = time_new - time_old
            if elapsed <= 0: elapsed = 1.0
            
            rx_speed = ((net_new.bytes_recv - net_old.bytes_recv) * 8) / (elapsed * 1024)
            tx_speed = ((net_new.bytes_sent - net_old.bytes_sent) * 8) / (elapsed * 1024)
            
            net_old = net_new
            time_old = time_new
            
            os_info = get_os_info()
            uptime = get_uptime()
            
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
            
            headers = {
                "Content-Type": "application/json",
                "X-Api-Key": api_key
            }
            
            logger.info(f"Sending metrics: CPU={payload['cpu_usage']}% RAM={payload['ram_usage']}% Disk={payload['disk_usage']}%")
            response = requests.post(report_url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info("Metrics reported successfully.")
            else:
                logger.error(f"Failed to report metrics: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error in agent report loop: {e}")
            
        sleep_time = max(1, interval - 1)
        time.sleep(sleep_time)

def main():
    logger.info("Starting Sentinel360 Client Agent...")
    config = load_config()
    
    server_url = config.get("server_url", "http://localhost:8000").rstrip("/")
    api_key = config.get("api_key", "YOUR_API_KEY_HERE")
    interval = config.get("interval_seconds", 15)
    
    if api_key == "YOUR_API_KEY_HERE":
        logger.warning("Agent API Key is still default!")
        
    # Check for --tray argument
    use_tray = "--tray" in sys.argv
    
    if use_tray and TRAY_AVAILABLE:
        # Start reporter loop in background thread
        reporter_thread = threading.Thread(target=report_loop, args=(server_url, api_key, interval), daemon=True)
        reporter_thread.start()
        
        # System Tray Exit Callback
        def on_exit(icon, item):
            icon.stop()
            sys.exit(0)
            
        # Initial Battery Status
        battery = psutil.sensors_battery()
        pct = battery.percent if battery else 100
        plugged = battery.power_plugged if battery else False
        
        # Create tray icon
        global tray_icon
        tray_icon = pystray.Icon(
            "Sentinel360",
            create_battery_icon(pct, plugged),
            f"Sentinel360 Agent - Battery: {pct}%"
        )
        
        # Update tray icon thread
        def update_tray():
            while True:
                time.sleep(10)
                bat = psutil.sensors_battery()
                if bat:
                    p = bat.percent
                    pl = bat.power_plugged
                    tray_icon.icon = create_battery_icon(p, pl)
                    tray_icon.title = f"Sentinel360 Agent - Battery: {p}%"
                    
        update_thread = threading.Thread(target=update_tray, daemon=True)
        update_thread.start()
        
        tray_icon.menu = pystray.Menu(
            pystray.MenuItem("Sentinel360 Agent Running", lambda: None, enabled=False),
            pystray.MenuItem(f"Host: {server_url}", lambda: None, enabled=False),
            pystray.MenuItem("Exit", on_exit)
        )
        
        logger.info("Running System Tray icon. Look at your Windows taskbar.")
        tray_icon.run()
    else:
        if use_tray and not TRAY_AVAILABLE:
            logger.warning("Tray libraries not available. Falling back to console mode.")
        # Run report loop in main thread
        report_loop(server_url, api_key, interval)

if __name__ == "__main__":
    main()
