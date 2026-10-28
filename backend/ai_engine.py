# -*- coding: utf-8 -*-
"""
AI Engine for SDN Controller (Intent-Based Networking - Mininet Edition)
Chuyển đổi ý định điều khiển mạng bằng ngôn ngữ tự nhiên thành OpenFlow 1.3 Rules.
"""

import os
import sys
import json
import re
import requests
from typing import Dict, List, Any, Optional, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def build_sdn_system_prompt() -> str:
    return """Bạn là Trợ lý AI Kỹ sư SDN (Software-Defined Networking & Intent-Based Networking Copilot).
Nhiệm vụ của bạn là nhận các yêu cầu điều khiển, giám sát hoặc định tuyến lưu lượng từ người quản trị và chuyển thành cấu trúc JSON chuẩn để gửi tới SDN Controller (Ryu / OpenFlow 1.3) điều khiển mạng ảo hóa Mininet.

HẠ TẦNG MẠNG MININET (OPEN VSWITCH & HOSTS):
- Switches:
  * s1 (DPID 1): Core Switch (Trunk nối s2, s3)
  * s2 (DPID 2): Distribution Switch (Trunk nối s1, s3)
  * s3 (DPID 3): Server Farm Switch (Trunk nối s1, s2)
- Hosts / Endpoints:
  * h1 (IP: 10.0.0.1, MAC: 00:00:00:00:00:01) - Máy Client 1 (nối s1)
  * h2 (IP: 10.0.0.2, MAC: 00:00:00:00:00:02) - Máy Client 2 (nối s2)
  * h3 (IP: 10.0.0.3, MAC: 00:00:00:00:00:03) - Web Server HTTP cổng 80 (nối s3)
  * h4 (IP: 10.0.0.4, MAC: 00:00:00:00:00:04) - Windows File Server / Attacker (nối s3)

QUY TẮC CẤU TRÚC JSON ĐẦU RA BẮT BUỘC:
Trả về DUY NHẤT một khối JSON (bọc trong ```json ... ```):

{
  "intent": "FIREWALL_DROP" | "FIREWALL_ALLOW" | "QOS_LIMIT" | "DYNAMIC_ROUTING" | "INFO_QUERY",
  "target_switch": 1,
  "priority": 1000,
  "match": {
    "eth_type": 2048,
    "ipv4_src": "10.0.0.4",
    "ipv4_dst": "10.0.0.3",
    "ip_proto": 6,
    "tcp_dst": 80
  },
  "rate_kbps": 2000,
  "explanation": "Giải thích ngắn gọn bằng tiếng Việt lý do và tác động của rule này tới mạng Mininet."
}
"""

