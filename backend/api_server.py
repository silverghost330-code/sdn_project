# -*- coding: utf-8 -*-
"""
FastAPI Northbound Gateway for SDN Controller (Mininet Linux Server Edition)
Cung cấp REST API cho Web Dashboard, tương tác trực tiếp với Ryu Controller (OpenFlow 1.3).
"""

import os
import sys
import json
import time
import subprocess
import requests
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "web"))

try:
    from ai_engine import call_gemini_api, extract_and_validate_json, parse_sdn_intent_locally
except ImportError:
    from backend.ai_engine import call_gemini_api, extract_and_validate_json, parse_sdn_intent_locally

app = FastAPI(
    title="SDN Data Controller - Mininet Linux Server Edition",
    description="Hệ thống điều khiển lưu lượng mạng SDN tập trung qua OpenFlow 1.3 cho Mininet",
    version="2.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RYU_BASE_URL = os.environ.get("RYU_BASE_URL", "http://127.0.0.1:8080")

# Trạng thái mạng ảo hóa Mininet
sdn_state = {
    "environment": "Mininet Network Namespaces (Linux Server)",
    "controller_url": "127.0.0.1:6653",
    "switches": [
        {"dpid": "0000000000000001", "name": "s1 (Core Switch)", "ports": [1, 2, 3], "status": "ACTIVE", "flow_count": 5},
        {"dpid": "0000000000000002", "name": "s2 (Distribution)", "ports": [1, 2, 3], "status": "ACTIVE", "flow_count": 4},
        {"dpid": "0000000000000003", "name": "s3 (Server Farm)", "ports": [1, 2, 3, 4], "status": "ACTIVE", "flow_count": 5}
    ],
    "hosts": [
        {"id": "h1", "ip": "10.0.0.1", "mac": "00:00:00:00:00:01", "switch": "s1", "port": 1, "name": "Host h1 (Client PC 1)"},
        {"id": "h2", "ip": "10.0.0.2", "mac": "00:00:00:00:00:02", "switch": "s2", "port": 1, "name": "Host h2 (Client PC 2)"},
        {"id": "h3", "ip": "10.0.0.3", "mac": "00:00:00:00:00:03", "switch": "s3", "port": 1, "name": "Host h3 (Web Server HTTP :80)"},
        {"id": "h4", "ip": "10.0.0.4", "mac": "00:00:00:00:00:04", "switch": "s3", "port": 2, "name": "Host h4 (Windows File Server :445/:8080)"}
    ],
    "links": [
        {"src": "s1", "src_port": 2, "dst": "s2", "dst_port": 2, "speed": "10Gbps (RAM Bus)", "status": "UP"},
        {"src": "s1", "src_port": 3, "dst": "s3", "dst_port": 3, "speed": "10Gbps (RAM Bus)", "status": "UP"},
        {"src": "s2", "src_port": 3, "dst": "s3", "dst_port": 4, "speed": "10Gbps (RAM Bus)", "status": "UP"}
    ],
    "firewall_rules": [],
    "qos_meters": [],
    "flows": [
        {"table_id": 0, "priority": 0, "match": "ALL", "action": "CONTROLLER:65535", "packets": 0, "bytes": 0}
    ]
}

class FirewallRuleCreate(BaseModel):
    dpid: int = Field(default=1, description="Datapath ID của Switch OVS")
    src_ip: Optional[str] = Field(default="", description="IP Nguồn")
    dst_ip: Optional[str] = Field(default="", description="IP Đích")
    proto: Optional[str] = Field(default="ANY", description="Giao thức (TCP, UDP, ICMP, ANY)")
    dst_port: Optional[int] = Field(default=None, description="Cổng dịch vụ")
    action: str = Field(default="DROP", description="DROP hoặc ALLOW")
    description: Optional[str] = Field(default="", description="Mô tả mục đích rule")

class QoSMeterCreate(BaseModel):
    dpid: int = Field(default=1, description="Datapath ID của Switch OVS")
    rate_kbps: int = Field(default=1000, description="Giới hạn tốc độ tính bằng Kbps")
    burst_size: int = Field(default=500)
    src_ip: Optional[str] = Field(default="", description="IP Nguồn (để trống = Tất cả)")
    dst_ip: Optional[str] = Field(default="", description="IP Đích (để trống = Tất cả)")
    target: Optional[str] = Field(default="All", description="Mô tả đối tượng")
    description: Optional[str] = Field(default="")

class AICopilotRequest(BaseModel):
    prompt: str
    api_key: Optional[str] = ""

sdn_events = [
    {
        "id": 1,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "SYSTEM",
        "level": "SUCCESS",
        "message": "SDN Controller & Northbound Gateway đã sẵn sàng giám sát",
        "details": {"mode": "Mininet Mesh Topology"}
    }
]
last_link_states = {}

def record_sdn_event(event_type: str, level: str, message: str, details: Optional[Dict[str, Any]] = None):
    new_id = (sdn_events[0]["id"] + 1) if sdn_events else 1
    d = details or {}
    sw = None
    if "dpid" in d:
        sw = f"s{d['dpid']}"
    elif "src" in d:
        sw = d["src"]
    elif "switch" in d:
        sw = d["switch"]

    event_entry = {
        "id": new_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": event_type,
        "level": level.upper(),  # SUCCESS, INFO, WARNING, DANGER
        "message": message,
        "detail": message,
        "switch": sw,
        "details": d
    }
    sdn_events.insert(0, event_entry)
    if len(sdn_events) > 100:
        sdn_events.pop()
    return event_entry

def sync_live_topology():
    """
    Truy vấn trực tiếp OpenFlow portdesc từ Ryu để phát hiện sự thay đổi link status UP / DOWN
    """
    global last_link_states
    port_states = {}

    try:
        for dpid in [1, 2, 3]:
            r = requests.get(f"{RYU_BASE_URL}/stats/portdesc/{dpid}", timeout=0.4)
            if r.status_code == 200:
                ports = r.json().get(str(dpid), [])
                for p in ports:
                    pno = p.get("port_no")
                    if isinstance(pno, int):
                        state = p.get("state", 0)
                        is_down = bool(state & 1)
                        port_states[(dpid, pno)] = is_down
    except Exception:
        pass

    sw_dpid_map = {"s1": 1, "s2": 2, "s3": 3}
    for link in sdn_state["links"]:
        src_id = sw_dpid_map.get(link["src"])
        dst_id = sw_dpid_map.get(link["dst"])
        src_p = link["src_port"]
        dst_p = link["dst_port"]

        src_down = port_states.get((src_id, src_p), False)
        dst_down = port_states.get((dst_id, dst_p), False)
        link_down = src_down or dst_down
        new_status = "DOWN" if link_down else "UP"

        link_key = f"{link['src']}-{link['dst']}"
        old_status = last_link_states.get(link_key, "UP")

        if old_status != new_status:
            last_link_states[link_key] = new_status
            link["status"] = new_status
            if new_status == "DOWN":
                record_sdn_event(
                    "LINK_DOWN", "DANGER",
                    f"🚨 [ĐỨT ĐƯỜNG TRUYỀN] Liên kết {link['src']} <-> {link['dst']} (cổng {link['src']}-eth{src_p} / {link['dst']}-eth{dst_p}) đã BỊ NGẮT (DOWN)!",
                    {"src": link["src"], "dst": link["dst"], "status": "DOWN"}
                )
            else:
                record_sdn_event(
                    "LINK_UP", "SUCCESS",
                    f"🟢 [PHỤC HỒI KẾT NỐI] Liên kết {link['src']} <-> {link['dst']} đã HOẠT ĐỘNG TRỞ LẠI (UP)!",
                    {"src": link["src"], "dst": link["dst"], "status": "UP"}
                )
        else:
            link["status"] = new_status

    for host in sdn_state["hosts"]:
        sw_id = sw_dpid_map.get(host["switch"])
        p_no = host["port"]
        h_down = port_states.get((sw_id, p_no), False)
        new_h_status = "DOWN" if h_down else "UP"
        h_key = f"{host['id']}-{host['switch']}"
        old_h_status = last_link_states.get(h_key, "UP")
        if old_h_status != new_h_status:
            last_link_states[h_key] = new_h_status
            host["status"] = new_h_status
            if new_h_status == "DOWN":
                record_sdn_event("HOST_DISCONNECTED", "WARNING", f"⚠️ Cổng kết nối máy {host['id']} ({host['name']}) tới {host['switch']} bị ngắt!")
            else:
                record_sdn_event("HOST_CONNECTED", "SUCCESS", f"🟢 Máy {host['id']} ({host['name']}) đã kết nối lại tới {host['switch']}!")
        else:
            host["status"] = new_h_status

class EventWebhookRequest(BaseModel):
    type: str = "GENERIC"
    level: str = "INFO"
    message: str = ""
    details: Optional[Dict[str, Any]] = None

@app.get("/api/sdn/status")
def get_status():
    sync_live_topology()
    ryu_online = False
    try:
        r = requests.get(f"{RYU_BASE_URL}/stats/switches", timeout=0.6)
        if r.status_code == 200:
            ryu_online = True
    except Exception:
        pass

    all_links_up = all(l.get("status") == "UP" for l in sdn_state["links"])

    return {
        "controller": "Ryu SDN Controller (OpenFlow 1.3)",
        "platform": "Mininet Network Namespaces (Linux Server)",
        "ryu_online": ryu_online,
        "mode": "Live Mininet + Ryu Connected" if ryu_online else "Standby / Mininet Ready",
        "switch_count": len(sdn_state["switches"]),
        "host_count": len(sdn_state["hosts"]),
        "firewall_rules_count": len(sdn_state["firewall_rules"]),
        "qos_meters_count": len(sdn_state["qos_meters"]),
        "links_status": "ALL_UP" if all_links_up else "ALERT_DOWN",
        "events_count": len(sdn_events)
    }

@app.get("/api/sdn/topology")
def get_topology():
    sync_live_topology()
    return {
        "platform": "Mininet Topology",
        "switches": sdn_state["switches"],
        "hosts": sdn_state["hosts"],
        "links": sdn_state["links"]
    }

@app.get("/api/sdn/events")
def get_events(limit: int = 50):
    sync_live_topology()
    return sdn_events[:limit]

@app.post("/api/sdn/events/webhook")
def receive_event_webhook(req: EventWebhookRequest):
    event = record_sdn_event(req.type, req.level, req.message, req.details)
    return {"status": "ok", "event": event}

@app.delete("/api/sdn/events")
def clear_events():
    sdn_events.clear()
    record_sdn_event("SYSTEM", "INFO", "Đã dọn sạch lịch sử sự kiện mạng")
    return {"status": "ok", "message": "Đã dọn sạch nhật ký"}

@app.get("/api/sdn/switches")
def get_switches():
    try:
        r = requests.get(f"{RYU_BASE_URL}/stats/switches", timeout=0.8)
        if r.status_code == 200:
            connected_dpids = r.json()
            for sw in sdn_state["switches"]:
                sw_dpid_int = int(sw["dpid"], 16)
                if sw_dpid_int in connected_dpids:
                    sw["status"] = "ACTIVE"
                    try:
                        rf = requests.get(f"{RYU_BASE_URL}/stats/flow/{sw_dpid_int}", timeout=0.5)
                        if rf.status_code == 200:
                            flows = rf.json().get(str(sw_dpid_int), [])
                            sw["flow_count"] = len(flows)
                    except Exception:
                        pass
                else:
                    sw["status"] = "STANDBY"
    except Exception:
        pass
    return sdn_state["switches"]

@app.get("/api/sdn/flows")
def get_flows(dpid: Optional[str] = "all"):
    formatted_flows = []
    try:
        dpids_to_query = [1, 2, 3] if (not dpid or dpid == "all") else [int(dpid)]
        for sw_id in dpids_to_query:
            r = requests.get(f"{RYU_BASE_URL}/stats/flow/{sw_id}", timeout=0.8)
            if r.status_code == 200:
                data = r.json()
                raw_flows = data.get(str(sw_id), [])
                for f in raw_flows:
                    actions_list = f.get("actions", [])
                    if not actions_list:
                        act_str = "DROP"
                    else:
                        act_str = ", ".join([str(a.get("type", a) if isinstance(a, dict) else a) for a in actions_list])
                    formatted_flows.append({
                        "switch": f"s{sw_id}",
                        "dpid": sw_id,
                        "table_id": f.get("table_id", 0),
                        "priority": f.get("priority", 0),
                        "match": f.get("match", {}),
                        "action": act_str,
                        "packets": f.get("packet_count", 0),
                        "bytes": f.get("byte_count", 0),
                        "duration_sec": f.get("duration_sec", 0),
                        "idle_timeout": f.get("idle_timeout", 0)
                    })
        if formatted_flows:
            return formatted_flows
    except Exception:
        pass
    return sdn_state["flows"]

def resolve_out_port(dpid: int, src_ip: str = "", dst_ip: str = "") -> int:
    """
    Xác định cổng ra (egress port) tối ưu cho switch OVS theo kiến trúc Spanning Tree:
    - s1 (Core Switch, DPID 1):
        + h1 (10.0.0.1) -> port 1
        + h2 (10.0.0.2) -> port 2 (sang s2)
        + h3, h4 (10.0.0.3, 10.0.0.4) -> port 3 (sang s3)
    - s2 (Distribution Switch, DPID 2):
        + h2 (10.0.0.2) -> port 1
        + Uplink tới s1 Core (dẫn tới h1, h3, h4) -> port 2
    - s3 (Server Farm Switch, DPID 3):
        + h3 (10.0.0.3) -> port 1
        + h4 (10.0.0.4) -> port 2
        + Uplink tới s1 Core (dẫn tới h1, h2) -> port 3
    """
    link_status = {f"{l['src']}-{l['dst']}": l.get("status", "UP") for l in sdn_state.get("links", [])}
    s1_s2_up = link_status.get("s1-s2", "UP") == "UP"
    s1_s3_up = link_status.get("s1-s3", "UP") == "UP"

    routing_map = {
        1: {
            "10.0.0.1": 1,
            "10.0.0.2": 2 if s1_s2_up else 3,
            "10.0.0.3": 3 if s1_s3_up else 2,
            "10.0.0.4": 3 if s1_s3_up else 2
        },
        2: {
            "10.0.0.1": 2 if s1_s2_up else 3,
            "10.0.0.2": 1,
            "10.0.0.3": 2 if (s1_s2_up and s1_s3_up) else 3,
            "10.0.0.4": 2 if (s1_s2_up and s1_s3_up) else 3
        },
        3: {
            "10.0.0.1": 3 if s1_s3_up else 4,
            "10.0.0.2": 3 if (s1_s3_up and s1_s2_up) else 4,
            "10.0.0.3": 1,
            "10.0.0.4": 2
        }
    }

    if dpid in routing_map and dst_ip in routing_map[dpid]:
        return routing_map[dpid][dst_ip]

    # Nếu không có dst_ip nhưng có src_ip trên switch biên:
    if src_ip:
        if dpid == 2:
            return 1 if src_ip != "10.0.0.2" else (2 if s1_s2_up else 3)
        elif dpid == 3:
            return (3 if s1_s3_up else 4) if src_ip in ["10.0.0.3", "10.0.0.4"] else 1
        elif dpid == 1:
            return 1 if src_ip == "10.0.0.1" else 3

    # Fallback tra cứu từ Ryu flow stats nếu flow đã được học
    try:
        r = requests.get(f"{RYU_BASE_URL}/stats/flow/{dpid}", timeout=0.6)
        if r.status_code == 200:
            flows = r.json().get(str(dpid), [])
            for f in flows:
                match = f.get("match", {})
                if dst_ip and (match.get("nw_dst") == dst_ip or match.get("ipv4_dst") == dst_ip):
                    for act in f.get("actions", []):
                        if isinstance(act, str) and act.startswith("OUTPUT:"):
                            return int(act.split(":")[1])
    except Exception:
        pass

    default_egress = {1: 3, 2: 2, 3: 3}
    return default_egress.get(dpid, 1)

@app.get("/api/sdn/firewall")
def get_firewall_rules():
    return sdn_state["firewall_rules"]

@app.post("/api/sdn/firewall")
def add_firewall_rule(rule: FirewallRuleCreate):
    match_dict = {}
    is_ip_rule = bool(rule.src_ip or rule.dst_ip or (rule.proto and rule.proto.upper() != "ANY") or rule.dst_port)
    if is_ip_rule:
        match_dict["dl_type"] = 2048  # 0x0800 IPv4
        if rule.src_ip:
            match_dict["nw_src"] = rule.src_ip
        if rule.dst_ip:
            match_dict["nw_dst"] = rule.dst_ip
        proto_up = rule.proto.upper() if rule.proto else "ANY"
        if proto_up == "TCP":
            match_dict["ip_proto"] = 6
            if rule.dst_port:
                match_dict["tcp_dst"] = rule.dst_port
        elif proto_up == "UDP":
            match_dict["ip_proto"] = 17
            if rule.dst_port:
                match_dict["udp_dst"] = rule.dst_port
        elif proto_up == "ICMP":
            match_dict["ip_proto"] = 1

    out_port = resolve_out_port(rule.dpid, rule.src_ip, rule.dst_ip)
    ryu_actions = [] if rule.action.upper() == "DROP" else [{"type": "OUTPUT", "port": out_port}]

    new_id = max([r["id"] for r in sdn_state["firewall_rules"]], default=0) + 1
    new_rule = {
        "id": new_id,
        "dpid": rule.dpid,
        "priority": 1000,
        "src_ip": rule.src_ip,
        "dst_ip": rule.dst_ip,
        "proto": rule.proto.upper(),
        "dst_port": rule.dst_port,
        "action": rule.action.upper(),
        "match": match_dict,
        "description": rule.description or f"Rule {rule.action} {rule.src_ip} -> {rule.dst_ip}",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hits": 0
    }
    sdn_state["firewall_rules"].append(new_rule)

    # Đẩy trực tiếp xuống Ryu REST API nếu đang chạy
    try:
        ryu_rule = {
            "dpid": rule.dpid,
            "priority": 1000,
            "match": match_dict,
            "actions": ryu_actions
        }
        requests.post(f"{RYU_BASE_URL}/stats/flowentry/add", json=ryu_rule, timeout=1.5)
    except Exception as ex:
        print(f"[!] Lỗi đẩy Flow-Mod xuống Ryu: {ex}")

    record_sdn_event(
        "FIREWALL",
        "WARNING" if rule.action.upper() == "DROP" else "INFO",
        f"Đã nạp luật Firewall {rule.action.upper()} {rule.proto} từ {rule.src_ip or '*'} tới {rule.dst_ip or '*'} trên Switch s{rule.dpid}",
        {"rule_id": new_id, "action": rule.action, "dpid": rule.dpid}
    )

    return {"status": "success", "message": "Đã đẩy Flow-Mod xuống Switch Mininet thành công", "rule": new_rule}

@app.delete("/api/sdn/firewall/{rule_id}")
def delete_firewall_rule(rule_id: int):
    target_rule = None
    for r in sdn_state["firewall_rules"]:
        if r["id"] == rule_id:
            target_rule = r
            break
    if not target_rule:
        raise HTTPException(status_code=404, detail="Không tìm thấy Rule ID")

    sdn_state["firewall_rules"] = [r for r in sdn_state["firewall_rules"] if r["id"] != rule_id]

    try:
        del_rule = {
            "dpid": target_rule["dpid"],
            "priority": target_rule.get("priority", 1000),
            "match": target_rule.get("match", {})
        }
        requests.post(f"{RYU_BASE_URL}/stats/flowentry/delete_strict", json=del_rule, timeout=1.5)
    except Exception as ex:
        print(f"[!] Lỗi gỡ bỏ Flow-Mod trên Ryu: {ex}")

    record_sdn_event("FIREWALL", "INFO", f"Đã gỡ bỏ luật Firewall ID #{rule_id} trên Switch s{target_rule['dpid']}")

    return {"status": "success", "message": f"Đã xóa rule ID {rule_id}"}

@app.get("/api/sdn/qos")
def get_qos_meters():
    return sdn_state["qos_meters"]

@app.post("/api/sdn/qos")
def add_qos_meter(meter: QoSMeterCreate):
    new_id = max([m["meter_id"] for m in sdn_state["qos_meters"]], default=0) + 1
    src = (meter.src_ip or "").strip()
    dst = (meter.dst_ip or "").strip()

    # Nếu không truyền src_ip/dst_ip nhưng có target dạng regex
    if not src and not dst and meter.target:
        import re
        ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', meter.target)
        if len(ips) >= 2:
            src, dst = ips[0], ips[1]
        elif len(ips) == 1:
            src = ips[0]

    target_display = f"{src or '*'} ➔ {dst or '*'}" if (src or dst) else (meter.target or "Tất cả traffic")

    new_meter = {
        "meter_id": new_id,
        "dpid": meter.dpid,
        "rate_kbps": meter.rate_kbps,
        "burst_size": meter.burst_size,
        "src_ip": src,
        "dst_ip": dst,
        "target": target_display,
        "description": meter.description or f"Giới hạn {meter.rate_kbps} Kbps cho {target_display}",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    sdn_state["qos_meters"].append(new_meter)

    # Đẩy Meter Table và Flow Instruction xuống Ryu
    try:
        meter_req = {
            "dpid": meter.dpid,
            "flags": ["KBPS", "BURST", "STATS"],
            "meter_id": new_id,
            "bands": [
                {
                    "type": "DROP",
                    "rate": meter.rate_kbps,
                    "burst_size": meter.burst_size
                }
            ]
        }
        requests.post(f"{RYU_BASE_URL}/stats/meterentry/add", json=meter_req, timeout=1.5)

        # Xây dựng Flow Match theo IP nguồn và/hoặc IP đích
        match_fields = {"dl_type": 2048}
        if src:
            match_fields["nw_src"] = src
        if dst:
            match_fields["nw_dst"] = dst

        out_port = resolve_out_port(meter.dpid, src, dst)
        flow_meter = {
            "dpid": meter.dpid,
            "priority": 500,
            "match": match_fields,
            "actions": [
                {"type": "METER", "meter_id": new_id},
                {"type": "OUTPUT", "port": out_port}
            ]
        }
        requests.post(f"{RYU_BASE_URL}/stats/flowentry/add", json=flow_meter, timeout=1.5)
    except Exception as ex:
        print(f"[!] Lỗi đẩy Meter xuống Ryu: {ex}")

    record_sdn_event(
        "QOS",
        "INFO",
        f"Đã kích hoạt QoS Meter Table #{new_id} ({target_display} - {meter.rate_kbps} Kbps) trên Switch s{meter.dpid}",
        {"meter_id": new_id, "rate_kbps": meter.rate_kbps, "dpid": meter.dpid}
    )

    return {"status": "success", "message": f"Đã cài đặt OpenFlow Meter Table ({target_display} - {meter.rate_kbps} Kbps) vào Switch Mininet", "meter": new_meter}

def find_mininet_host_pid(host_name: str) -> Optional[int]:
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
        for line in out.splitlines():
            if f"mininet:{host_name}" in line and "ps -eo" not in line and "grep" not in line:
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    return int(parts[0])
    except Exception:
        pass
    return None

class PingTestRequest(BaseModel):
    src: str = Field(default="h2", description="Host nguồn (h1, h2, h3, h4)")
    dst: str = Field(default="10.0.0.4", description="IP hoặc host đích")
    count: int = Field(default=3, description="Số lượng gói tin ping")

@app.post("/api/sdn/ping")
def test_ping(req: PingTestRequest):
    host_map = {"h1": "10.0.0.1", "h2": "10.0.0.2", "h3": "10.0.0.3", "h4": "10.0.0.4"}
    src_host = req.src.lower().strip()
    dst_target = req.dst.strip()
    if dst_target in host_map:
        dst_target = host_map[dst_target]

    pid = find_mininet_host_pid(src_host)
    if not pid:
        return {
            "status": "error",
            "message": f"Không tìm thấy tiến trình Mininet cho host '{src_host}'. Vui lòng đảm bảo mạng Mininet đang chạy.",
            "output": ""
        }

    cmd = ["sudo", "mnexec", "-a", str(pid), "ping", "-c", str(req.count), "-W", "2", dst_target]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = proc.stdout or proc.stderr
        success = proc.returncode == 0
        return {
            "status": "success" if success else "failed",
            "return_code": proc.returncode,
            "src": src_host,
            "dst": dst_target,
            "output": output
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "output": ""}

@app.delete("/api/sdn/qos/{meter_id}")
def delete_qos_meter(meter_id: int):
    target_meter = None
    for m in sdn_state["qos_meters"]:
        if m["meter_id"] == meter_id:
            target_meter = m
            break
    if not target_meter:
        raise HTTPException(status_code=404, detail="Không tìm thấy Meter ID")

    sdn_state["qos_meters"] = [m for m in sdn_state["qos_meters"] if m["meter_id"] != meter_id]

    try:
        # Xóa Flow Entry bóp băng thông tương ứng trên Ryu
        del_flow = {
            "dpid": target_meter["dpid"],
            "priority": 500,
            "match": {"dl_type": 2048}
        }
        if target_meter.get("src_ip"):
            del_flow["match"]["nw_src"] = target_meter["src_ip"]
        if target_meter.get("dst_ip"):
            del_flow["match"]["nw_dst"] = target_meter["dst_ip"]
        requests.post(f"{RYU_BASE_URL}/stats/flowentry/delete_strict", json=del_flow, timeout=1.5)

        # Xóa Meter Entry
        requests.post(f"{RYU_BASE_URL}/stats/meterentry/delete", json={"dpid": target_meter["dpid"], "meter_id": meter_id}, timeout=1.5)
    except Exception as ex:
        print(f"[!] Lỗi gỡ bỏ Meter trên Ryu: {ex}")

    record_sdn_event("QOS", "INFO", f"Đã xóa QoS Meter ID #{meter_id} khỏi Switch s{target_meter['dpid']}")

    return {"status": "success", "message": f"Đã xóa QoS Meter ID {meter_id}"}

@app.post("/api/ai/copilot")
def ai_copilot(req: AICopilotRequest):
    if req.api_key:
        success, text = call_gemini_api(req.api_key, req.prompt)
        if success:
            ok, data, err = extract_and_validate_json(text)
            if ok:
                return {"status": "success", "ai_raw": text, "parsed": data}
            else:
                return {"status": "success", "ai_raw": text, "parse_error": err}
        # Nếu Gemini API lỗi (ví dụ key sai / hết quota), tự động fallback sang local parser!

    parsed_rule = parse_sdn_intent_locally(req.prompt)
    return {"status": "success", "ai_raw": "Local Intent Parser", "parsed": parsed_rule}
# ==============================================================================
# SNAPSHOT & 1-CLICK ROLLBACK MANAGEMENT ENGINE
# ==============================================================================

BACKUP_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "backups", "snapshots"))
os.makedirs(BACKUP_DIR, exist_ok=True)

