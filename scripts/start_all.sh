#!/bin/bash
# ==============================================================================
# Script Khởi Động Toàn Bộ Hệ Thống: Ryu Controller + Web Dashboard + Mininet
# Cách dùng:
#   chmod +x scripts/start_all.sh
#   sudo ./scripts/start_all.sh
# ==============================================================================

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$SCRIPT_DIR"

echo "========================================================================"
echo " 🚀 ĐANG KHỞI ĐỘNG HỆ THỐNG SDN DATA CONTROLLER TRÊN LINUX SERVER"
echo "========================================================================"

# 1. Dọn dẹp tiến trình cũ và giải phóng port
echo "[1/4] Dọn dẹp trạng thái mạng cũ..."
sudo mn -c > /dev/null 2>&1
sudo fuser -k 6653/tcp 8080/tcp 8000/tcp > /dev/null 2>&1
sleep 1

# 2. Khởi động Ryu SDN Controller
echo "[2/4] Đang khởi động Ryu OpenFlow 1.3 Controller (Cổng 6653)..."
ryu-manager --observe-links controller/ryu_sdn_controller.py ryu.app.ofctl_rest > ryu.log 2>&1 &
RYU_PID=$!
sleep 2

# 3. Khởi động FastAPI Web Dashboard
echo "[3/4] Đang khởi động Web Dashboard & Northbound API (Cổng 8000)..."
python3 run_web.py > web.log 2>&1 &
WEB_PID=$!
sleep 2

SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "------------------------------------------------------------------------"
echo " 🌐 Web Dashboard: http://$SERVER_IP:8000 (hoặc http://localhost:8000)"
echo " 📖 Swagger API:   http://$SERVER_IP:8000/docs"
echo " ⚙️ Ryu REST API:  http://127.0.0.1:8080"
echo "------------------------------------------------------------------------"
echo ""

# 4. Khởi động mạng ảo hóa Mininet
echo "[4/4] Đang khởi động Mạng Ảo Hóa Mininet (3 OVS Switch, 4 Host)..."
echo "      (Gõ 'pingall' để kiểm tra kết nối, hoặc gõ 'exit' để thoát Mininet)"
echo ""
sudo python3 controller/mininet_topology.py

# Dọn dẹp khi Mininet thoát
echo "[*] Đang dừng Ryu Controller và Web Dashboard..."
sudo kill $RYU_PID $WEB_PID > /dev/null 2>&1
sudo mn -c > /dev/null 2>&1
echo "[*] Đã tắt hệ thống an toàn."
