"""
TOOL BÁO CÁO ĐƠN HÀNG B2B LÊN TELEGRAM (Phiên bản Hybrid)
- Apps Script Web App: đọc Sheet + lọc PIC
- Python local: check GHN + gửi Telegram
Hẹn giờ 9h, 13h, 15h bằng Windows Task Scheduler.
"""

import urllib.request
import urllib.error
import json
import sys
import time
from datetime import datetime

# Fix Unicode trên Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ==========================================
# CẤU HÌNH
# ==========================================

TELEGRAM_TOKEN = "8261927820:AAEuN92GJ5kALTBwIKXi7hu7NKJnXFX0EdU"
CHAT_ID = "-1003817788024"
TOPIC_ID = 1575  # Topic/thread trong supergroup
PIC_NAME = "Đào Anh Duy"

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbwNwZ9as40oj8M5sO1SJn8HC7FKPFy7i0mvEiM8WOKpHJfBAT1RBhHSc5ybNKPmvifo/exec"

# GHN API
GHN_URL = "https://fe-online-gateway.ghn.vn/order-tracking/public-api/client/tracking-logs"

# Trạng thái cần bỏ qua (4 trạng thái)
# - delivered = giao thành công
# - delivery_fail = giao hàng không thành công
# - transporting = đang trung chuyển hàng giao/hàng trả
# - delivering = đang giao hàng / đã gán chuyến đi
SKIP_STATUSES = ["delivered", "delivery_fail", "transporting", "delivering"]


# ==========================================
# HÀM CHECK TRẠNG THÁI GHN
# ==========================================

def check_ghn(order_code):
    """Gọi API GHN — trả về (should_skip, status_name_vn)."""
    for attempt in range(3):
        try:
            data = json.dumps({"order_code": order_code.strip()}).encode("utf-8")
            req = urllib.request.Request(GHN_URL, data=data, headers={
                "Content-Type": "application/json",
                "Origin": "https://donhang.ghn.vn",
                "Referer": "https://donhang.ghn.vn/",
                "User-Agent": "Mozilla/5.0"
            })
            res = urllib.request.urlopen(req, timeout=10)
            result = json.loads(res.read().decode("utf-8"))

            if result.get("code") == 200 and result.get("data"):
                order_info = result["data"].get("order_info", {})
                status = order_info.get("status", "").lower()
                status_name = order_info.get("status_name", "")
                should_skip = any(s in status for s in SKIP_STATUSES)
                print(f"  GHN {order_code} -> {status} ({status_name}) -> {'BO QUA' if should_skip else 'GIU LAI'}")
                time.sleep(1.5)
                return should_skip, status_name
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 3 * (attempt + 1)
                print(f"  GHN {order_code} -> 429 rate limit, cho {wait}s...")
                time.sleep(wait)
                continue
            print(f"  GHN {order_code} -> HTTP {e.code}")
        except Exception as e:
            print(f"  GHN {order_code} -> Loi: {e}")
        time.sleep(1.5)
    return False, ""


# ==========================================
# HÀM GỬI TELEGRAM (HTML mode — bold đáng tin cậy)
# ==========================================

