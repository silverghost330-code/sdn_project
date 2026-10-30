# -*- coding: utf-8 -*-
"""
Ryu SDN Data Controller Application (OpenFlow 1.3)
Điều khiển lưu lượng, chuyển tiếp L2, Tường lửa Firewall và QoS Meter Table.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp, icmp

class SDNDataController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SDNDataController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        # Quản lý động các cổng bị khóa chống Loop (mặc định khóa nhánh dự phòng s2-port3 <-> s3-port4)
        self.blocked_ports = {(2, 3), (3, 4)}
        self.backup_link_active = False
        self.down_ports = set()
        self.down_switches = set()
        self.logger.info(">>> SDN Data Controller (OpenFlow 1.3) đã sẵn sàng hoạt động! <<<")

    def reset_l2_flows(self):
        """Xóa bảng MAC đã học và các flow chuyển tiếp L2 cũ trên tất cả các datapath (giữ lại table-miss flow priority 0)"""
        self.mac_to_port.clear()
        for dpid, datapath in list(self.datapaths.items()):
            try:
                ofproto = datapath.ofproto
                parser = datapath.ofproto_parser
                match = parser.OFPMatch()
                del_mod = parser.OFPFlowMod(
                    datapath=datapath,
                    command=ofproto.OFPFC_DELETE,
                    out_port=ofproto.OFPP_ANY,
                    out_group=ofproto.OFPG_ANY,
                    match=match
                )
                datapath.send_msg(del_mod)

                # Cài đặt lại Table-miss Flow Entry (priority 0)
                actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
                self.add_flow(datapath, priority=0, match=match, actions=actions)

                # Cài đặt lại LLDP Flow Entry (priority 65535) để bảo toàn khám phá Topology LLDP
                lldp_match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_LLDP,
                    eth_dst='01:80:c2:00:00:0e'
                )
                self.add_flow(datapath, priority=0xFFFF, match=lldp_match, actions=actions)
            except Exception as ex:
                self.logger.error("Lỗi khi làm mới Flow trên Switch s%s: %s", dpid, ex)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        """Phát hiện sự kiện Switch kết nối (start) hoặc mất kết nối (stop / del-br)"""
        datapath = ev.datapath
        dpid = getattr(datapath, 'id', None)

        if ev.state == DEAD_DISPATCHER:
            if dpid is None:
                return
            self.datapaths.pop(dpid, None)
            self.mac_to_port.pop(dpid, None)
            self.down_switches.add(dpid)
            # Xóa các port của switch bị tắt khỏi down_ports
            self.down_ports = {p for p in self.down_ports if p[0] != dpid}

            # Kích hoạt Fast Failover cho các switch còn sống
            self.blocked_ports.clear()
            self.backup_link_active = True
            self.reset_l2_flows()
            self.logger.warning(
                "🚨 [SWITCH DOWN] Switch s%s mất kết nối! Đã mở khóa nhánh dự phòng s2-s3 và làm mới bảng Flow L2!",
                dpid
            )

            try:
                import requests
                requests.post(
                    "http://127.0.0.1:8000/api/sdn/webhook/event",
                    json={
                        "type": "SWITCH_CHANGE",
                        "dpid": dpid,
                        "port_no": 0,
                        "reason": "SWITCH_DOWN"
                    },
                    timeout=0.5
                )
            except Exception as ex:
                self.logger.debug("Không thể gửi webhook SWITCH_DOWN: %s", ex)

        elif ev.state == MAIN_DISPATCHER:
            if dpid is None:
                return
            self.datapaths[dpid] = datapath
            self.down_switches.discard(dpid)

            # Kiểm tra nếu cả 3 switch {1, 2, 3} đều có mặt và không có cổng nào đang lỗi vật lý
            if {1, 2, 3}.issubset(set(self.datapaths.keys())) and not self.down_ports:
                self.blocked_ports = {(2, 3), (3, 4)}
                self.backup_link_active = False
                self.reset_l2_flows()
                self.logger.info(
                    "🟢 [SWITCH UP] Cả 3 Switch (s1, s2, s3) đã hoạt động! Khôi phục khóa chống Loop trên nhánh s2-s3."
                )

            try:
                import requests
                requests.post(
                    "http://127.0.0.1:8000/api/sdn/webhook/event",
                    json={
                        "type": "SWITCH_CHANGE",
                        "dpid": dpid,
                        "port_no": 0,
                        "reason": "SWITCH_UP"
                    },
                    timeout=0.5
                )
            except Exception as ex:
                self.logger.debug("Không thể gửi webhook SWITCH_UP: %s", ex)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.datapaths[datapath.id] = datapath

        # Cài đặt Table-miss Flow Entry: Gói chưa biết gửi lên Controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("Đã cấu hình Table-miss Flow Entry cho Switch DPID: %016x", datapath.id)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath, buffer_id=buffer_id,
                priority=priority, match=match,
                instructions=inst, idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath, priority=priority,
                match=match, instructions=inst,
                idle_timeout=idle_timeout, hard_timeout=hard_timeout
            )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # Loop-Free Spanning Tree Broadcast Prevention with Dynamic Failover
        # Redundant mesh trunk: s2-port3 <-> s3-port4 (được quản lý động qua self.blocked_ports)
        is_broadcast_or_multicast = eth.dst == 'ff:ff:ff:ff:ff:ff' or eth.dst.startswith('01:') or dst not in self.mac_to_port[dpid]
        if is_broadcast_or_multicast:
            if (dpid, in_port) in self.blocked_ports:
                # Discard broadcast packet coming from blocked redundant trunk link to prevent broadcast storm
                return

        # L2 MAC Learning
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            actions = [parser.OFPActionOutput(out_port)]

            # Nếu đã học được port đích, cài Flow Entry để switch tự forward ở Data Plane
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, priority=10, match=match, actions=actions, buffer_id=msg.buffer_id, idle_timeout=60)
                return
            else:
                self.add_flow(datapath, priority=10, match=match, actions=actions, idle_timeout=60)
        else:
            # Loop-free Spanning Tree broadcast flooding (tự động mở cổng dự phòng khi Failover)
            actions = []
            if dpid == 1:
                all_ports = [1, 2, 3]
            elif dpid == 2:
                all_ports = [1, 2, 3]  # Port 3 là nhánh dự phòng sang s3
            elif dpid == 3:
                all_ports = [1, 2, 3, 4]  # Port 4 là nhánh dự phòng sang s2
            else:
                all_ports = [p for p in range(1, 10)]

            flood_ports = [p for p in all_ports if (dpid, p) not in self.blocked_ports]
            for p in flood_ports:
                if p != in_port:
                    actions.append(parser.OFPActionOutput(p))

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id,
            in_port=in_port, actions=actions, data=data
        )
        datapath.send_msg(out)

    def notify_backend(self, event_type, level, message, details=None):
        """Gửi thông báo biến động mạng về FastAPI Backend bất đồng bộ (non-blocking)"""
        def _send():
            try:
                import urllib.request
                import json
                payload = json.dumps({
                    "type": event_type,
                    "level": level,
                    "message": message,
                    "details": details or {}
                }).encode('utf-8')
                req = urllib.request.Request(
                    "http://127.0.0.1:8000/api/sdn/webhook/event",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                urllib.request.urlopen(req, timeout=0.5)
            except Exception:
                pass
        import threading
        threading.Thread(target=_send, daemon=True).start()

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """Phát hiện tức thời khi có cổng switch bị Up/Down/Rút cáp"""
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto
        port_name = msg.desc.name.decode('utf-8', 'ignore') if isinstance(msg.desc.name, bytes) else str(msg.desc.name)

        is_down = bool(msg.desc.state & ofproto.OFPPS_LINK_DOWN)
        state_str = "DOWN" if is_down else "UP"

        if reason == ofproto.OFPPR_ADD:
            self.down_ports.discard((dpid, port_no))
            desc = f"Switch s{dpid}: Cổng {port_no} ({port_name}) vừa được thêm vào mạng"
            self.logger.warning(f"🔔 [PORT ADD] {desc}")
            self.notify_backend("PORT_ADD", "INFO", desc, {"dpid": dpid, "port": port_no, "name": port_name})
        elif reason == ofproto.OFPPR_DELETE:
            self.down_ports.add((dpid, port_no))
            desc = f"Switch s{dpid}: Cổng {port_no} ({port_name}) đã bị xóa khỏi thiết bị"
            self.logger.warning(f"🚨 [PORT DELETE] {desc}")
            self.blocked_ports.clear()
            self.backup_link_active = True
            self.reset_l2_flows()
            self.notify_backend("PORT_DELETE", "DANGER", desc, {"dpid": dpid, "port": port_no, "name": port_name})
        elif reason == ofproto.OFPPR_MODIFY:
            if is_down:
                self.down_ports.add((dpid, port_no))
                # Mở khóa nhánh dự phòng s2-s3 khi phát hiện sự cố đứt cáp và xóa bảng MAC/Flow cũ
                self.blocked_ports.clear()
                self.backup_link_active = True
                self.reset_l2_flows()
                self.logger.warning("⚡ [FAILOVER] Đã mở khóa nhánh dự phòng s2-s3 và làm mới bảng MAC/Flow!")
            else:
                self.down_ports.discard((dpid, port_no))
                # Khôi phục khóa chống Loop trên nhánh dự phòng s2-s3 khi đường truyền UP trở lại và không có switch nào đang DOWN
                if not self.down_ports and not self.down_switches:
                    self.blocked_ports = {(2, 3), (3, 4)}
                    self.backup_link_active = False
                    self.reset_l2_flows()
                    self.logger.info("🔄 [RECOVERY] Đã khôi phục khóa chống Loop trên nhánh dự phòng s2-s3!")

            level = "DANGER" if is_down else "SUCCESS"
            icon = "🚨" if is_down else "🟢"
            desc = f"{icon} Switch s{dpid}: Cổng {port_no} ({port_name}) chuyển trạng thái -> {state_str}"
            self.logger.warning(f"[PORT STATUS] {desc}")
            self.notify_backend("PORT_STATUS", level, desc, {"dpid": dpid, "port": port_no, "name": port_name, "state": state_str})

    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):
        """Bắt sự kiện khi Flow hết hạn idle_timeout hoặc bị gỡ"""
        msg = ev.msg
        dp = msg.datapath
        desc = f"Switch s{dp.id}: Luồng (Priority {msg.priority}) đã hết hạn TCAM (Khớp {msg.packet_count} gói, {msg.byte_count} B)"
        self.logger.info(f"ℹ️ [FLOW TIMEOUT] {desc}")
        self.notify_backend("FLOW_REMOVED", "INFO", desc, {"dpid": dp.id, "priority": msg.priority, "packets": msg.packet_count})

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def error_msg_handler(self, ev):
        """Bắt các lỗi giao thức OpenFlow từ switch"""
        msg = ev.msg
        dp = msg.datapath
        desc = f"Switch s{dp.id} báo lỗi OpenFlow: type=0x{msg.type:02x}, code=0x{msg.code:02x}"
        self.logger.error(f"⚠️ [OFP ERROR] {desc}")
        self.notify_backend("OFP_ERROR", "WARNING", desc, {"dpid": dp.id, "type": msg.type, "code": msg.code})