def parse_sdn_intent_locally(user_prompt: str) -> Dict[str, Any]:
    """
    Trình phân tích ý định ngôn ngữ tự nhiên thông minh (hỗ trợ tiếng Việt có dấu, không dấu, tiếng Anh)
    Chuyển đổi thành OpenFlow 1.3 Rule chính xác.
    """
    p_lower = user_prompt.lower()
    
    # Loại bỏ dấu tiếng Việt để kiểm tra không dấu
    def remove_accents(input_str):
        import unicodedata
        s = unicodedata.normalize('NFD', input_str)
        return ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    
    p_no_accents = remove_accents(p_lower)

    # 1. Phát hiện Intent
    is_drop = any(w in p_lower or w in p_no_accents for w in [
        'chặn', 'chan', 'cấm', 'cam', 'ngăn', 'ngan', 'khoá', 'khoa', 'hủy', 'huy',
        'drop', 'block', 'deny', 'reject', 'filter'
    ])
    is_qos = any(w in p_lower or w in p_no_accents for w in [
        'giới hạn', 'gioi han', 'bóp', 'bop', 'qos', 'băng thông', 'bang thong',
        'rate', 'limit', 'tốc độ', 'toc do'
    ])
    is_allow = any(w in p_lower or w in p_no_accents for w in [
        'cho phép', 'cho phep', 'mở', 'mo', 'allow', 'permit', 'pass'
    ])

    # 2. Nhận diện các Host & IP
    host_map = {
        'h1': {'ip': '10.0.0.1', 'sw': 1, 'name': 'Host h1 (10.0.0.1)'},
        'pc1': {'ip': '10.0.0.1', 'sw': 1, 'name': 'Host h1 (10.0.0.1)'},
        'client 1': {'ip': '10.0.0.1', 'sw': 1, 'name': 'Host h1 (10.0.0.1)'},
        'h2': {'ip': '10.0.0.2', 'sw': 2, 'name': 'Host h2 (10.0.0.2)'},
        'pc2': {'ip': '10.0.0.2', 'sw': 2, 'name': 'Host h2 (10.0.0.2)'},
        'client 2': {'ip': '10.0.0.2', 'sw': 2, 'name': 'Host h2 (10.0.0.2)'},
        'h3': {'ip': '10.0.0.3', 'sw': 3, 'name': 'Web Server h3 (10.0.0.3)'},
        'web': {'ip': '10.0.0.3', 'sw': 3, 'name': 'Web Server h3 (10.0.0.3)'},
        'http': {'ip': '10.0.0.3', 'sw': 3, 'name': 'Web Server h3 (10.0.0.3)'},
        'h4': {'ip': '10.0.0.4', 'sw': 3, 'name': 'File Server h4 (10.0.0.4)'},
        'file': {'ip': '10.0.0.4', 'sw': 3, 'name': 'File Server h4 (10.0.0.4)'},
        'smb': {'ip': '10.0.0.4', 'sw': 3, 'name': 'File Server h4 (10.0.0.4)'},
        'samba': {'ip': '10.0.0.4', 'sw': 3, 'name': 'File Server h4 (10.0.0.4)'},
        'server': {'ip': '10.0.0.4', 'sw': 3, 'name': 'Server h4 (10.0.0.4)'},
        'win': {'ip': '10.0.0.4', 'sw': 3, 'name': 'File Server h4 (10.0.0.4)'}
    }

    # Tìm explicit IP trong prompt
    ip_matches = re.findall(r'\b10\.0\.0\.[1-4]\b', p_lower)
    
    # Tìm src và dst
    src_host = None
    dst_host = None

    if len(ip_matches) >= 2:
        src_ip = ip_matches[0]
        dst_ip = ip_matches[1]
    elif len(ip_matches) == 1:
        src_ip = ip_matches[0]
        dst_ip = '10.0.0.4' if src_ip != '10.0.0.4' else '10.0.0.3'
    else:
        # Nhận diện theo tên host
        found_keys = []
        for key in ['h1', 'h2', 'h3', 'h4', 'web', 'file', 'smb', 'pc1', 'pc2']:
            if re.search(r'\b' + key + r'\b', p_lower):
                found_keys.append(key)
        
        if len(found_keys) >= 2:
            src_host = host_map[found_keys[0]]
            dst_host = host_map[found_keys[1]]
            src_ip = src_host['ip']
            dst_ip = dst_host['ip']
        elif len(found_keys) == 1:
            src_host = host_map[found_keys[0]]
            src_ip = src_host['ip']
            dst_ip = '10.0.0.4' if src_ip != '10.0.0.4' else '10.0.0.3'
        else:
            # Mặc định an toàn
            src_ip = '10.0.0.2'
            dst_ip = '10.0.0.4'

    # Nhận diện Port & Protocol
    ip_proto = None
    tcp_dst = None
    if any(w in p_lower for w in ['445', 'smb', 'file', 'samba', 'share']):
        ip_proto = 6
        tcp_dst = 445
    elif any(w in p_lower for w in ['8080', 'port 8080']):
        ip_proto = 6
        tcp_dst = 8080
    elif any(w in p_lower for w in ['80', 'web', 'http', 'nginx']):
        ip_proto = 6
        tcp_dst = 80
    elif any(w in p_lower or w in p_no_accents for w in ['ping', 'icmp']):
        ip_proto = 1
    elif 'udp' in p_lower:
        ip_proto = 17
    elif 'tcp' in p_lower:
        ip_proto = 6

    # 3. Phân luồng trả kết quả
    if is_qos:
        # Tìm số băng thông chuẩn xác (ưu tiên cụm có đơn vị k/kbps/m/mbps)
        rate = 1000
        unit_match = re.search(r'(\d+)\s*(kbps|k|mbps|m)\b', p_lower)
        if unit_match:
            val = int(unit_match.group(1))
            unit = unit_match.group(2).lower()
            rate = val * 1000 if 'm' in unit else val
        else:
            num_match = re.search(r'(?:băng thông|bang thong|tốc độ|toc do|mức|muc|rate|limit)\s*(?:là|la|khoảng|khoang)?\s*(\d+)', p_lower)
            if num_match:
                rate = int(num_match.group(1))
            else:
                big_nums = [int(n) for n in re.findall(r'\b\d+\b', p_lower) if int(n) >= 50]
                if big_nums:
                    rate = big_nums[0]
        
        has_two_endpoints = len(found_keys) >= 2 or len(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', user_prompt)) >= 2
        dst_endpoint = dst_ip if has_two_endpoints else ""
        target_label = f"{src_ip} ➔ {dst_ip}" if has_two_endpoints else f"Host ({src_ip})"
        target_switch = 2 if src_ip == '10.0.0.2' else (1 if src_ip == '10.0.0.1' else 3)
        
        match_dict = {"ipv4_src": src_ip}
        if dst_endpoint:
            match_dict["ipv4_dst"] = dst_endpoint

        return {
            "intent": "QOS_LIMIT",
            "target_switch": target_switch,
            "rate_kbps": rate,
            "src_ip": src_ip,
            "dst_ip": dst_endpoint,
            "match": match_dict,
            "target": target_label,
            "explanation": f"Hệ thống đã nhận diện ý định QoS: '{user_prompt}'. Giới hạn băng thông từ {src_ip} đến {dst_endpoint or 'mọi đích'} ở mức {rate} Kbps trên Switch s{target_switch}."
        }
    
    # Mặc định hoặc Drop / Allow
    action = "ALLOW" if is_allow else "DROP"
    target_switch = 3 if dst_ip in ['10.0.0.3', '10.0.0.4'] else (2 if dst_ip == '10.0.0.2' else 1)
    
    match_data = {
        "ipv4_src": src_ip,
        "ipv4_dst": dst_ip
    }
    if ip_proto:
        match_data["ip_proto"] = ip_proto
    if tcp_dst:
        match_data["tcp_dst"] = tcp_dst

    proto_name = "TCP" if ip_proto == 6 else ("ICMP (Ping)" if ip_proto == 1 else "ANY")
    port_text = f" cổng {tcp_dst}" if tcp_dst else ""

    return {
        "intent": "FIREWALL_DROP" if action == "DROP" else "FIREWALL_ALLOW",
        "action": action,
        "target_switch": target_switch,
        "priority": 1000,
        "match": match_data,
        "explanation": f"Hệ thống phân tích ý định: '{user_prompt}'. Thiết lập luật {action} lưu lượng {proto_name}{port_text} từ {src_ip} tới {dst_ip} trên Switch s{target_switch}."
    }

def extract_and_validate_json(ai_response_text: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    if not ai_response_text:
        return False, None, "AI không trả về nội dung."
    clean_text = ai_response_text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', clean_text, re.IGNORECASE)
    if match:
        clean_text = match.group(1).strip()
    try:
        data = json.loads(clean_text)
        return True, data, "OK"
    except json.JSONDecodeError as e:
        return False, None, f"Lỗi parse JSON: {e}"

def call_gemini_api(api_key: str, user_prompt: str, model: str = "gemini-1.5-flash") -> Tuple[bool, str]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    system_instruction = build_sdn_system_prompt()
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_instruction}\n\nYÊU CẦU ĐIỀU KHIỂN TRAFFIC:\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048
        }
    }
    try:
        resp = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=40)
        if resp.status_code != 200:
            return False, f"Lỗi Gemini API ({resp.status_code}): {resp.text}"
        res_json = resp.json()
        candidates = res_json.get("candidates", [])
        if not candidates:
            return False, "Không có kết quả trả về từ Gemini."
        return True, candidates[0]["content"]["parts"][0]["text"]
    except Exception as e:
        return False, f"Lỗi kết nối: {str(e)}"