def send_telegram(text):
    """Gửi tin nhắn lên Telegram dùng HTML. Tự chia nhỏ nếu quá dài."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX_LEN = 4000  # Telegram giới hạn 4096, để dư

    # Chia tin nhắn thành nhiều phần nếu quá dài
    if len(text) <= MAX_LEN:
        chunks = [text]
    else:
        chunks = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > MAX_LEN:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)

    for i, chunk in enumerate(chunks):
        msg_data = {
            "chat_id": CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if TOPIC_ID:
            msg_data["message_thread_id"] = TOPIC_ID
        payload = json.dumps(msg_data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            res = urllib.request.urlopen(req, timeout=10)
            result = json.loads(res.read().decode("utf-8"))
            if not result.get("ok"):
                print(f"Telegram loi part {i+1}: {result}")
        except Exception as e:
            print(f"Loi Telegram part {i+1}: {e}")
        time.sleep(1)  # Tránh rate limit Telegram


# ==========================================
# HÀM CHÍNH
# ==========================================

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Bat dau bao cao...")

    # 1. Đọc dữ liệu trực tiếp từ Google Sheet CSV (Bỏ qua Web App)
    print("Doc du lieu truc tiep tu Google Sheet (CSV)...")
    try:
        csv_url = "https://docs.google.com/spreadsheets/d/1AxoVdTpPcYn49qqWzmlYzWsKWk8v9UahErtBntBqn6g/export?format=csv&gid=566926461"
        res = urllib.request.urlopen(csv_url, timeout=30)
        text = res.read().decode("utf-8").splitlines()
        import csv
        reader = csv.reader(text)
        data = list(reader)
    except Exception as e:
        print(f"LOI: Khong ket noi duoc Google Sheet! {e}")
        send_telegram("❌ <b>LỖI BÁO CÁO</b>\nKhông đọc được Google Sheet")
        return

    # Tìm dòng header
    header_idx = 0
    for h in range(min(len(data), 10)):
        row_text = " ".join(data[h]).lower()
        if "pic" in row_text and "order" in row_text:
            header_idx = h
            break
            
    headers = [str(x).lower().strip() for x in data[header_idx]]
    col = {"pic": -1, "kho": -1, "khach": -1, "ma_don": -1, "ngay_nhap": -1, "flag": -1}
    for i, h in enumerate(headers):
        if col["pic"] == -1 and "pic" in h: col["pic"] = i
        if col["kho"] == -1 and any(x in h for x in ["kho hiện tại", "kho hiện", "kho giao hàng"]): col["kho"] = i
        if col["khach"] == -1 and any(x in h for x in ["khách", "tên khách", "khách hàng", "customer", "shop"]): col["khach"] = i
        if col["ma_don"] == -1 and any(x in h for x in ["order code", "order_code", "mã đơn", "mã vđ", "mã vận đơn", "mvd"]): col["ma_don"] = i
        if col["ngay_nhap"] == -1 and any(x in h for x in ["ngày nhập kho", "ngày nhập", "nhập kho"]): col["ngay_nhap"] = i
        if col["flag"] == -1 and any(x in h for x in ["flag_hen_gio", "flag_hẹn_giờ", "hẹn giờ", "hen gio"]): col["flag"] = i

    orders = []
    for i in range(header_idx + 1, len(data)):
        row = data[i]
        
        def get_cell(idx):
            return row[idx].strip() if idx != -1 and idx < len(row) else ""
            
        pic = get_cell(col["pic"])
        if PIC_NAME.lower() not in pic.lower():
            continue
            
        orders.append({
            "kho": get_cell(col["kho"]),
            "khach": get_cell(col["khach"]),
            "ma_don": get_cell(col["ma_don"]),
            "ngay_nhap": get_cell(col["ngay_nhap"]),
            "flag": get_cell(col["flag"])
        })

    print(f"Nhan {len(orders)} don tu Google Sheet")
    if not orders:
        print("Khong co don nao.")
        return

    # 3. Sắp xếp: Kho → Ngày nhập (cũ trước) → Khách
    orders.sort(key=lambda o: (o.get("kho", ""), o.get("ngay_nhap", ""), o.get("khach", "")))

    # 4. Check GHN & tạo báo cáo (dùng HTML)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    today_str = datetime.now().strftime("%Y-%m-%d")

    lines = []
    lines.append("📦 <b>BÁO CÁO ĐƠN HÀNG B2B</b>")
    lines.append(f"👤 PIC: {PIC_NAME}")
    lines.append(f"⏰ {now}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    stt = 0
    total = 0
    skipped = 0
    current_kho = ""

    print("Kiem tra trang thai GHN...")
    for o in orders:
        ma_don = o.get("ma_don", "")
        kho = o.get("kho", "")
        khach = o.get("khach", "")
        ngay_nhap = o.get("ngay_nhap", "")
        flag = o.get("flag", "")
        # Bỏ qua kho cụ thể theo yêu cầu
        kho_lower = kho.lower()
        if "kho lấy hàng concung hưng yên" in kho_lower:
            continue

        # Check GHN → bỏ qua theo danh sách
        status_name = ""
        if ma_don:
            skip, status_name = check_ghn(ma_don)
            if skip:
                skipped += 1
                continue

        # Nhóm theo Kho (reset STT)
        if kho and kho != current_kho:
            current_kho = kho
            stt = 0
            lines.append("")
            lines.append(f"🏭 <b>{kho}</b>")

        # Format ngày: dd/MM (ngắn gọn), tô đậm nếu quá khứ
        ngay_display = ""
        if ngay_nhap:
            try:
                parts = ngay_nhap.split("-")  # yyyy-MM-dd
                short_date = f"{parts[2]}/{parts[1]}"  # dd/MM
                if ngay_nhap < today_str:
                    ngay_display = f"<b>{short_date}</b>"
                else:
                    ngay_display = short_date
            except:
                ngay_display = ngay_nhap

        stt += 1
        total += 1
        line = f'{stt}. {khach} — <a href="https://tracuunoibo.ghn.vn/internal?order_code={ma_don}">{ma_don}</a>'
        if ngay_display:
            line += f" — Nhập: {ngay_display}"
        if status_name:
            line += f" — {status_name}"
        if flag:
            line += f" ⏰ {flag}"
        lines.append(line)

    # 5. Gửi Telegram
    message = "\n".join(lines)
    print(f"\nGui Telegram ({total} don, bo {skipped} don)...")
    send_telegram(message)
    print("XONG!")


if __name__ == "__main__":
    main()
