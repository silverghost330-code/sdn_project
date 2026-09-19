# -*- coding: utf-8 -*-
"""
Ryu SDN Data Controller Application (OpenFlow 1.3)
Điều khiển lưu lượng, chuyển tiếp L2, Tường lửa Firewall và QoS Meter Table.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp, icmp

class SDNDataController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SDNDataController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.logger.info(">>> SDN Data Controller (OpenFlow 1.3) đã sẵn sàng hoạt động! <<<")

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

        # Loop-Free Spanning Tree Broadcast Prevention for 3-Switch Mesh (s1 Core, s2 Dist, s3 Server Farm)
        # Redundant mesh trunk: s2-port3 <-> s3-port4
        is_broadcast_or_multicast = eth.dst == 'ff:ff:ff:ff:ff:ff' or eth.dst.startswith('01:') or dst not in self.mac_to_port[dpid]
        if is_broadcast_or_multicast:
            if (dpid == 2 and in_port == 3) or (dpid == 3 and in_port == 4):
                # Discard broadcast packet coming from redundant trunk link to prevent broadcast storm
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
            # Loop-free Spanning Tree broadcast flooding
            actions = []
            if dpid == 1:
                flood_ports = [1, 2, 3]
            elif dpid == 2:
                flood_ports = [1, 2]  # Port 3 is redundant trunk to s3
            elif dpid == 3:
                flood_ports = [1, 2, 3]  # Port 4 is redundant trunk to s2
            else:
                flood_ports = [p for p in range(1, 10)]

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
