# 4. การสาธิตการทำงานของโปรแกรม (Live Demo)

## เตรียมก่อนสาธิต
1. `cp .env.example .env` แล้วกรอกค่า (ดู [10-cicd.md](10-cicd.md))
2. `docker compose up -d --build`
3. เปิด `http://localhost/`
4. เตรียม 2 หน้าจอ/แท็บ: **นักศึกษา** กับ **เจ้าหน้าที่** (login คนละบัญชี) + ข้อมูลตัวอย่างจาก `python manage.py seed_demo_data`

## 4.1 Use Case หลัก — ไหลครบวงจร "จอง → รับ → คืน → บทลงโทษ"

```mermaid
sequenceDiagram
    actor S as นักศึกษา
    actor T as เจ้าหน้าที่
    participant SYS as ระบบ
    S->>SYS: 1. ล็อกอิน + ดูอุปกรณ์ (เห็นจำนวนคงเหลือสด)
    S->>SYS: 2. จองอุปกรณ์ (เลือกวันเริ่ม-คืน)
    SYS-->>S: ได้รหัสจอง BK-XXXX + อีเมลยืนยัน (unit → reserved)
    T->>SYS: 3. สแกน QR/ค้นรหัส → กดยืนยันรับ
    SYS-->>S: อีเมลรับของสำเร็จ (unit → borrowed)
    Note over SYS: ครบกำหนด ระบบส่งอีเมลเตือน (ใกล้ครบ/ถึง/เกิน)
    T->>SYS: 4. กดยืนยันคืน (+ ติดธงชำรุดถ้ามี)
    SYS-->>S: อีเมลคืนสำเร็จ; ถ้าคืนช้าเกินเกณฑ์ → พักสิทธิ์ + อีเมลแจ้ง
```

**ลำดับที่จะกดโชว์จริง (พร้อมสิ่งที่ชี้ให้ดู):**
| # | ผู้ทำ | การกระทำ | ชี้ให้กรรมการเห็น |
|:-:|------|----------|------------------|
| 1 | นักศึกษา | ดูรายการอุปกรณ์ | ตัวเลข "คงเหลือ" ตรงกับจำนวนชิ้นว่างจริง |
| 2 | นักศึกษา | จอง 1 ชิ้น | ได้รหัส `BK-...`, คงเหลือลดทันที, มีอีเมลเข้า log |
| 3 | เจ้าหน้าที่ | สแกน QR → **หน้าจอแค่แสดงข้อมูล ยังไม่เปลี่ยนสถานะ** → กดยืนยันรับ | สถานะเปลี่ยนก็ต่อเมื่อกดปุ่ม (ดู edge case ข้อ c) |
| 4 | เจ้าหน้าที่ | ยืนยันคืน (ตั้งวันคืนย้อนให้เกินกำหนดเพื่อโชว์บทลงโทษ) | บัญชีนักศึกษาถูกพักสิทธิ์ + จองใหม่ไม่ได้ |
| 5 | เจ้าหน้าที่ | Dashboard | ตัวเลขสรุปอัปเดตตามการทำรายการ |

## 4.2 การจัดการ Error / Edge Case

ทุกเคสด้านล่าง **มีเทสต์อัตโนมัติครอบคลุมอยู่แล้ว** ใน `backend/rental/tests.py` (รวม 39 เคส + เทสต์หน้าเว็บใน `backend/frontend/tests.py` อีก 10 เคส ผ่านทั้งหมด) จะสาธิตผ่าน UI หรือโชว์ผลรันเทสต์ก็ได้

| Edge case | พฤติกรรมที่ถูกต้อง | โค้ด | เทสต์ |
|-----------|-------------------|------|------|
| **(a) ของหมด / จองชนกัน (race)** | คนที่สองได้ข้อความ "ของหมด" ไม่ได้ของซ้ำ | `services.py:93` `select_for_update(skip_locked=True)` | `test_out_of_stock_rejected`, `test_cancel_returns_unit_to_stock` |
| **(b) จองซ้อน (1 คน 1 รายการ)** | จองใหม่ไม่ได้ถ้ายังมีรายการค้าง | `services.py:82-91` | `test_same_student_cannot_double_book_same_model` |
| **(c) สแกน QR ≠ ยืนยันอัตโนมัติ** | การค้นด้วย QR อ่านอย่างเดียว ไม่เปลี่ยนสถานะ | `StaffBookingLookupView` (read-only) | `test_qr_lookup_does_not_change_status` |
| **(d) วันที่ไม่ถูกต้อง** | เริ่มย้อนหลัง/คืนก่อนเริ่ม/ยืมนานเกิน/จองล่วงหน้าไกลเกิน → ปฏิเสธ | `services.py:56-63,77` | `test_invalid_dates_rejected` |
| **(e) สิทธิ์ข้ามบทบาท** | นักศึกษาเรียก endpoint เจ้าหน้าที่ไม่ได้ และกลับกัน | `permissions.py` | `test_student_cannot_use_staff_endpoints`, `test_staff_cannot_book` |
| **(f) คืนก่อนรับ** | ยืนยันคืนรายการที่ยังไม่รับไม่ได้ | `services.py:182` | `test_cannot_confirm_return_before_pickup` |
| **(g) ยกเลิกของคนอื่น** | นักศึกษายกเลิก booking ที่ไม่ใช่ของตัวเองไม่ได้ | view เช็ค owner | `test_student_cannot_cancel_others_booking` |
| **(h) แก้สถานะ unit มั่ว** | เจ้าหน้าที่ตั้ง unit เป็น reserved/borrowed เองไม่ได้ | view guard | `test_unit_status_guard` |
| **(i) อีเมลส่งล้มเหลว** | ไม่ล้มทั้ง request — บันทึก log ว่าส่งไม่สำเร็จ | `notifications.py` | `test_email_failure_is_logged_not_raised` |
| **(j) no-show** | ไม่มารับตามเวลา → ระบบยกเลิกและคืนของเข้าสต็อก | `jobs.py` | `test_no_show_is_cancelled_and_stock_restored` |

### คำสั่งรันเทสต์โชว์หน้างาน
```bash
cd backend
python manage.py test --verbosity 2
# ผล: Ran 49 tests ... OK
```

> จุดขายเวลาสาธิต: ไม่ได้แค่ "เดินผ่าน happy path" แต่ **ทุก edge case มีเทสต์ยืนยัน** และกฎสำคัญที่สุด (race condition) ถูกบังคับที่ระดับฐานข้อมูล ไม่ใช่แค่เช็คในโค้ด
