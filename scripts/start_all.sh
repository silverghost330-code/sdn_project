#!/bin/bash
# ==============================================================================
# Script Khởi Động Toàn Bộ Hệ Thống: Ryu Controller + Web Dashboard + Mininet
# Cách dùng:
#   chmod +x scripts/start_all.sh
#   sudo ./scripts/start_all.sh
# ==============================================================================

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$SCRIPT_DIR"

PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
RYU_BIN="$SCRIPT_DIR/venv/bin/ryu-manager"

if [ ! -f "$RYU_BIN" ]; then
    echo "[-] Không tìm thấy Ryu trong $RYU_BIN!"
    echo "[-] Vui lòng kiểm tra lại môi trường venv trước khi khởi động."
    exit 1
fi

echo "========================================================================"
echo " 🚀 ĐANG KHỞI ĐỘNG HỆ THỐNG SDN DATA CONTROLLER TRÊN LINUX SERVER"
echo "========================================================================"

# Hàm dọn dẹp khi thoát
cleanup() {
    echo ""
    echo "[*] Đang dừng Ryu Controller và Web Dashboard..."
    if [ -n "$RYU_PID" ]; then
        kill "$RYU_PID" > /dev/null 2>&1
    fi
    if [ -n "$WEB_PID" ]; then
        kill "$WEB_PID" > /dev/null 2>&1
    fi
    sudo fuser -k 6653/tcp 8080/tcp 8000/tcp > /dev/null 2>&1
    sudo mn -c > /dev/null 2>&1
    echo "[*] Đã tắt hệ thống an toàn."
}
trap cleanup EXIT INT TERM

# 1. Dọn dẹp tiến trình cũ và giải phóng port
echo "[1/4] Dọn dẹp trạng thái mạng cũ..."
sudo mn -c > /dev/null 2>&1
sudo fuser -k 6653/tcp 8080/tcp 8000/tcp > /dev/null 2>&1
sudo rm -f "$SCRIPT_DIR/ryu.log" "$SCRIPT_DIR/web.log" > /dev/null 2>&1
sleep 1

# 2. Khởi động Ryu SDN Controller
echo "[2/4] Đang khởi động Ryu OpenFlow 1.3 Controller (Cổng 6653 & 8080)..."
"$RYU_BIN" --observe-links controller/ryu_sdn_controller.py ryu.app.ofctl_rest > ryu.log 2>&1 &
RYU_PID=$!
sleep 2

# 3. Khởi động FastAPI Web Dashboard
echo "[3/4] Đang khởi động Web Dashboard & Northbound API (Cổng 8000)..."
"$PYTHON_BIN" run_web.py > web.log 2>&1 &
WEB_PID=$!
sleep 2

SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "------------------------------------------------------------------------"
echo " 🌐 Web Dashboard: http://${SERVER_IP:-localhost}:8000 (hoặc http://localhost:8000)"
echo " 📖 Swagger API:   http://${SERVER_IP:-localhost}:8000/docs"
echo " ⚙️ Ryu REST API:  http://127.0.0.1:8080"
echo "------------------------------------------------------------------------"
echo ""

# 4. Khởi động mạng ảo hóa Mininet
echo "[4/4] Đang khởi động Mạng Ảo Hóa Mininet (3 OVS Switch, 4 Host)..."
echo "      (Gõ 'pingall' để kiểm tra kết nối, hoặc gõ 'exit' để thoát Mininet)"
echo ""
sudo /usr/bin/python3 controller/mininet_topology.py
