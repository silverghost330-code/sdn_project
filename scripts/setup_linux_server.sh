#!/bin/bash
# ==============================================================================
# Script Cài Đặt Tự Động Môi Trường SDN Mininet & Ryu Trên Linux Server
# Chạy trên Ubuntu / Debian:
#   chmod +x scripts/setup_linux_server.sh
#   ./scripts/setup_linux_server.sh
# ==============================================================================

set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$SCRIPT_DIR"

echo "========================================================================"
echo " 🚀 BẮT ĐẦU CÀI ĐẶT SDN MININET CONTROLLER SERVER (UBUNTU / DEBIAN)"
echo "========================================================================"

# 1. Cập nhật gói hệ thống và cài Mininet, OVS, các công cụ mạng
echo "[*] Đang cài đặt Mininet, Open vSwitch, net-tools..."
sudo apt-get update -y
sudo apt-get install -y mininet openvswitch-switch python3 python3-pip python3-venv net-tools curl git iperf tcpdump

# 2. Khởi động dịch vụ Open vSwitch daemon
echo "[*] Khởi động dịch vụ Open vSwitch daemon..."
sudo service openvswitch-switch start || sudo systemctl start openvswitch-switch || true
sudo ovs-vsctl show || true

# 3. Chuẩn bị Python runtime tương thích cho Ryu Controller
# Ryu yêu cầu Python 3.8 - 3.10 để hoạt động ổn định nhất với eventlet/greenlet
SYS_PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[*] Python mặc định của hệ thống: $SYS_PY_VER"

if [ -f "$SCRIPT_DIR/.python310/bin/python3.10" ]; then
    echo "[*] Đã tìm thấy Python 3.10 tại .python310"
    PY_CMD="$SCRIPT_DIR/.python310/bin/python3.10"
else
    echo "[*] Tải và thiết lập Python 3.10 runtime độc lập cho Ryu..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    uv python install 3.10
    cp -r "$HOME/.local/share/uv/python/cpython-3.10"* "$SCRIPT_DIR/.python310" 2>/dev/null || true
    PY_CMD="$SCRIPT_DIR/.python310/bin/python3.10"
fi

# 4. Tạo virtual environment và cài đặt thư viện
echo "[*] Thiết lập Virtual Environment (Python 3.10)..."
rm -rf "$SCRIPT_DIR/venv"
if command -v uv &> /dev/null; then
    uv venv "$SCRIPT_DIR/venv" --python "$PY_CMD"
else
    "$PY_CMD" -m venv "$SCRIPT_DIR/venv"
fi

# Đảm bảo symlink trỏ chuẩn xác
ln -sf "$PY_CMD" "$SCRIPT_DIR/venv/bin/python"

# 5. Cài đặt các thư viện cần thiết
echo "[*] Đang cài đặt các thư viện Python (FastAPI, Uvicorn, Ryu, Requests, Eventlet)..."
"$SCRIPT_DIR/venv/bin/python" -m pip install --upgrade pip "setuptools==67.6.1" wheel pbr six
"$SCRIPT_DIR/venv/bin/python" -m pip install --no-build-isolation ryu tinyrpc fastapi uvicorn requests pydantic "eventlet<=0.33.3"

# 6. Tự động Patch lỗi ALREADY_HANDLED trong ryu/app/wsgi.py
"$SCRIPT_DIR/venv/bin/python" -c "
import glob, os
for wsgi_path in glob.glob('$SCRIPT_DIR/venv/lib/python*/site-packages/ryu/app/wsgi.py'):
    with open(wsgi_path, 'r') as f:
        content = f.read()
    if 'from eventlet.wsgi import ALREADY_HANDLED' in content and 'try:' not in content:
        content = content.replace(
            '    from eventlet.wsgi import ALREADY_HANDLED\n    _ALREADY_HANDLED = ALREADY_HANDLED',
            '    try:\n        from eventlet.wsgi import ALREADY_HANDLED\n    except (ImportError, AttributeError):\n        ALREADY_HANDLED = [b\'\']\n    _ALREADY_HANDLED = ALREADY_HANDLED'
        )
        with open(wsgi_path, 'w') as f:
            f.write(content)
        print('[+] Đã patch thành công:', wsgi_path)
" 2>/dev/null || true

# 7. Tạo liên kết hệ thống cho ryu-manager
sudo ln -sf "$SCRIPT_DIR/venv/bin/ryu-manager" /usr/local/bin/ryu-manager
sudo ln -sf "$SCRIPT_DIR/venv/bin/ryu" /usr/local/bin/ryu

echo ""
echo "========================================================================"
echo " ✅ CÀI ĐẶT HOÀN TẤT! SẴN SÀNG KHỞI CHẠY HỆ THỐNG SDN"
echo " Để khởi động toàn bộ hệ thống, hãy chạy: sudo ./scripts/start_all.sh"
echo "========================================================================"
