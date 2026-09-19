# HƯỚNG DẪN XÂY DỰNG MÔ HÌNH SDN TRÊN PNETLAB

Tài liệu hướng dẫn từng bước tạo Topology mạng SDN ảo hóa trên **PNETLab**, kết nối các **Open vSwitch (OVS)** về **Ryu SDN Controller** và **Web Dashboard**.

---

## 1. Kiến Trúc Mạng Trên PNETLab

```
                   [ PNETLab Cloud0 (Management / Bridged Net) ]
                                      |
         +----------------------------+----------------------------+
         | (eth0)                                                  | (eth0)
    +-----------+ (eth2)                            (eth2)   +-----------+
    |  OVS-SW1  |============================================|  OVS-SW2  |
    +-----------+                                            +-----------+
      | (eth1)       \ (eth3)                      (eth3) /        | (eth1)
      |               \                          /                 |
   [ VPC1 ]            +======= [ OVS-SW3 ] =====+             [ VPC2 ]
(10.0.0.1)                      +-----------+                  (10.0.0.2)
                                 | (eth1)    \ (eth4)
                                 |                                      [ Web Server ]     [ Attacker ]
                           (10.0.0.3:80)      (10.0.0.4)
```

- **Cloud0 (Management Network)**: Cổng `eth0` của mỗi Switch OVS cắm vào `Cloud0` để nhận IP DHCP từ PNETLab và kết nối thẳng tới IP của máy chủ chạy Ryu Controller.
- **Data Plane (Các cổng eth1, eth2, eth3, eth4)**: Là các đường truyền dữ liệu nội bộ được OpenFlow 1.3 điều khiển hoàn toàn.

---

## 2. Các Bước Tạo Lab Trên PNETLab Web GUI

### Bước 1: Thêm các Node Switch OVS
1. Vào giao diện Web PNETLab -> Chọn **Add a Node**.
2. Tìm template: **Open vSwitch (Docker)** hoặc **Linux (chọn image OVS)**:
   - Node 1: Tên `OVS-SW1` | Cấu hình 4 NICs (eth0 đến eth3) | RAM 256MB.
   - Node 2: Tên `OVS-SW2` | Cấu hình 4 NICs (eth0 đến eth3) | RAM 256MB.
   - Node 3: Tên `OVS-SW3` | Cấu hình 5 NICs (eth0 đến eth4) | RAM 256MB.

### Bước 2: Thêm Cloud Management (Cloud0)
1. Chọn **Add a Network** -> Chọn type **Management(Cloud0)**.
2. Nối dây:
   - `OVS-SW1 (eth0)` <---> `Management(Cloud0)`
   - `OVS-SW2 (eth0)` <---> `Management(Cloud0)`
   - `OVS-SW3 (eth0)` <---> `Management(Cloud0)`

### Bước 3: Nối Dây Data Plane Giữa Các Switch & Host
1. **Liên kết giữa các Switch (Trunk Data Links)**:
   - `OVS-SW1 (eth2)` <---> `OVS-SW2 (eth2)`
   - `OVS-SW1 (eth3)` <---> `OVS-SW3 (eth2)`
   - `OVS-SW2 (eth3)` <---> `OVS-SW3 (eth3)`
2. **Thêm các End-Hosts**:
   - `VPC1`: Nối tới `OVS-SW1 (eth1)` | Đặt IP: `ip 10.0.0.1/24`
   - `VPC2`: Nối tới `OVS-SW2 (eth1)` | Đặt IP: `ip 10.0.0.2/24`
   - `Web-Server` (Ubuntu/Linux Docker): Nối tới `OVS-SW3 (eth1)` | IP `10.0.0.3/24`
   - `Attacker` (Linux/VPC): Nối tới `OVS-SW3 (eth4)` | IP `10.0.0.4/24`

---

## 3. Cấu Hình Tự Động Cho Các Switch OVS

Mở Console của từng Switch OVS trên PNETLab và chạy lệnh:

### Trên Switch 1 (OVS-SW1):
```bash
# Giả sử IP máy chủ chạy Ryu Controller là 192.168.1.100 (IP card Cloud0)
curl -O http://192.168.1.100:8000/static/setup_ovs_node.sh
chmod +x setup_ovs_node.sh
./setup_ovs_node.sh 192.168.1.100 6653 br0 0000000000000001
```

### Trên Switch 2 (OVS-SW2):
```bash
./setup_ovs_node.sh 192.168.1.100 6653 br0 0000000000000002
```

### Trên Switch 3 (OVS-SW3):
```bash
./setup_ovs_node.sh 192.168.1.100 6653 br0 0000000000000003
```

---

## 4. Điểm Độc Quyền Khi Dùng PNETLab Để Chấm Điểm

1. **Bắt gói tin OpenFlow bằng Wireshark Trực Tiếp**:
   - Nhấp chuột phải vào đường dây nối giữa `OVS-SW1 (eth0)` và `Cloud0` -> Chọn **Capture** -> **Wireshark**.
   - Bạn sẽ thấy trực tiếp các gói:
     - `OFPT_HELLO` (Bắt tay phiên OpenFlow 1.3).
     - `OFPT_FEATURES_REPLY` (Báo cáo Datapath ID và Ports).
     - `OFPT_PACKET_IN` (Switch hỏi Controller khi có luồng lạ).
     - `OFPT_FLOW_MOD` (Controller đẩy lệnh Drop / Forward xuống).
2. **Minh chứng sống động trước Giảng viên**:
   - Khi bạn bấm nút "Chặn IP" trên Web Dashboard, ngay lập tức trong Wireshark của PNETLab sẽ xuất hiện gói `OFPT_FLOW_MOD` bắn từ IP Controller sang Switch, chứng minh chuẩn kiến trúc SDN Chapter 6.
