#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script Demo Đồ Án SDN Data Controller (OpenFlow 1.3 + LLDP Topology + Host Discovery)
Hỗ trợ trình diễn trực quan trên Terminal cho giảng viên chấm đồ án.
Cách chạy:
    python3 demo_do_an.py          (Chạy menu tương tác)
    python3 demo_do_an.py --all    (Chạy tự động lần lượt tất cả chức năng)
"""

import os
import sys
import time
import json
import subprocess
import urllib.request

RYU_URL = "http://127.0.0.1:8080"
API_URL = "http://127.0.0.1:8000"


def http_get_json(url: str, timeout: float = 2.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_hex_or_int(val) -> int:
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if s.isdigit() and not s.startswith("0000"):
        return int(s)
    return int(s, 16)


def trigger_host_pings():
    """Kích hoạt các host gửi gói tin qua cổng biên để Ryu học danh sách Host thực tế"""
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
        host_pids = {}
        for line in out.splitlines():
            for h in ("h1", "h2", "h3", "h4"):
                if f"mininet:{h}" in line and "ps -eo" not in line:
                    parts = line.strip().split()
                    if parts and parts[0].isdigit():
                        host_pids[h] = parts[0]
        targets = {"h1": "10.0.0.3", "h2": "10.0.0.4", "h3": "10.0.0.1", "h4": "10.0.0.2"}
        for h, pid in host_pids.items():
            subprocess.run(
                ["sudo", "mnexec", "-a", pid, "ping", "-c", "1", "-W", "1", targets[h]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3
            )
    except Exception:
        pass


def demo_1_lldp_topology():
    print("\n" + "=" * 76)
    print(" [CHỨC NĂNG 1] PHÁT HIỆN TOPOLOGY MẠNG TỰ ĐỘNG BẰNG GIAO THỨC LLDP")
    print("=" * 76)
    switches = http_get_json(f"{RYU_URL}/v1.0/topology/switches")
    links = http_get_json(f"{RYU_URL}/v1.0/topology/links")

    print(f"[+] Số lượng OpenFlow Switch được Ryu phát hiện ({len(switches)} Switch):")
    for sw in switches:
        dpid_num = parse_hex_or_int(sw.get("dpid", "0"))
        ports = [p.get("name", f"port-{p.get('port_no')}") for p in sw.get("ports", [])]
        print(f"    - Switch s{dpid_num} (DPID: {sw.get('dpid')}) | Cổng: {', '.join(ports)}")

    print(f"\n[+] Các liên kết vật lý phát hiện bởi giao thức LLDP ({len(links)} chiều liên kết):")
    for lk in links:
        src_dpid = parse_hex_or_int(lk["src"]["dpid"])
        src_port = parse_hex_or_int(lk["src"]["port_no"])
        dst_dpid = parse_hex_or_int(lk["dst"]["dpid"])
        dst_port = parse_hex_or_int(lk["dst"]["port_no"])
        print(f"    Switch s{src_dpid} (Port {src_port}) <===[LLDP]===> Switch s{dst_dpid} (Port {dst_port})")


def demo_2_switches_and_hosts():
    print("\n" + "=" * 76)
    print(" [CHỨC NĂNG 2] THU THẬP THÔNG TIN PHẦN CỨNG SWITCH VÀ HOST ĐỘNG")
    print("=" * 76)
    trigger_host_pings()
    time.sleep(0.5)

    print("[+] Thông tin phần cứng Open vSwitch (từ /stats/desc/<dpid>):")
    for dpid in (1, 2, 3):
        try:
            desc_data = http_get_json(f"{RYU_URL}/stats/desc/{dpid}").get(str(dpid), {})
            print(
                f"    - Switch s{dpid}: Nhà SX={desc_data.get('mfr_desc', 'Nicira/OVS')} | "
                f"Phần cứng={desc_data.get('hw_desc', 'Open vSwitch')} | "
                f"Phiên bản={desc_data.get('sw_desc', 'OVS')}"
            )
        except Exception as ex:
            print(f"    - Switch s{dpid}: OFFLINE ({ex})")

    hosts = http_get_json(f"{RYU_URL}/v1.0/topology/hosts")
    print(f"\n[+] Danh sách Host thực tế Ryu phát hiện trên cổng biên ({len(hosts)} Host):")
    for h in sorted(hosts, key=lambda x: x.get("mac", "")):
        mac = h.get("mac", "N/A")
        ipv4_list = h.get("ipv4", [])
        ip_str = ipv4_list[0] if ipv4_list else "Đang học ARP/IP"
        port_info = h.get("port", {})
        sw_dpid = parse_hex_or_int(port_info.get("dpid", 0))
        port_no = parse_hex_or_int(port_info.get("port_no", 0))
        print(f"    - Host MAC: {mac} | IPv4: {ip_str:<12} ---> Gắn tại Switch s{sw_dpid} (Port {port_no})")


def main():
    if "--all" in sys.argv:
        demo_1_lldp_topology()
        demo_2_switches_and_hosts()
        return

    while True:
        print("\n" + "=" * 68)
        print(" 🎓 MENU DEMO ĐỒ ÁN SDN DATA CONTROLLER (OPENFLOW 1.3 + LLDP)")
        print("=" * 68)
        print("  1. Chức năng 1: Phát hiện Topology mạng tự động qua LLDP")
        print("  2. Chức năng 2: Thu thập thông tin Switch và Host thực tế")
        print("  0. Thoát")
        choice = input("\nChọn chức năng (0-2): ").strip()
        if choice == "1":
            demo_1_lldp_topology()
        elif choice == "2":
            demo_2_switches_and_hosts()
        elif choice == "0":
            break


if __name__ == "__main__":
    main()

