#!/bin/bash
# ==============================================================================
# Script Cài Đặt Tự Động Môi Trường SDN Mininet & Ryu Trên Linux Server
# Chạy trên Ubuntu / Debian:
#   chmod +x setup_linux_server.sh
#   ./setup_linux_server.sh
# ==============================================================================

echo "========================================================================"
echo " 🚀 BẮT ĐẦU CÀI ĐẶT SDN MININET CONTROLLER SERVER (UBUNTU / DEBIAN)"
echo "========================================================================"

# 1. Cập nhật gói hệ thống
sudo apt update

# 2. Cài đặt Mininet, Open vSwitch và các công cụ mạng
echo "[*] Đang cài đặt Mininet, Open vSwitch, iperf, net-tools..."
sudo apt install -y mininet openvswitch-switch python3 python3-pip python3-setuptools net-tools curl git iperf tcpdump

# 3. Khởi động dịch vụ Open vSwitch
echo "[*] Khởi động dịch vụ Open vSwitch daemon..."
sudo service openvswitch-switch start || sudo systemctl start openvswitch-switch
sudo ovs-vsctl show

# 4. Cài đặt các thư viện Python cho Controller & Web Dashboard
echo "[*] Đang cài đặt thư viện Python (FastAPI, Uvicorn, Ryu, Requests)..."
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$SCRIPT_DIR"

# Tạo môi trường ảo với system packages
python3 -m venv --system-site-packages "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install "setuptools==67.6.1"
"$SCRIPT_DIR/venv/bin/pip" install --no-build-isolation ryu tinyrpc fastapi uvicorn requests pydantic

# Patch ALREADY_HANDLED nếu cần trên eventlet mới
python3 -c "
import os
wsgi_path = '$SCRIPT_DIR/venv/lib/python3.13/site-packages/ryu/app/wsgi.py'
if os.path.exists(wsgi_path):
    with open(wsgi_path, 'r') as f:
        content = f.read()
    if 'from eventlet.wsgi import ALREADY_HANDLED' in content and 'try:' not in content:
        content = content.replace(
            '    from eventlet.wsgi import ALREADY_HANDLED\n    _ALREADY_HANDLED = ALREADY_HANDLED',
            '    try:\n        from eventlet.wsgi import ALREADY_HANDLED\n    except (ImportError, AttributeError):\n        ALREADY_HANDLED = [b\'\']\n    _ALREADY_HANDLED = ALREADY_HANDLED'
        )
        with open(wsgi_path, 'w') as f:
            f.write(content)
" 2>/dev/null || true

# Tạo liên kết hệ thống cho ryu-manager
sudo ln -sf "$SCRIPT_DIR/venv/bin/ryu-manager" /usr/local/bin/ryu-manager
sudo ln -sf "$SCRIPT_DIR/venv/bin/ryu" /usr/local/bin/ryu

echo ""
echo "========================================================================"
echo " CÀI ĐẶT HOÀN TẤT! SẴN SÀNG KHỞI CHẠY HỆ THỐNG SDN"
echo " Để khởi động toàn bộ hệ thống, hãy chạy: sudo ./scripts/start_all.sh"
echo "========================================================================"
