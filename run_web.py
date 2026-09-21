# -*- coding: utf-8 -*-
"""
Khởi động SDN Data Controller & Web Dashboard (Mininet Edition)
Hỗ trợ chạy cục bộ trên Windows hoặc trên Server Cloud (bind 0.0.0.0).
"""

import os
import sys
import webbrowser
import threading
import time
import subprocess
import uvicorn

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
backend_dir = os.path.join(SCRIPT_DIR, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

def ensure_port_free(port=8000):
    try:
        if sys.platform == "win32":
            cmd = f'netstat -ano | findstr :{port}'
            output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
            current_pid = str(os.getpid())
            pids = set()
            for line in output.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                    pid = parts[4]
                    if pid and pid != "0" and pid != current_pid:
                        pids.add(pid)
            for pid in pids:
                print(f"[*] Cổng {port} đang bị chiếm bởi PID {pid}. Đang giải phóng...")
                subprocess.run(f"taskkill /PID {pid} /F", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)
        else:
            subprocess.run(f"fuser -k {port}/tcp", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def open_browser(port=8000):
    time.sleep(1.5)
    url = f"http://localhost:{port}"
    print(f"\n[*] Đang mở Dashboard tại: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    PORT = 8000
    ensure_port_free(PORT)

    print("=" * 68)
    print(" 🚀 KHỞI ĐỘNG SDN CONTROLLER FOR MININET & VIRTUAL NETWORK ".center(68))
    print("=" * 68)
    print(f"[*] Local URL:    http://localhost:{PORT}")
    print(f"[*] Network URL:  http://0.0.0.0:{PORT}")
    print(f"[*] API Docs:     http://localhost:{PORT}/docs")
    print("=" * 68)

    if sys.platform == "win32":
        threading.Thread(target=open_browser, args=(PORT,), daemon=True).start()

    from backend.api_server import app
    # Bind 0.0.0.0 để máy trong mạng Mininet và máy bên ngoài đều truy cập được
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
