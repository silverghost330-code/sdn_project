#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Mininet Virtual Network Topology for Linux Server
Xây dựng mô hình mạng nội bộ ảo hóa gồm 3 Switch Open vSwitch (Spine/Leaf Mesh)
và 4 Host (Client 1, Client 2, Web Server, Windows File Server/Attacker).
Kết nối trực tiếp tới Ryu Remote Controller tại 127.0.0.1:6653.
"""

import sys
import time
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info

def create_sdn_topology():
    info("*** [1] Khởi tạo hệ thống mạng Mininet (Auto MACs)...\n")
    net = Mininet(controller=RemoteController, switch=OVSSwitch, autoSetMacs=True)

    info("*** [2] Kết nối tới Ryu Remote Controller (Port 6653)...\n")
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    info("*** [3] Khởi tạo các Switch Open vSwitch (Chuẩn OpenFlow 1.3)...\n")
    s1 = net.addSwitch('s1', protocols='OpenFlow13', dpid='0000000000000001') # Core Switch
    s2 = net.addSwitch('s2', protocols='OpenFlow13', dpid='0000000000000002') # Distribution Switch
    s3 = net.addSwitch('s3', protocols='OpenFlow13', dpid='0000000000000003') # Server Farm Switch

    info("*** [4] Khởi tạo các Host ảo hóa...\n")
    # Host h1: Máy Client 1
    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    # Host h2: Máy Client 2
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    # Host h3: Web Server nội bộ (chạy HTTP port 80)
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
    # Host h4: Windows File Server / Attacker Host (chạy dịch vụ File Sharing port 445 / 8080)
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

    info("*** [5] Thiết lập các đường truyền liên kết (Virtual Links)...\n")
    # Liên kết Host - Switch (Access Links)
    net.addLink(h1, s1) # h1-eth0 <-> s1-eth1
    net.addLink(h2, s2) # h2-eth0 <-> s2-eth1
    net.addLink(h3, s3) # h3-eth0 <-> s3-eth1
    net.addLink(h4, s3) # h4-eth0 <-> s3-eth2

    # Liên kết giữa các Switch tạo vòng Trunk Mesh chống nghẽn
    net.addLink(s1, s2) # s1-eth2 <-> s2-eth2
    net.addLink(s1, s3) # s1-eth3 <-> s3-eth3
    net.addLink(s2, s3) # s2-eth3 <-> s3-eth4

    info("*** [6] Khởi động mạng ảo hóa Mininet...\n")
    net.start()

    info("*** [7] Khởi động các dịch vụ Server tự động...\n")
    # Khởi động Web Server HTTP trên h3
    h3.cmd('python3 -m http.server 80 > /dev/null 2>&1 &')
    info("    [+] Web Server đã chạy trên h3 (http://10.0.0.3:80)\n")

    # Khởi động dịch vụ Giả Lập File Server trên h4 (cổng 8080 và cổng 445)
    h4.cmd('python3 -m http.server 8080 > /dev/null 2>&1 &')
    info("    [+] Windows File Server đã sẵn sàng trên h4 (10.0.0.4:8080 & SMB)\n")

    info("\n" + "=" * 65 + "\n")
    info(" 🚀 MẠNG ẢO HÓA MININET ĐÃ SẴN SÀNG ĐIỀU KHIỂN BỞI RYU SDN!\n")
    info(" - Kiểm tra toàn mạng: gõ 'pingall'\n")
    info(" - Test Web Server:   gõ 'h1 curl http://10.0.0.3'\n")
    info(" - Test File Server:  gõ 'h1 curl http://10.0.0.4:8080'\n")
    info(" - Thoát Mininet:     gõ 'exit'\n")
    info("=" * 65 + "\n\n")

    CLI(net)

    info("*** Đang tắt mạng và giải phóng tài nguyên...\n")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    create_sdn_topology()
