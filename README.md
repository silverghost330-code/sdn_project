# ĐỒ ÁN MÔN CÔNG NGHỆ MẠNG: SDN DATA CONTROLLER ON LINUX SERVER (MININET EDITION)

Dự án xây dựng bộ điều khiển mạng định nghĩa bằng phần mềm (**Software-Defined Networking - SDN Controller**) để quản lý, giám sát và kiểm soát toàn bộ lưu lượng (traffic) trên mạng nội bộ ảo hóa **Mininet** chạy trên Linux Server theo chuẩn **OpenFlow 1.3**.

---

## 📁 Cấu Trúc Dự Án

```
D:\DỰ ÁN môn công nghệ mạng\
├── scripts\
│   ├── setup_linux_server.sh   # Cài đặt tự động Mininet, OVS, Python packages (1-click)
│   └── start_all.sh            # Khởi động toàn bộ: Ryu + Web Dashboard + Mininet (1-click)
├── controller\
│   ├── ryu_sdn_controller.py   # Ryu SDN Controller OpenFlow 1.3 (L2 Learning, Firewall, Meter QoS)
│   └── mininet_topology.py     # Script tạo topo mạng ảo hóa (3 OVS Switch Mesh, 4 Host)
├── backend\
│   ├── api_server.py           # FastAPI Northbound Gateway & REST Endpoints (bind 0.0.0.0)
│   └── ai_engine.py            # AI SDN Intent-Based Copilot (Gemini API)
├── web\
│   ├── css\styles.css          # Giao diện Dark Theme chuyên nghiệp
│   ├── js\app.js              # Logic Web Dashboard & Vẽ sơ đồ mạng Mininet realtime
│   └── index.html              # Giao diện Dashboard quản trị SDN
├── docs\
│   ├── pnetlab_lab_guide.md    # Tài liệu tham khảo: hướng dẫn mở rộng trên PNETLab (tùy chọn)
│   └── setup_ovs_node.sh       # Script cấu hình Open vSwitch node ngoài (tùy chọn)
├── run_web.py                  # Khởi động Web Dashboard (tự mở port, mở browser)
├── requirements.txt            # Thư viện Python cần thiết
└── README.md                   # Hướng dẫn chi tiết
```

---

## 🚀 Hướng Dẫn Vận Hành Trên Linux Server (3 Bước Nhanh Gọn)

### Bước 1: Sao chép thư mục dự án vào Linux Server
Bạn có thể copy thư mục dự án từ USB `D:` vào Linux Server (đặt tại thư mục `~/sdn_project`).

### Bước 2: Cài đặt môi trường tự động
Chạy script cài đặt (chỉ cần chạy 1 lần duy nhất):
```bash
cd ~/sdn_project
chmod +x scripts/*.sh
./scripts/setup_linux_server.sh
```

### Bước 3: Khởi động toàn bộ hệ thống bằng 1 lệnh duy nhất!
```bash
sudo ./scripts/start_all.sh
```

Hệ thống sẽ tự động:
1. Khởi động **Ryu Controller** (lắng nghe cổng 6653).
2. Khởi động **FastAPI Web Dashboard** (mở cổng 8000).
3. Khởi tạo **Mạng ảo hóa Mininet** (3 Switch OVS `s1`, `s2`, `s3` và 4 Host `h1`, `h2`, `h3`, `h4`).
4. Khởi động dịch vụ Web Server trên `h3` (cổng 80) và File Server trên `h4` (cổng 8080/445).

---

## 💻 Trải Nghiệm & Thử Nghiệm

1. **Truy cập Web Dashboard từ Laptop**:
   - Mở trình duyệt gõ: `http://<IP_LINUX_SERVER>:8000`
   - Xem sơ đồ mạng trực quan, kiểm tra trạng thái Switch và Host.

2. **Các câu lệnh thử nghiệm trong Mininet CLI**:
   - Kiểm tra thông mạng L2:
     ```bash
     mininet> pingall
     ```
   - Kiểm tra Web Server `h3`:
     ```bash
     mininet> h1 curl http://10.0.0.3
     ```
   - Kiểm tra truyền file sang Windows File Server `h4`:
     ```bash
     mininet> h1 curl http://10.0.0.4:8080
     ```
   - Thử nghiệm Firewall:
     - Trên Web Dashboard, bấm **Thêm Rule**: Chặn `10.0.0.2` (h2) gửi tới `10.0.0.4` (h4) cổng 445 hoặc ping.
     - Trong Mininet CLI: `h2 ping h4` -> **Bị chặn 100%**, trong khi `h1 ping h4` vẫn bình thường!
   - Thử nghiệm QoS bóp băng thông:
     - Trên Web Dashboard, tạo Meter giới hạn tốc độ `h2` còn 1000 Kbps.
     - Trong Mininet CLI: `iperf h2 h3` -> Băng thông bị bóp chặt chính xác ở ngưỡng 1.0 Mbps!
