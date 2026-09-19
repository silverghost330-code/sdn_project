#!/bin/bash
# ==============================================================================
# Script tự động cấu hình Open vSwitch Node trong PNETLab
# Cách dùng trên console của Switch OVS trong PNETLab:
#   chmod +x setup_ovs_node.sh
#   ./setup_ovs_node.sh <CONTROLLER_IP> <BRIDGE_NAME> <DATAPATH_ID>
# Ví dụ:
#   ./setup_ovs_node.sh 192.168.1.100 br0 0000000000000001
# ==============================================================================

CONTROLLER_IP=${1:-"192.168.1.100"}
CONTROLLER_PORT=${2:-"6653"}
BRIDGE_NAME=${3:-"br0"}
DPID=${4:-"0000000000000001"}

echo "========================================================"
echo " 🌐 CẤU HÌNH OPEN VSWITCH TRONG PNETLAB -> RYU CONTROLLER"
echo "========================================================"
echo "Controller IP:   $CONTROLLER_IP:$CONTROLLER_PORT"
echo "Bridge Name:     $BRIDGE_NAME"
echo "Datapath ID:     $DPID"
echo "========================================================"

# 1. Khởi động OVS Service nếu chưa bật
service openvswitch-switch start 2>/dev/null || /etc/init.d/openvswitch-switch start 2>/dev/null

# 2. Xóa bridge cũ nếu có để tránh xung đột
ovs-vsctl --if-exists del-br $BRIDGE_NAME

# 3. Tạo Bridge mới
ovs-vsctl add-br $BRIDGE_NAME

# 4. Gán Datapath ID cố định để Ryu Controller nhận dạng chính xác
ovs-vsctl set bridge $BRIDGE_NAME other-config:datapath-id=$DPID

# 5. Cấu hình giao thức OpenFlow 1.3
ovs-vsctl set bridge $BRIDGE_NAME protocols=OpenFlow13

# 6. Thêm các cổng mạng vật lý ảo (eth1, eth2, eth3...) vào bridge
for iface in eth1 eth2 eth3 eth4; do
    if ip link show $iface > /dev/null 2>&1; then
        echo "[+] Đang thêm cổng $iface vào bridge $BRIDGE_NAME..."
        ovs-vsctl --may-exist add-port $BRIDGE_NAME $iface
        ip link set $iface up
    fi
done

# Bật bridge
ip link set $BRIDGE_NAME up

# 7. Trỏ Bridge tới Ryu SDN Controller
echo "[*] Đang kết nối tới Ryu SDN Controller tại tcp:$CONTROLLER_IP:$CONTROLLER_PORT..."
ovs-vsctl set-controller $BRIDGE_NAME tcp:$CONTROLLER_IP:$CONTROLLER_PORT

# 8. Cấu hình chế độ Fail-Secure (Chặn mọi traffic nếu chưa có rule từ Controller)
ovs-vsctl set-fail-mode $BRIDGE_NAME secure

echo ""
echo " Kiểm tra trạng thái kết nối OVS:"
ovs-vsctl show
echo ""
echo " Trạng thái Controller:"
ovs-vsctl get-controller $BRIDGE_NAME
echo " Hoàn tất cấu hình OVS cho PNETLab!"