class SnapshotCreateRequest(BaseModel):
    name: str = Field(default="Snapshot_SDN", description="Tên bản sao lưu")
    description: Optional[str] = Field(default="", description="Ghi chú mục đích sao lưu")

def create_system_snapshot(name: str, description: str = "", is_auto: bool = False) -> Dict[str, Any]:
    """Tạo bản snapshot lưu toàn bộ cấu hình SDN và Flow Table"""
    snap_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() % 1000)}"
    
    # Dump flows thực tế từ Ryu nếu có
    live_flows = {}
    for dpid in [1, 2, 3]:
        try:
            r = requests.get(f"{RYU_BASE_URL}/stats/flow/{dpid}", timeout=0.6)
            if r.status_code == 200:
                live_flows[str(dpid)] = r.json().get(str(dpid), [])
        except Exception:
            pass

    snapshot_data = {
        "id": snap_id,
        "name": name,
        "description": description or ("Bản sao lưu tự động trước khi thay đổi" if is_auto else "Bản sao lưu cấu hình SDN"),
        "is_auto": is_auto,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
        "firewall_rules": list(sdn_state.get("firewall_rules", [])),
        "qos_meters": list(sdn_state.get("qos_meters", [])),
        "live_flows": live_flows,
        "switches": list(sdn_state.get("switches", [])),
        "hosts": list(sdn_state.get("hosts", [])),
        "links": list(sdn_state.get("links", []))
    }

    file_path = os.path.join(BACKUP_DIR, f"{snap_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

    record_sdn_event(
        "SNAPSHOT_CREATE",
        "INFO",
        f"📸 Đã tạo bản Snapshot '{name}' ({len(snapshot_data['firewall_rules'])} Firewall, {len(snapshot_data['qos_meters'])} QoS)",
        {"snapshot_id": snap_id, "name": name}
    )

    return snapshot_data

@app.get("/api/sdn/snapshots")
def list_snapshots():
    """Lấy danh sách tất cả các bản snapshot đã lưu"""
    snapshots = []
    if os.path.exists(BACKUP_DIR):
        for fname in os.listdir(BACKUP_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(BACKUP_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        snapshots.append({
                            "id": data.get("id", fname[:-5]),
                            "name": data.get("name", fname[:-5]),
                            "description": data.get("description", ""),
                            "is_auto": data.get("is_auto", False),
                            "created_at": data.get("created_at", ""),
                            "timestamp": data.get("timestamp", 0),
                            "firewall_count": len(data.get("firewall_rules", [])),
                            "qos_count": len(data.get("qos_meters", [])),
                            "file_size_bytes": os.path.getsize(fpath)
                        })
                except Exception as ex:
                    print(f"[!] Lỗi đọc snapshot {fname}: {ex}")

    snapshots.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    # Nếu chưa có bản snapshot nào, tự động tạo bản Baseline ban đầu
    if len(snapshots) == 0:
        base = create_system_snapshot("Baseline_Khoi_Tao_Chuan", "Bản sao lưu chuẩn ban đầu của hệ thống", is_auto=False)
        snapshots.append({
            "id": base["id"],
            "name": base["name"],
            "description": base["description"],
            "is_auto": False,
            "created_at": base["created_at"],
            "timestamp": base["timestamp"],
            "firewall_count": len(base["firewall_rules"]),
            "qos_count": len(base["qos_meters"]),
            "file_size_bytes": os.path.getsize(os.path.join(BACKUP_DIR, f"{base['id']}.json"))
        })

    return snapshots

@app.post("/api/sdn/snapshots")
def create_snapshot_endpoint(req: SnapshotCreateRequest):
    """API Tạo Snapshot mới"""
    name = req.name.strip() or f"Snapshot_{datetime.now().strftime('%H%M%S')}"
    snap = create_system_snapshot(name, req.description, is_auto=False)
    return {"status": "success", "message": f"Đã tạo bản sao lưu '{name}' thành công", "snapshot": snap}

@app.get("/api/sdn/snapshots/{snapshot_id}")
def get_snapshot_detail(snapshot_id: str):
    """Xem chi tiết nội dung file snapshot"""
    fpath = os.path.join(BACKUP_DIR, f"{snapshot_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Không tìm thấy bản Snapshot")
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file snapshot: {ex}")

@app.delete("/api/sdn/snapshots/{snapshot_id}")
def delete_snapshot_endpoint(snapshot_id: str):
    """Xóa một bản snapshot"""
    fpath = os.path.join(BACKUP_DIR, f"{snapshot_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Không tìm thấy bản Snapshot cần xóa")
    try:
        os.remove(fpath)
        record_sdn_event("SNAPSHOT_DELETE", "INFO", f"Đã xóa bản Snapshot #{snapshot_id}")
        return {"status": "success", "message": f"Đã xóa bản sao lưu {snapshot_id}"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

@app.get("/api/sdn/snapshots/{snapshot_id}/download")
def download_snapshot_file(snapshot_id: str):
    """Tải file JSON snapshot về máy"""
    fpath = os.path.join(BACKUP_DIR, f"{snapshot_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Không tìm thấy file snapshot")
    return FileResponse(fpath, media_type="application/json", filename=f"{snapshot_id}.json")

@app.post("/api/sdn/snapshots/{snapshot_id}/restore")
def restore_snapshot_endpoint(snapshot_id: str):
    """
    1-Click Rollback: Hoàn nguyên toàn bộ cấu hình mạng về bản snapshot đã chọn!
    """
    fpath = os.path.join(BACKUP_DIR, f"{snapshot_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Không tìm thấy bản Snapshot để khôi phục")

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            snap_data = json.load(f)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file snapshot: {ex}")

    # Bước 1: Dọn dẹp toàn bộ Firewall Rules hiện tại trên switch
    for cur_fw in list(sdn_state.get("firewall_rules", [])):
        try:
            del_flow = {
                "dpid": cur_fw["dpid"],
                "priority": cur_fw.get("priority", 1000),
                "match": cur_fw.get("match", {})
            }
            requests.post(f"{RYU_BASE_URL}/stats/flowentry/delete_strict", json=del_flow, timeout=0.8)
        except Exception:
            pass

    # Bước 2: Dọn dẹp toàn bộ QoS Meters hiện tại trên switch
    for cur_m in list(sdn_state.get("qos_meters", [])):
        try:
            del_flow = {
                "dpid": cur_m["dpid"],
                "priority": 500,
                "match": {"dl_type": 2048}
            }
            if cur_m.get("src_ip"):
                del_flow["match"]["nw_src"] = cur_m["src_ip"]
            if cur_m.get("dst_ip"):
                del_flow["match"]["nw_dst"] = cur_m["dst_ip"]
            requests.post(f"{RYU_BASE_URL}/stats/flowentry/delete_strict", json=del_flow, timeout=0.8)
            requests.post(f"{RYU_BASE_URL}/stats/meterentry/delete", json={"dpid": cur_m["dpid"], "meter_id": cur_m["meter_id"]}, timeout=0.8)
        except Exception:
            pass

    # Bước 3: Nạp lại danh sách Firewall Rules từ Snapshot
    restored_fw = snap_data.get("firewall_rules", [])
    sdn_state["firewall_rules"] = list(restored_fw)
    for fw in restored_fw:
        try:
            match_dict = fw.get("match")
            if not match_dict:
                match_dict = {"dl_type": 2048}
                if fw.get("src_ip"):
                    match_dict["nw_src"] = fw["src_ip"]
                if fw.get("dst_ip"):
                    match_dict["nw_dst"] = fw["dst_ip"]
                p = fw.get("proto", "").upper()
                if p == "TCP":
                    match_dict["nw_proto"] = 6
                elif p == "UDP":
                    match_dict["nw_proto"] = 17
                elif p == "ICMP":
                    match_dict["nw_proto"] = 1
                if fw.get("dst_port"):
                    match_dict["tp_dst"] = fw["dst_port"]

            ryu_act = []
            if fw.get("action", "").upper() == "ALLOW":
                ryu_act = [{"type": "OUTPUT", "port": "NORMAL"}]

            requests.post(f"{RYU_BASE_URL}/stats/flowentry/add", json={
                "dpid": fw["dpid"],
                "priority": fw.get("priority", 1000),
                "match": match_dict,
                "actions": ryu_act
            }, timeout=0.8)
        except Exception as ex:
            print(f"[!] Lỗi phục hồi Firewall {fw.get('id')}: {ex}")

    # Bước 4: Nạp lại danh sách QoS Meters từ Snapshot
    restored_qos = snap_data.get("qos_meters", [])
    sdn_state["qos_meters"] = list(restored_qos)
    for q in restored_qos:
        try:
            mid = q["meter_id"]
            dpid = q["dpid"]
            rate = q.get("rate_kbps", 1000)
            burst = q.get("burst_size", 500)
            src_ip = q.get("src_ip", "")
            dst_ip = q.get("dst_ip", "")

            # Tạo meter table trên Ryu
            meter_payload = {
                "dpid": dpid,
                "meter_id": mid,
                "flags": ["KBPS", "BURST", "STATS"],
                "bands": [{"type": "DROP", "rate": rate, "burst_size": burst}]
            }
            requests.post(f"{RYU_BASE_URL}/stats/meterentry/add", json=meter_payload, timeout=0.8)

            # Cài flow entry priority 500
            flow_match = {"dl_type": 2048}
            if src_ip:
                flow_match["nw_src"] = src_ip
            if dst_ip:
                flow_match["nw_dst"] = dst_ip

            out_port = resolve_out_port(dpid, src_ip, dst_ip)
            actions = [
                {"type": "METER", "meter_id": mid},
                {"type": "OUTPUT", "port": out_port}
            ]
            requests.post(f"{RYU_BASE_URL}/stats/flowentry/add", json={
                "dpid": dpid,
                "priority": 500,
                "match": flow_match,
                "actions": actions
            }, timeout=0.8)
        except Exception as ex:
            print(f"[!] Lỗi phục hồi QoS Meter {q.get('meter_id')}: {ex}")

    record_sdn_event(
        "SNAPSHOT_RESTORE",
        "SUCCESS",
        f"⚡ [1-CLICK ROLLBACK] Đã khôi phục toàn bộ cấu hình mạng về bản '{snap_data.get('name')}' ({len(restored_fw)} Firewall, {len(restored_qos)} QoS)!",
        {"snapshot_id": snapshot_id, "name": snap_data.get("name")}
    )

    return {
        "status": "success",
        "message": f"Đã hoàn nguyên cấu hình về bản '{snap_data.get('name')}' thành công!",
        "restored_firewall": len(restored_fw),
        "restored_qos": len(restored_qos)
    }

if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

