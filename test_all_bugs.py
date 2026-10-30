#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script Kiểm Thử Tự Động 4 Lỗi Kỹ Thuật Hệ Thống SDN Data Controller (Mininet Edition)
Cách chạy:
    python3 test_all_bugs.py
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(SCRIPT_DIR, "venv", "bin", "python")

# Tự động chuyển sang Python 3.10 trong venv nếu đang gọi bằng Python hệ thống
try:
    import fastapi
    import ryu
except ImportError:
    if os.path.exists(VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(VENV_PYTHON):
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def test_bug_1_ai_copilot():
    from backend.api_server import AICopilotRequest, ai_copilot
    res = ai_copilot(AICopilotRequest(prompt="Chặn h2 gửi file tới h4 cổng 445"))
    assert res is not None, "Hàm ai_copilot trả về None (thiếu câu lệnh return)"
    assert isinstance(res, dict) and res.get("status") == "success", f"Trạng thái không hợp lệ: {res}"
    assert "parsed" in res and res["parsed"].get("intent") == "FIREWALL_DROP", f"Kết quả parse sai: {res}"
    print("[PASS] LỖI 1: Endpoint AI Copilot (/api/ai/copilot) trả về JSON hợp lệ.")


def test_bug_2_dynamic_failover():
    from controller.ryu_sdn_controller import SDNDataController
    ctrl = SDNDataController()
    assert hasattr(ctrl, "blocked_ports") and ctrl.blocked_ports == {(2, 3), (3, 4)}, (
        "Khởi tạo self.blocked_ports không đúng {(2, 3), (3, 4)}"
    )
    ctrl.mac_to_port = {1: {"00:00:00:00:00:01": 1}}

    class DummyOfproto:
        OFPPR_ADD = 0
        OFPPR_DELETE = 1
        OFPPR_MODIFY = 2
        OFPPS_LINK_DOWN = 1
        OFPFC_DELETE = 3
        OFPP_ANY = 0xffffffff
        OFPG_ANY = 0xffffffff
        OFPP_CONTROLLER = 0xfffffffd
        OFPCML_NO_BUFFER = 0xffff
        OFPIT_APPLY_ACTIONS = 4

    class DummyParser:
        def OFPMatch(self, **kwargs):
            return kwargs

        def OFPFlowMod(self, **kwargs):
            return kwargs

        def OFPActionOutput(self, port, max_len=0):
            return ("OUTPUT", port)

        def OFPInstructionActions(self, type_, actions):
            return (type_, actions)

    class DummyDP:
        id = 1
        ofproto = DummyOfproto()
        ofproto_parser = DummyParser()

        def __init__(self):
            self.sent_msgs = []

        def send_msg(self, msg):
            self.sent_msgs.append(msg)

    dp1 = DummyDP()
    ctrl.datapaths[1] = dp1

    class DummyDesc:
        port_no = 2
        name = b"s1-eth2"
        state = 1  # LINK_DOWN

    class DummyMsg:
        datapath = dp1
        reason = DummyOfproto.OFPPR_MODIFY
        desc = DummyDesc()

    class DummyEv:
        msg = DummyMsg()

    # Giả lập đứt cáp (LINK DOWN)
    ctrl.port_status_handler(DummyEv())
    assert len(ctrl.blocked_ports) == 0, "Nhánh dự phòng chưa được mở khóa khi LINK DOWN"
    assert len(ctrl.mac_to_port) == 0, "Bảng mac_to_port chưa được xóa khi LINK DOWN"
    assert any(isinstance(m, dict) and m.get("command") == DummyOfproto.OFPFC_DELETE for m in dp1.sent_msgs), (
        "Chưa gửi bản tin OFPFlowMod (OFPFC_DELETE) để xóa các flow L2 cũ"
    )

    # Giả lập khôi phục cáp (LINK UP)
    DummyDesc.state = 0  # LINK_UP
    ctrl.port_status_handler(DummyEv())
    assert ctrl.blocked_ports == {(2, 3), (3, 4)}, "Chưa khóa lại nhánh dự phòng khi LINK UP trở lại"
    print("[PASS] LỖI 2: Cơ chế chống Loop động & tự động hội tụ Failover (s2-s3) hoạt động chính xác.")


def test_bug_3_state_sync():
    from backend.api_server import sdn_state
    fw = sdn_state.get("firewall_rules", None)
    qos = sdn_state.get("qos_meters", None)
    assert fw == [] and qos == [], (
        f"sdn_state vẫn chứa dữ liệu giả lập lệch pha với OVS: firewall={fw}, qos={qos}"
    )
    print("[PASS] LỖI 3: Trạng thái khởi tạo sdn_state (firewall_rules & qos_meters) đồng bộ 100% với OVS.")


def test_bug_4_userspace_meter():
    topo_path = os.path.join(SCRIPT_DIR, "controller", "mininet_topology.py")
    with open(topo_path, "r", encoding="utf-8") as f:
        topo_src = f.read()
    count_user = topo_src.count("datapath='user'") + topo_src.count('datapath="user"')
    assert count_user >= 3, f"Các switch trong mininet_topology.py chưa cấu hình đủ datapath='user' (tìm thấy {count_user}/3)"
    print("[PASS] LỖI 4: Cả 3 Switch OVS (s1, s2, s3) đã cấu hình datapath='user' hỗ trợ đầy đủ OpenFlow 1.3 Meter Table.")


def test_bug_5_switch_stop_start():
    from controller.ryu_sdn_controller import SDNDataController, MAIN_DISPATCHER, DEAD_DISPATCHER
    from backend.api_server import EventWebhookRequest, receive_event_webhook, get_topology, get_events

    ctrl = SDNDataController()

    class DummyOfproto:
        OFPFC_DELETE = 3
        OFPP_ANY = 0xffffffff
        OFPG_ANY = 0xffffffff
        OFPP_CONTROLLER = 0xfffffffd
        OFPCML_NO_BUFFER = 0xffff
        OFPIT_APPLY_ACTIONS = 4
        OFP_NO_BUFFER = 0xffffffff

    class DummyParser:
        def OFPMatch(self, **kwargs):
            return kwargs

        def OFPFlowMod(self, **kwargs):
            return kwargs

        def OFPActionOutput(self, port, max_len=0):
            return ("OUTPUT", port)

        def OFPInstructionActions(self, type_, actions):
            return (type_, actions)

        def OFPPacketOut(self, **kwargs):
            return kwargs

    class DummyDP:
        ofproto = DummyOfproto()
        ofproto_parser = DummyParser()

        def __init__(self, dpid):
            self.id = dpid
            self.sent_msgs = []

        def send_msg(self, msg):
            self.sent_msgs.append(msg)

    class DummyStateEv:
        def __init__(self, datapath, state):
            self.datapath = datapath
            self.state = state

    dp1, dp2, dp3 = DummyDP(1), DummyDP(2), DummyDP(3)

    # 1. Khởi tạo cả 3 switch (s1, s2, s3) ở trạng thái UP (MAIN_DISPATCHER)
    for dp in (dp1, dp2, dp3):
        ctrl.state_change_handler(DummyStateEv(dp, MAIN_DISPATCHER))
    assert set(ctrl.datapaths.keys()) == {1, 2, 3}, "3 switch chưa được đăng ký vào ctrl.datapaths"
    assert ctrl.blocked_ports == {(2, 3), (3, 4)} and not ctrl.backup_link_active, (
        "Khóa chống Loop chưa bật khi đủ 3 switch UP"
    )

    # 2. Giả lập tắt switch s1 (switch s1 stop -> DEAD_DISPATCHER)
    ctrl.mac_to_port = {1: {"00:00:00:00:00:01": 1}, 2: {"00:00:00:00:00:02": 1}, 3: {"00:00:00:00:00:03": 1}}
    dp2.sent_msgs.clear()
    dp3.sent_msgs.clear()
    ctrl.state_change_handler(DummyStateEv(dp1, DEAD_DISPATCHER))

    assert 1 not in ctrl.datapaths, "Switch s1 chưa bị xóa khỏi self.datapaths khi DEAD_DISPATCHER"
    assert len(ctrl.blocked_ports) == 0 and ctrl.backup_link_active is True, (
        "Nhánh dự phòng s2-s3 chưa được mở khóa khi s1 bị stop"
    )
    assert any(m.get("command") == DummyOfproto.OFPFC_DELETE for m in dp2.sent_msgs), (
        "Chưa xóa Flow L2 cũ trên s2 khi s1 bị stop"
    )
    assert any(m.get("command") == DummyOfproto.OFPFC_DELETE for m in dp3.sent_msgs), (
        "Chưa xóa Flow L2 cũ trên s3 khi s1 bị stop"
    )

    # 3. Kiểm tra chuyển tiếp gói tin giữa h2 (trên s2) và h3 (trên s3) qua nhánh dự phòng s2-port3 <-> s3-port4
    from ryu.lib.packet import packet, ethernet
    pkt = packet.Packet()
    pkt.add_protocol(ethernet.ethernet(dst="ff:ff:ff:ff:ff:ff", src="00:00:00:00:00:02", ethertype=0x0806))
    pkt.serialize()

    class DummyPktMsg:
        def __init__(self, dp, in_port, data):
            self.datapath = dp
            self.match = {"in_port": in_port}
            self.data = data
            self.buffer_id = DummyOfproto.OFP_NO_BUFFER

    class DummyPktEv:
        def __init__(self, msg):
            self.msg = msg

    dp2.sent_msgs.clear()
    ctrl.packet_in_handler(DummyPktEv(DummyPktMsg(dp2, 1, pkt.data)))
    assert len(dp2.sent_msgs) == 1 and ("OUTPUT", 3) in dp2.sent_msgs[0]["actions"], (
        "s2 không flood gói ARP ra port 3 (nhánh dự phòng sang s3)"
    )

    dp3.sent_msgs.clear()
    ctrl.packet_in_handler(DummyPktEv(DummyPktMsg(dp3, 4, pkt.data)))
    assert len(dp3.sent_msgs) == 1 and ("OUTPUT", 1) in dp3.sent_msgs[0]["actions"], (
        "s3 chặn mất gói tin đến từ port 4 (nhánh dự phòng từ s2) thay vì chuyển tới h3 (port 1)"
    )

    # 4. Kiểm tra Webhook SWITCH_DOWN & API /api/sdn/topology, /api/sdn/events
    receive_event_webhook(EventWebhookRequest(
        type="SWITCH_CHANGE", dpid=1, port_no=0, reason="SWITCH_DOWN"
    ))
    topo = get_topology()
    sw_map = {int(s["dpid"], 16): s for s in topo["switches"]}
    link_map = {f"{l['src']}-{l['dst']}": l for l in topo["links"]}
    events = get_events(limit=10)

    assert sw_map[1]["status"] == "DOWN" and sw_map[1]["online"] is False, f"Switch s1 chưa chuyển sang DOWN: {sw_map[1]}"
    assert link_map["s1-s2"]["status"] == "DOWN" and link_map["s1-s3"]["status"] == "DOWN", (
        f"Các link nối với s1 chưa chuyển sang DOWN: {link_map}"
    )
    assert link_map["s2-s3"]["status"] == "UP", f"Nhánh dự phòng s2-s3 không ở trạng thái UP: {link_map['s2-s3']}"
    assert any(e.get("reason") == "SWITCH_DOWN" and e.get("dpid") == 1 for e in events), (
        "Không tìm thấy bản ghi sự kiện SWITCH_DOWN cho s1 trong /api/sdn/events"
    )

    # 5. Khôi phục s1 (switch s1 start -> MAIN_DISPATCHER & SWITCH_UP)
    ctrl.state_change_handler(DummyStateEv(dp1, MAIN_DISPATCHER))
    assert ctrl.blocked_ports == {(2, 3), (3, 4)} and not ctrl.backup_link_active, (
        "Chưa khôi phục khóa chống Loop khi s1 kết nối trở lại"
    )
    receive_event_webhook(EventWebhookRequest(
        type="SWITCH_CHANGE", dpid=1, port_no=0, reason="SWITCH_UP"
    ))
    topo_up = get_topology()
    sw_map_up = {int(s["dpid"], 16): s for s in topo_up["switches"]}
    assert sw_map_up[1]["status"] == "UP" and sw_map_up[1]["online"] is True, "Switch s1 chưa khôi phục UP"
    print("[PASS] LỖI 5: Xử lý sự cố tắt/bật Switch (switch sX stop/start), Fast Failover s2-s3 & đồng bộ Topology/Events hoạt động chính xác.")


if __name__ == "__main__":
    print("=" * 72)
    print(" 🔍 ĐANG CHẠY KIỂM THỬ TỰ ĐỘNG HỆ THỐNG SDN PROJECT")
    print("=" * 72)
    try:
        test_bug_1_ai_copilot()
        test_bug_2_dynamic_failover()
        test_bug_3_state_sync()
        test_bug_4_userspace_meter()
        test_bug_5_switch_stop_start()
        print("=" * 72)
        print(" ✅ TẤT CẢ 5 BÀI TEST ĐỀU ĐẠT [PASS] (5/5)! HỆ THỐNG HOẠT ĐỘNG HOÀN HẢO!")
        print("=" * 72)
    except AssertionError as e:
        print(f" ❌ [FAIL] Kiểm thử thất bại: {e}")
        sys.exit(1)

