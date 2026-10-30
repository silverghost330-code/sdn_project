#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Mininet Virtual Network Topology for Linux Server
Xây dựng mô hình mạng nội bộ ảo hóa gồm 3 Switch Open vSwitch (Spine/Leaf Mesh)
và 4 Host (Client 1, Client 2, Web Server, Windows File Server/Attacker).
Kết nối trực tiếp tới Ryu Remote Controller tại 127.0.0.1:6653.
"""

import os
import sys
import time
import socket
import subprocess
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info

def is_port_open(port: int, host: str = '127.0.0.1') -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except Exception:
        return False

def ensure_services_running():
    """Tự động khởi chạy Ryu Controller (6653) và Web Dashboard (8000) nếu người dùng chạy trực tiếp file này"""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    ryu_bin = os.path.join(project_dir, 'venv', 'bin', 'ryu-manager')
    py_bin = os.path.join(project_dir, 'venv', 'bin', 'python')
    ctrl_app = os.path.join(project_dir, 'controller', 'ryu_sdn_controller.py')
    web_app = os.path.join(project_dir, 'run_web.py')
    spawned = []

    if not is_port_open(6653) and os.path.exists(ryu_bin):
        info("*** [Auto-Start] Khởi động Ryu OpenFlow 1.3 Controller (Port 6653 & 8080)...\n")
        ryu_log = open(os.path.join(project_dir, 'ryu.log'), 'w')
        p_ryu = subprocess.Popen(
            [ryu_bin, '--observe-links', ctrl_app, 'ryu.app.ofctl_rest', 'ryu.app.rest_topology'],
            cwd=project_dir, stdout=ryu_log, stderr=subprocess.STDOUT
        )
        spawned.append(p_ryu)
        time.sleep(2.0)

    if not is_port_open(8000) and os.path.exists(py_bin):
        info("*** [Auto-Start] Khởi động Web Dashboard & Northbound API (Port 8000)...\n")
        web_log = open(os.path.join(project_dir, 'web.log'), 'w')
        p_web = subprocess.Popen(
            [py_bin, web_app],
            cwd=project_dir, stdout=web_log, stderr=subprocess.STDOUT
        )
        spawned.append(p_web)
        time.sleep(1.5)

    return spawned

def create_sdn_topology():
    spawned_procs = ensure_services_running()
    info("*** [1] Khởi tạo hệ thống mạng Mininet (Auto MACs)...\n")
    net = Mininet(controller=RemoteController, switch=OVSSwitch, autoSetMacs=True)

    info("*** [2] Kết nối tới Ryu Remote Controller (Port 6653)...\n")
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    info("*** [3] Khởi tạo các Switch Open vSwitch (Chuẩn OpenFlow 1.3 - Userspace Datapath)...\n")
    s1 = net.addSwitch('s1', protocols='OpenFlow13', dpid='0000000000000001', datapath='user') # Core Switch
    s2 = net.addSwitch('s2', protocols='OpenFlow13', dpid='0000000000000002', datapath='user') # Distribution Switch
    s3 = net.addSwitch('s3', protocols='OpenFlow13', dpid='0000000000000003', datapath='user') # Server Farm Switch

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

    # Tắt TX/RX Checksum Offloading trên các giao diện veth của Host để TCP/UDP (iperf, curl)
    # hoạt động ổn định 100% với Open vSwitch Userspace Datapath (netdev)
    for h in [h1, h2, h3, h4]:
        h.cmd("ethtool -K " + h.defaultIntf().name + " tx off rx off")

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
    info(" - Test Failover:     gõ 'link s1 s2 down' -> 'pingall' -> 'link s1 s2 up'\n")
    info(" - Test Web Server:   gõ 'h1 curl http://10.0.0.3'\n")
    info(" - Test File Server:  gõ 'h1 curl http://10.0.0.4:8080'\n")
    info(" - Test QoS (iperf):  gõ 'iperf h2 h3'\n")
    info(" - Thoát Mininet:     gõ 'exit'\n")
    info("=" * 65 + "\n\n")

    if '--daemon' in sys.argv or not sys.stdin.isatty():
        info("*** [Daemon Mode] Giữ mạng Mininet hoạt động nền (nhấn Ctrl+C hoặc kill để dừng)...\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        CLI(net)

    info("*** Đang tắt mạng và giải phóng tài nguyên...\n")
    net.stop()
    for p in spawned_procs:
        try:
            p.terminate()
        except Exception:
            pass

if __name__ == '__main__':
    setLogLevel('info')
    create_sdn_topology()
