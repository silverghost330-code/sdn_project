#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Menu Hỗ Trợ Chụp Ảnh Báo Cáo Đồ Án SDN (Tích hợp LLDP Topology & Host Discovery)
Cách chạy:
    python3 menu_chup_anh.py
"""

import sys
from demo_do_an import demo_1_lldp_topology, demo_2_switches_and_hosts

if __name__ == "__main__":
    if "--all" in sys.argv:
        demo_1_lldp_topology()
        demo_2_switches_and_hosts()
    else:
        from demo_do_an import main
        main()

