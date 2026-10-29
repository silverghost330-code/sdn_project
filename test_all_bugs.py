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


if __name__ == "__main__":
    print("=" * 72)
    print(" 🔍 ĐANG CHẠY KIỂM THỬ TỰ ĐỘNG 4 LỖI KỸ THUẬT SDN PROJECT")
    print("=" * 72)
    try:
        test_bug_1_ai_copilot()
        test_bug_2_dynamic_failover()
        test_bug_3_state_sync()
        test_bug_4_userspace_meter()
        print("=" * 72)
        print(" ✅ TẤT CẢ 4 BÀI TEST ĐỀU ĐẠT [PASS] (4/4)! HỆ THỐNG HOẠT ĐỘNG HOÀN HẢO!")
        print("=" * 72)
    except AssertionError as e:
        print(f" ❌ [FAIL] Kiểm thử thất bại: {e}")
        sys.exit(1)

