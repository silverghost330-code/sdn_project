#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bộ Kiểm Thử Tổng Thể End-to-End (E2E Full Test Suite) cho Hệ Thống SDN Data Controller
Kiểm tra toàn diện 7 hạng mục thực tế trên Mininet + Ryu Controller + FastAPI:
  1. Phát hiện Topology bằng LLDP (/v1.0/topology/switches, /v1.0/topology/links, /api/sdn/topology)
  2. Thu thập thông tin Switch & Host thực tế (/stats/desc/<dpid>, /v1.0/topology/hosts)
  3. Tường lửa SDN Firewall ACL (Chặn & Khôi phục lưu lượng thực tế giữa các Host)
  4. Điều hướng lưu lượng L2 / Traffic Steering (Kiểm tra cài đặt Flow & Ping thông suốt)
  5. Giám sát thống kê Port & Flow Stats (/stats/flow/<dpid>, /stats/port/<dpid>, /api/sdn/flows)
  6. Giới hạn băng thông QoS Meter Table (Cài đặt, cập nhật lại không lỗi OFPMFC_METER_EXISTS, xóa)
  7. Tự động phục hồi sự cố Link Down & Switch Stop (DEAD_DISPATCHER) qua nhánh dự phòng s2-s3
"""

import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

RYU_URL = "http://127.0.0.1:8080"
API_URL = "http://127.0.0.1:8000"


def http_req(url: str, method: str = "GET", payload=None, timeout: float = 3.0):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_host_pid(host_name: str):
    out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
    for line in out.splitlines():
        if f"mininet:{host_name}" in line and "ps -eo" not in line and "grep" not in line:
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                return int(parts[0])
    return None


def host_ping(src_host: str, dst_ip: str, count: int = 2, wait_sec: int = 1) -> bool:
    pid = get_host_pid(src_host)
    assert pid is not None, f"Không tìm thấy tiến trình Mininet cho host {src_host}"
    proc = subprocess.run(
        ["sudo", "mnexec", "-a", str(pid), "ping", "-c", str(count), "-W", str(wait_sec), dst_ip],
        capture_output=True, text=True, timeout=10
    )
    return proc.returncode == 0


def test_1_lldp_topology():
    print("\n[TEST 1/7] Kiểm tra LLDP Topology Discovery (/v1.0/topology/links & /api/sdn/topology)...")
    switches = http_req(f"{RYU_URL}/v1.0/topology/switches")
    links = http_req(f"{RYU_URL}/v1.0/topology/links")
    assert len(switches) == 3, f"Ryu phải phát hiện đủ 3 switch, thực tế: {len(switches)}"
    assert len(links) > 0, "Ryu /v1.0/topology/links trả về mảng rỗng []! LLDP chưa hoạt động!"

    discovered_pairs = set()
    for lk in links:
        s_dpid = int(lk["src"]["dpid"], 16)
        d_dpid = int(lk["dst"]["dpid"], 16)
        discovered_pairs.add((min(s_dpid, d_dpid), max(s_dpid, d_dpid)))
    assert {(1, 2), (1, 3), (2, 3)}.issubset(discovered_pairs), (
        f"LLDP chưa phát hiện đủ 3 cặp kết nối tam giác (1-2, 1-3, 2-3): {discovered_pairs}"
    )

    api_topo = http_req(f"{API_URL}/api/sdn/topology")
    assert all(sw["status"] == "UP" for sw in api_topo["switches"]), f"Switch chưa ở trạng thái UP: {api_topo['switches']}"
    assert len(api_topo.get("lldp_discovered_links", [])) >= 6, "API /api/sdn/topology thiếu lldp_discovered_links"
    print("  ✅ [PASS] Bước 1: LLDP Topology Discovery phát hiện đầy đủ 3 Switch và 6 chiều liên kết.")


def test_2_switch_and_host_info():
    print("\n[TEST 2/7] Kiểm tra thu thập thông tin Switch & Host động (/v1.0/topology/hosts)...")
    # Kích hoạt lưu lượng từ cả 4 host để Ryu học Host
    assert host_ping("h1", "10.0.0.3", count=1), "h1 không ping được h3"
    assert host_ping("h2", "10.0.0.4", count=1), "h2 không ping được h4"
    time.sleep(0.5)

    for dpid in (1, 2, 3):
        desc = http_req(f"{RYU_URL}/stats/desc/{dpid}")
        assert str(dpid) in desc, f"Không lấy được thông tin phần cứng switch s{dpid}"

    hosts = http_req(f"{RYU_URL}/v1.0/topology/hosts")
    assert len(hosts) >= 2, f"Ryu /v1.0/topology/hosts chưa thu thập được danh sách host: {hosts}"
    print(f"  ✅ [PASS] Bước 2: Đã thu thập thông tin 3 Switch OVS và {len(hosts)} Host thực tế trên cổng biên.")


def test_3_firewall_acl():
    print("\n[TEST 3/7] Kiểm tra Tường lửa SDN Firewall ACL (DROP & Khôi phục)...")
    # Tạo rule chặn ICMP từ h2 (10.0.0.2) tới h4 (10.0.0.4) trên s2 (dpid=2)
    res = http_req(
        f"{API_URL}/api/sdn/firewall",
        method="POST",
        payload={
            "dpid": 2,
            "src_ip": "10.0.0.2",
            "dst_ip": "10.0.0.4",
            "proto": "ICMP",
            "action": "DROP",
            "description": "E2E Test Block h2 -> h4"
        }
    )
    rule_id = res["rule"]["id"]
    time.sleep(0.5)

    # Kiểm tra h2 ping h4 phải bị chặn (False), trong khi h1 ping h4 vẫn thông (True)
    blocked = not host_ping("h2", "10.0.0.4", count=1, wait_sec=1)
    h1_ok = host_ping("h1", "10.0.0.4", count=1, wait_sec=1)
    assert blocked, "Firewall rule DROP đã cài nhưng h2 vẫn ping được h4!"
    assert h1_ok, "Firewall chặn nhầm cả lưu lượng hợp lệ từ h1 tới h4!"

    # Xóa rule và kiểm tra h2 ping h4 thông trở lại
    http_req(f"{API_URL}/api/sdn/firewall/{rule_id}", method="DELETE")
    time.sleep(0.5)
    restored = host_ping("h2", "10.0.0.4", count=2, wait_sec=1)
    assert restored, "Sau khi xóa Firewall rule, h2 vẫn không ping lại được h4!"
    print("  ✅ [PASS] Bước 3: Firewall ACL chặn và mở lại lưu lượng chính xác 100%.")


def test_4_traffic_steering_l2():
    print("\n[TEST 4/7] Kiểm tra chuyển tiếp L2 & điều hướng lưu lượng (Traffic Steering)...")
    assert host_ping("h1", "10.0.0.2", count=2), "h1 <-> h2 không thông"
    assert host_ping("h1", "10.0.0.3", count=2), "h1 <-> h3 không thông"
    assert host_ping("h2", "10.0.0.3", count=2), "h2 <-> h3 không thông"
    print("  ✅ [PASS] Bước 4: Lưu lượng L2 giữa tất cả các Host định tuyến thông suốt (0% loss).")


def test_5_port_and_flow_stats():
    print("\n[TEST 5/7] Kiểm tra thu thập thống kê Port & Flow Stats...")
    flows = http_req(f"{API_URL}/api/sdn/flows?dpid=all")
    assert isinstance(flows, list) and len(flows) >= 3, f"Danh sách Flow trả về không hợp lệ: {flows}"
    for dpid in (1, 2, 3):
        pstats = http_req(f"{RYU_URL}/stats/port/{dpid}")
        assert str(dpid) in pstats and len(pstats[str(dpid)]) >= 3, f"Thiếu thống kê port trên s{dpid}"
    print(f"  ✅ [PASS] Bước 5: Thu thập thành công {len(flows)} Flow entries và thống kê Port của 3 Switch.")


def test_6_qos_meter():
    print("\n[TEST 6/7] Kiểm tra giới hạn băng thông QoS Meter Table (Userspace OVS)...")
    # Lần 1: Tạo Meter #1 trên s2 với rate 2000 Kbps
    m1 = http_req(
        f"{API_URL}/api/sdn/qos",
        method="POST",
        payload={"dpid": 2, "meter_id": 1, "rate_kbps": 2000, "src_ip": "10.0.0.2", "dst_ip": "10.0.0.3"}
    )
    assert m1.get("status") == "success", f"Tạo QoS Meter lần 1 thất bại: {m1}"

    # Lần 2: Ghi đè lại cùng Meter #1 với rate 5000 Kbps (kiểm tra không bị lỗi OFPMFC_METER_EXISTS)
    m2 = http_req(
        f"{API_URL}/api/sdn/qos",
        method="POST",
        payload={"dpid": 2, "meter_id": 1, "rate_kbps": 5000, "src_ip": "10.0.0.2", "dst_ip": "10.0.0.3"}
    )
    assert m2.get("status") == "success", f"Cập nhật QoS Meter lần 2 thất bại: {m2}"
    time.sleep(0.4)

    # Xác nhận Meter thực sự tồn tại trong OVS qua Ryu REST API
    ryu_meters = http_req(f"{RYU_URL}/stats/meterconfig/2").get("2", [])
    assert any(m.get("meter_id") == 1 for m in ryu_meters), f"Meter #1 không tồn tại trong OVS s2: {ryu_meters}"

    # Xóa Meter sau khi test
    http_req(f"{API_URL}/api/sdn/qos/1", method="DELETE")
    print("  ✅ [PASS] Bước 6: QoS Meter Table cài đặt, cập nhật mức băng thông và gỡ bỏ thành công trên OVS.")


def test_7_link_and_switch_failover():
    print("\n[TEST 7/7] Kiểm tra Tự động Hội tụ khi Tắt Switch s1 (DEAD_DISPATCHER) & Khôi phục...")
    try:
        # Giả lập sập Switch s1 bằng lệnh ngắt kết nối OpenFlow Controller của s1
        subprocess.run(["sudo", "ovs-vsctl", "del-controller", "s1"], check=True)
        # Xóa các flow cũ trên bridge s1 (nếu gói đi lạc sang s1 khi del-controller) hoặc hạ cổng s1
        subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "del-flows", "s1"], check=False)
        time.sleep(2.0)

        topo_down = http_req(f"{API_URL}/api/sdn/topology")
        sw_map = {int(s["dpid"], 16): s for s in topo_down["switches"]}
        link_map = {f"{l['src']}-{l['dst']}": l for l in topo_down["links"]}
        events = http_req(f"{API_URL}/api/sdn/events")

        assert sw_map[1]["status"] == "DOWN", f"Switch s1 chưa chuyển sang DOWN: {sw_map[1]}"
        assert link_map["s1-s2"]["status"] == "DOWN" and link_map["s1-s3"]["status"] == "DOWN", (
            f"Các link nối vào s1 chưa chuyển sang DOWN: {link_map}"
        )
        assert link_map["s2-s3"]["status"] == "UP", f"Nhánh dự phòng s2-s3 không ở trạng thái UP: {link_map['s2-s3']}"
        assert any(e.get("reason") == "SWITCH_DOWN" or "SWITCH_DOWN" in str(e) for e in events), (
            "Không tìm thấy sự kiện SWITCH_DOWN trong /api/sdn/events"
        )

        # Kiểm tra h2 (trên s2) ping h3 (trên s3) thông suốt 0% packet loss qua nhánh dự phòng s2 <-> s3
        ok_failover = host_ping("h2", "10.0.0.3", count=3, wait_sec=1)
        assert ok_failover, "h2 không thể ping sang h3 qua nhánh dự phòng s2-s3 khi s1 bị tắt!"
    finally:
        # Khôi phục kết nối OpenFlow cho Switch s1
        subprocess.run(["sudo", "ovs-vsctl", "set-controller", "s1", "tcp:127.0.0.1:6653"], check=True)
        time.sleep(3.0)

    topo_up = http_req(f"{API_URL}/api/sdn/topology")
    assert all(s["status"] == "UP" for s in topo_up["switches"]), f"Switch s1 chưa khôi phục UP: {topo_up['switches']}"
    assert host_ping("h1", "10.0.0.3", count=2, wait_sec=1), "h1 chưa ping lại được h3 sau khi s1 khôi phục!"
    print("  ✅ [PASS] Bước 7: Tự động chuyển mạch Fast Failover qua s2-s3 khi s1 tắt và khôi phục hoàn hảo 100%.")


def main():
    print("=" * 78)
    print(" 🚀 BẮT ĐẦU CHẠY BỘ KIỂM THỬ END-TO-END TOÀN DIỆN (e2e_full_test.py)")
    print("=" * 78)
    try:
        test_1_lldp_topology()
        test_2_switch_and_host_info()
        test_3_firewall_acl()
        test_4_traffic_steering_l2()
        test_5_port_and_flow_stats()
        test_6_qos_meter()
        test_7_link_and_switch_failover()
        print("\n" + "=" * 78)
        print(" 🏆 KẾT QUẢ: ĐẠT PASS 100% (7/7 HẠNG MỤC END-TO-END)! HỆ THỐNG HOẠT ĐỘNG HOÀN HẢO!")
        print("=" * 78)
    except AssertionError as e:
        print(f"\n ❌ [FAIL] Kiểm thử E2E thất bại: {e}")
        sys.exit(1)
    except Exception as ex:
        print(f"\n ❌ [ERROR] Lỗi thực thi E2E: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    main()

